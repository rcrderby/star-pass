#!/usr/bin/env python3
""" The generated client reaches everything the contract publishes.

    Two questions, and they are different.  The first is whether the
    committed client still matches the contract, which is what makes
    generating it worth doing: a client generated once and then left
    behind describes a service that no longer exists.  The second is
    what the written half does with a request and a response, which no
    generator decides.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
import json
from io import BytesIO
from typing import Any, Callable, Dict, List, Optional

# Imports - Third-Party
import pytest
from requests import Response, Session

# Imports - Local
from star_pass_client import ApiProblem, Client, StreamEvent
from star_pass_client import _generator
from star_pass_client._client import PROBLEM_MEDIA_TYPE
from star_pass_client._operations import Operations

# Constants
BASE_URL = 'https://star-pass.test'
# Long enough to look like a real one, and not a real one.
CLIENT_CREDENTIAL = 'test-star-pass-api-value-not-a-real-one'

DRIFT_MESSAGE = (
    'The committed client no longer matches the contract. Run '
    f'"{_generator.REGENERATE_COMMAND}" and commit the result.'
)


class RecordingSession(Session):
    """ A session that answers from a script and remembers the asking. """

    def __init__(
            self,
            status: int = 200,
            body: Any = None,
            media_type: str = 'application/json',
            lines: Optional[List[str]] = None
    ) -> None:
        """ Prepare the answer every request will receive. """
        super().__init__()
        self.calls: List[Dict[str, Any]] = []
        self._status = status
        self._body = body if body is not None else {}
        self._media_type = media_type
        self._lines = lines

    # Stands in for 'Session.request' and never reaches a socket.
    # Every argument beyond the two the client names is collected, so
    # a test can assert on what was asked for.
    # pylint: disable=arguments-differ
    def request(self, method, url, **kwargs):  # type: ignore[override]
        """ Record the request and return the prepared answer.

            The headers a request carries are the session's plus its
            own, which is what the real session does; recorded the
            other way round, a request naming none of its own would
            look like one carrying no credential.
        """
        sent = dict(self.headers)
        sent.update(kwargs.pop('headers', None) or {})
        self.calls.append({
            'method': method,
            'url': url,
            'headers': sent,
            **kwargs
        })

        if self._lines is not None:
            # Every line is terminated, including the last.  Joined
            # without that, a trailing blank line is only a trailing
            # newline on the wire and the reader never sees the line
            # that says the frame is complete -- so the harness would
            # be sending something the service does not.
            content = ''.join(
                f'{line}\n' for line in self._lines
            ).encode('utf-8')
        else:
            content = json.dumps(self._body).encode('utf-8')

        response = Response()
        response.status_code = self._status
        response.headers['Content-Type'] = self._media_type
        # Both are set: the body is read from '_content' when the
        # answer is decoded at once, and from 'raw' when it is
        # streamed, which is also what closing the response reaches
        # for.
        response._content = content  # pylint: disable=protected-access
        response.raw = BytesIO(content)

        return response


@pytest.fixture(name='make_client')
def fixture_make_client() -> Callable[..., Any]:
    """ Return a way to build a client over a scripted session. """

    def build(**overrides: Any) -> Any:
        """ Return the client and the session it sends through. """
        session = RecordingSession(**overrides)

        return Client(
            base_url=BASE_URL,
            token=CLIENT_CREDENTIAL,
            session=session
        ), session

    return build


class TestTheCommittedClient:
    def test_the_committed_client_matches_the_contract(self) -> None:
        generated = _generator.render(
            document=_generator.specification()
        )

        assert _generator.committed() == generated, DRIFT_MESSAGE

    def test_every_operation_has_a_method(self) -> None:
        # This is the whole point of generating it: an endpoint the
        # client cannot reach is a failing test rather than something
        # nobody notices until the command line client needs it.
        published = {
            operation['operationId']
            for verbs in _generator.specification()['paths'].values()
            for operation in verbs.values()
        }

        assert published
        assert published <= set(dir(Operations))

    def test_the_contract_names_its_operations_readably(self) -> None:
        # The identifier is what a method is named after, so the
        # default built from the method and the path would leave the
        # client with 'get_run_v1_runs__run_id__get' on it.
        published = [
            operation['operationId']
            for verbs in _generator.specification()['paths'].values()
            for operation in verbs.values()
        ]

        assert 'get_run' in published
        assert all('__' not in name for name in published)

    def test_no_two_operations_share_a_name(self) -> None:
        # They become methods on one class, so a collision would mean
        # one endpoint silently replacing another.
        published = [
            operation['operationId']
            for verbs in _generator.specification()['paths'].values()
            for operation in verbs.values()
        ]

        assert len(published) == len(set(published))


class TestSendingARequest:
    def test_a_path_without_parameters_is_addressed(
        self,
        make_client: Callable[..., Any]
    ) -> None:
        client, session = make_client(body=[])

        client.list_runs()

        assert session.calls[0]['url'] == f'{BASE_URL}/v1/runs'

    def test_a_path_parameter_is_filled_in(
        self,
        make_client: Callable[..., Any]
    ) -> None:
        client, session = make_client(body={'id': 'r-1'})

        client.get_run(run_id='r-1')

        assert session.calls[0]['url'] == f'{BASE_URL}/v1/runs/r-1'

    def test_a_path_parameter_cannot_add_a_path_segment(
        self,
        make_client: Callable[..., Any]
    ) -> None:
        # An identifier is a value. One that could introduce a segment
        # would let a caller address something they did not ask for.
        client, session = make_client()

        client.get_run(run_id='../jobs/j-1')

        assert session.calls[0]['url'] == (
            f'{BASE_URL}/v1/runs/..%2Fjobs%2Fj-1'
        )

    def test_a_trailing_slash_on_the_address_is_dropped(
        self
    ) -> None:
        # Built here rather than through the factory, because the
        # address is the thing under test.
        session = RecordingSession(body=[])
        client = Client(
            base_url=f'{BASE_URL}/',
            token=CLIENT_CREDENTIAL,
            session=session
        )

        client.list_runs()

        assert session.calls[0]['url'] == f'{BASE_URL}/v1/runs'

    def test_the_credential_is_presented_as_a_bearer_token(
        self,
        make_client: Callable[..., Any]
    ) -> None:
        client, session = make_client(body=[])

        client.list_runs()

        assert session.calls[0]['headers']['Authorization'] == (
            f'Bearer {CLIENT_CREDENTIAL}'
        )

    def test_the_credential_never_reaches_the_address(
        self,
        make_client: Callable[..., Any]
    ) -> None:
        # A token in a query string lands in access logs.
        client, session = make_client(body=[])

        client.list_runs()

        assert CLIENT_CREDENTIAL not in session.calls[0]['url']

    def test_a_request_does_not_wait_for_ever(
        self,
        make_client: Callable[..., Any]
    ) -> None:
        # A client waiting on a service that stopped answering looks
        # exactly like one doing careful work.
        client, session = make_client(body=[])

        client.list_runs()

        assert session.calls[0]['timeout'] > 0


class TestReadingAnAnswer:
    def test_a_successful_answer_is_returned_decoded(
        self,
        make_client: Callable[..., Any]
    ) -> None:
        client, _ = make_client(body={'id': 'r-1', 'calendar': 'events'})

        assert client.get_run(run_id='r-1') == {
            'id': 'r-1',
            'calendar': 'events'
        }

    def test_a_problem_document_becomes_a_failure(
        self,
        make_client: Callable[..., Any]
    ) -> None:
        client, _ = make_client(
            status=404,
            media_type=PROBLEM_MEDIA_TYPE,
            body={
                'title': 'Not found',
                'detail': 'There is no run with the ID "r-9".',
                'reference': 'ref 7c1d94'
            }
        )

        with pytest.raises(ApiProblem) as error:
            client.get_run(run_id='r-9')

        assert error.value.status == 404
        assert error.value.reference == 'ref 7c1d94'
        assert 'no run with the ID' in str(error.value)

    def test_a_failure_carrying_no_reason_still_reports_its_reference(
        self,
        make_client: Callable[..., Any]
    ) -> None:
        # A response of 500 or above never carries the reason, so the
        # reference is the one part a person can act on.
        client, _ = make_client(
            status=500,
            media_type=PROBLEM_MEDIA_TYPE,
            body={'title': 'Something went wrong', 'reference': 'ref 22a1'}
        )

        with pytest.raises(ApiProblem) as error:
            client.get_run(run_id='r-1')

        assert error.value.detail is None
        assert 'ref 22a1' in str(error.value)

    def test_a_failure_that_is_not_a_problem_document_still_raises(
        self,
        make_client: Callable[..., Any]
    ) -> None:
        # Something in front of the service does not answer in problem
        # documents, and a client that returned its body as an answer
        # would hand a caller a page of HTML as a run.
        client, _ = make_client(status=502, body='<html>Bad gateway</html>')

        with pytest.raises(ApiProblem) as error:
            client.get_run(run_id='r-1')

        assert error.value.status == 502


class TestFollowingAStream:
    def test_a_streaming_operation_yields_what_arrives(
        self,
        make_client: Callable[..., Any]
    ) -> None:
        client, _ = make_client(
            media_type='text/event-stream',
            lines=['event: progress', 'data: {"done": 1}', '']
        )

        received = list(client.stream_job_events(job_id='j-1'))

        assert received == [
            StreamEvent(kind='progress', payload={'done': 1})
        ]

    def test_a_streaming_operation_yields_records_not_lines(
        self,
        make_client: Callable[..., Any]
    ) -> None:
        # The other half answers this operation from the database and
        # has no wire syntax to hand on, so neither half does.
        client, _ = make_client(
            media_type='text/event-stream',
            lines=['event: progress', 'data: {"done": 1}', '']
        )

        received = list(client.stream_job_events(job_id='j-1'))

        assert not any(isinstance(event, str) for event in received)

    def test_a_streaming_operation_asks_for_a_stream(
        self,
        make_client: Callable[..., Any]
    ) -> None:
        client, session = make_client(
            media_type='text/event-stream',
            lines=['data: {}', '']
        )

        list(client.stream_job_events(job_id='j-1'))

        assert session.calls[0]['stream'] is True

    def test_a_stream_waits_longer_than_a_plain_request(
        self,
        make_client: Callable[..., Any]
    ) -> None:
        # A job can be quiet for minutes while it reads a calendar or
        # waits on Amplify.
        client, session = make_client(
            media_type='text/event-stream',
            lines=['data: {}', '']
        )

        list(client.stream_job_events(job_id='j-1'))
        stream_timeout = session.calls[0]['timeout']

        client, session = make_client(body=[])
        client.list_runs()

        assert stream_timeout > session.calls[0]['timeout']

    def test_a_failed_stream_becomes_a_failure(
        self,
        make_client: Callable[..., Any]
    ) -> None:
        client, _ = make_client(
            status=404,
            media_type=PROBLEM_MEDIA_TYPE,
            body={'title': 'Not found'}
        )

        with pytest.raises(ApiProblem):
            list(client.stream_job_events(job_id='no-such-job'))
