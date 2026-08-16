#!/usr/bin/env python3
""" How the generated client reaches the service.

    Everything here is written by hand.  The operations -- one method
    per endpoint -- are generated from the committed specification into
    '_operations.py', so the surface cannot drift from the contract
    (D15), while the parts worth reading and testing stay ordinary
    code.

    The split is what makes generation cheap.  A generator that also
    emitted the session handling, the credential and the failure
    mapping would have to be reviewed every time it changed; this way
    the generated file holds nothing but the shape of the API.
"""

# Imports - Python Standard Library
from typing import Any, Dict, Iterator, Optional
from urllib.parse import quote

# Imports - Third-Party
from requests import Response, Session

# Imports - Local
from ._operations import Operations
from ._stream import events, StreamEvent

# Constants
# What the service returns when something went wrong (RFC 9457).
PROBLEM_MEDIA_TYPE = 'application/problem+json'

# How long to wait for a response.  Set rather than left unbounded: a
# client that waits for ever on a service that has stopped answering
# looks identical to one doing careful work.  The stream reads use
# their own, because a job can be quiet for minutes and a heartbeat is
# the only traffic between reports.
REQUEST_TIMEOUT_SECONDS = 30
STREAM_TIMEOUT_SECONDS = 300

# What a stream is decoded as.  Server-sent events are UTF-8 by
# specification, so it is fixed here rather than taken from the
# response: a stream arriving without a charset would otherwise be
# handed back as bytes by a method that says it returns text, and the
# service declaring one today is not a reason for the client to need
# it to.
STREAM_ENCODING = 'utf-8'


class ApiProblem(Exception):
    """ A failure the service described.

        Carries the problem document rather than only its text,
        because the reference is what correlates with the service log
        and is the one part of a 5xx that a person can act on: the
        reason is deliberately not in the response.

        Attributes:
            status (int):
                The response status.

            title (str):
                What went wrong, in a few words.

            detail (str, optional):
                Why, when the service says.  A response of 500 or
                above never carries one.

            reference (str, optional):
                The identifier the same failure is logged against.

            document (Dict[str, Any]):
                The problem document as it arrived.
    """

    def __init__(
            self,
            status: int,
            document: Dict[str, Any]
    ) -> None:
        """ Build the failure from the document the service returned.

            Args:
                status (int):
                    The response status.

                document (Dict[str, Any]):
                    The problem document, or what could be read of it.

            Returns:
                None.
        """

        self.status = status
        self.title = document.get('title', 'The request failed.')
        self.detail = document.get('detail')
        self.reference = document.get('reference')
        self.document = document

        super().__init__(
            f'{status} {self.title}'
            + (f': {self.detail}' if self.detail else '')
            + (f' (reference {self.reference})' if self.reference else '')
        )


class Client(Operations):
    """ A client for the star-pass API.

        The operations are inherited from the generated half, so this
        class holds only what they call: where the service is, what
        credential to present, and what to do with a response.
    """

    def __init__(
            self,
            base_url: str,
            token: str,
            session: Optional[Session] = None
    ) -> None:
        """ Point the client at a service and give it a credential.

            Args:
                base_url (str):
                    Where the service is, without a trailing path.

                token (str):
                    The bearer token to present.  Sent in the
                    Authorization header and never in a query string,
                    which lands in access logs.

                session (Session, optional):
                    A session to send through.  Defaults to None,
                    which builds one.

            Returns:
                None.
        """

        self._base_url = base_url.rstrip('/')
        self._session = session if session is not None else Session()
        self._session.headers['Authorization'] = f'Bearer {token}'

    def _url(
            self,
            path: str,
            **parameters: Any
    ) -> str:
        """ Return the address of one operation.

            Path values are escaped rather than interpolated as they
            arrive: an identifier is a value, and a value that could
            introduce a path segment would let a caller address
            something they did not ask for.

            Args:
                path (str):
                    The templated path from the specification.

                **parameters (Any):
                    Values for the template's placeholders.

            Returns:
                url (str):
                    The full address.
        """

        filled = path.format(
            **{
                name: quote(str(value), safe='')
                for name, value in parameters.items()
            }
        )

        return f'{self._base_url}{filled}'

    def _raise_for_problem(
            self,
            response: Response
    ) -> None:
        """ Turn a failed response into a failure a caller can catch.

            Args:
                response (Response):
                    The response to check.

            Raises:
                ApiProblem:
                    If the service reported a failure.

            Returns:
                None.
        """

        if response.ok:
            return None

        try:
            document = response.json()

        except ValueError:
            # A failure from something in front of the service, which
            # does not answer in problem documents.
            document = {}

        raise ApiProblem(
            status=response.status_code,
            document=document if isinstance(document, dict) else {}
        )

    def _call(
            self,
            method: str,
            path: str,
            body: Optional[Dict[str, Any]] = None,
            **parameters: Any
    ) -> Any:
        """ Send one request and return what the service answered.

            Args:
                method (str):
                    The HTTP method.

                path (str):
                    The templated path from the specification.

                body (Dict[str, Any], optional):
                    What to send.  Defaults to None, for an operation
                    that is sent nothing.  Named separately from the
                    path values, which fill the template: a body that
                    arrived among them would be interpolated into the
                    address.

                **parameters (Any):
                    Values for the template's placeholders.

            Raises:
                ApiProblem:
                    If the service reported a failure.

            Returns:
                answer (Any):
                    The decoded response body.
        """

        response = self._session.request(
            method=method,
            url=self._url(path=path, **parameters),
            json=body,
            timeout=REQUEST_TIMEOUT_SECONDS
        )

        self._raise_for_problem(response=response)

        return response.json()

    def _stream(
            self,
            method: str,
            path: str,
            **parameters: Any
    ) -> Iterator[StreamEvent]:
        """ Hold a request open and yield what arrives on it.

            The lines are parsed here rather than handed on, because
            the other half of this client answers the same operation
            from the database and has no wire syntax to hand on (D2).
            Parsing on the side that receives it is what lets a caller
            work with one record either way.

            Args:
                method (str):
                    The HTTP method.

                path (str):
                    The templated path from the specification.

                **parameters (Any):
                    Values for the template's placeholders.

            Raises:
                ApiProblem:
                    If the service reported a failure.

                StreamProtocolError:
                    If a frame is not what the contract says it is.

            Yields:
                event (StreamEvent):
                    One event, in the order they arrive.
        """

        with self._session.request(
            method=method,
            url=self._url(path=path, **parameters),
            timeout=STREAM_TIMEOUT_SECONDS,
            stream=True
        ) as response:
            self._raise_for_problem(response=response)

            response.encoding = STREAM_ENCODING

            yield from events(
                lines=response.iter_lines(decode_unicode=True)
            )
