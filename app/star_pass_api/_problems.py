#!/usr/bin/env python3
""" Every error the service returns, as a problem document.

    One response shape for every failure (RFC 9457): a media type of
    'application/problem+json' and a body carrying 'type', 'title',
    'status' and 'detail', plus a 'reference' a caller can quote.

    What a caller is told depends on whose problem it is.  A request
    that was wrong gets the reason, because the caller is the one who
    can fix it.  A failure inside the service gets a sentence and the
    reference; the reason goes to the log under that same reference,
    because an internal failure can carry a credential, a volunteer's
    name, or an upstream body that holds either.  The reference is what
    joins the two without putting the second in the first.

    The core's three exceptions arrive here and become three statuses,
    which is the whole translation between a domain that raises and a
    protocol that returns.  Nothing above this module builds an error
    response, so a new endpoint cannot invent a different shape.
"""

# Imports - Python Standard Library
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any, Dict, Optional
from uuid import uuid4

# Imports - Third-Party
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

# Imports - Local
from star_pass._exceptions import (
    ConfigurationError,
    StarPassError,
    UpstreamError,
    ValidationError
)
from star_pass._logging import get_logger

# Constants
PROBLEM_MEDIA_TYPE = 'application/problem+json'

# Problem type identifiers.  A URN rather than a URL: RFC 9457 wants a
# URI that identifies the problem type, and a URL would promise a page
# to serve.  'about:blank' is the value the specification reserves for
# a problem with nothing to say beyond its status code, and a title
# that repeats the status phrase is what it asks for alongside it.
PROBLEM_TYPE_BLANK = 'about:blank'
PROBLEM_TYPE_PREFIX = 'urn:star-pass:problem'
PROBLEM_TYPE_CONFIGURATION = f'{PROBLEM_TYPE_PREFIX}:configuration'
PROBLEM_TYPE_VALIDATION = f'{PROBLEM_TYPE_PREFIX}:validation'
PROBLEM_TYPE_UPSTREAM = f'{PROBLEM_TYPE_PREFIX}:upstream'
PROBLEM_TYPE_UNEXPECTED = f'{PROBLEM_TYPE_PREFIX}:unexpected'

# What a caller is told when the reason is not theirs to see.  The
# reference in the same document is how the reason is found.
INTERNAL_DETAIL = (
    'The service could not complete the request. Quote the reference '
    'when reporting it.'
)


@dataclass(frozen=True)
class ProblemKind:
    """ What kind of problem occurred, independent of the occasion.

        The status, the type identifier and the title are one fact
        about a category of failure; only the detail differs between
        two occurrences of it.

        Attributes:
            status_code (int):
                HTTP status the response carries.

            problem_type (str):
                URI identifying the problem type.

            title (str):
                Short summary of the type, stable across occurrences.
    """

    status_code: int
    problem_type: str
    title: str


# The kinds that are not tied to one of the core's exceptions.
VALIDATION_KIND = ProblemKind(
    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
    problem_type=PROBLEM_TYPE_VALIDATION,
    title='Unprocessable request'
)
UNEXPECTED_KIND = ProblemKind(
    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    problem_type=PROBLEM_TYPE_UNEXPECTED,
    title='Internal server error'
)

# How each of the core's exceptions is answered.  A configuration fault
# is the deployment's, so it is a server error however it was reached;
# supplied data that cannot be used is the caller's; an upstream that
# failed or answered unusably is a bad gateway.
#
# A route that means "no such thing" raises its own 404 rather than
# leaning on the validation entry here: the repository raises the same
# ValidationError for a value that is malformed and for one that names
# nothing, and only the route knows which it asked for.
CORE_EXCEPTION_PROBLEMS = {
    ConfigurationError: ProblemKind(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        problem_type=PROBLEM_TYPE_CONFIGURATION,
        title='Service configuration error'
    ),
    ValidationError: VALIDATION_KIND,
    UpstreamError: ProblemKind(
        status_code=status.HTTP_502_BAD_GATEWAY,
        problem_type=PROBLEM_TYPE_UPSTREAM,
        title='Upstream service error'
    )
}

# Module logger
logger = get_logger(__name__)


def problem_document(
        *,
        status_code: int,
        title: str,
        detail: str,
        problem_type: str = PROBLEM_TYPE_BLANK,
        extra: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """ Build a problem document.

        Args:
            status_code (int):
                HTTP status the response carries.

            title (str):
                Short, stable summary of the problem type.  It does not
                change from one occurrence to the next; 'detail' does.

            detail (str):
                What went wrong this time, written for the caller.

            problem_type (str, optional):
                URI identifying the problem type.  Defaults to
                'about:blank', for a problem that is only its status.

            extra (Dict[str, Any], optional):
                Further members to include.  Defaults to None.

        Returns:
            document (Dict[str, Any]):
                The document's members, reference included.
    """

    document: Dict[str, Any] = {
        'type': problem_type,
        'title': title,
        'status': status_code,
        'detail': detail,
        'reference': uuid4().hex
    }
    document.update(extra or {})

    return document


def problem_response(
        document: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None
) -> JSONResponse:
    """ Return a problem document as a response.

        Args:
            document (Dict[str, Any]):
                The document to send.

            headers (Dict[str, str], optional):
                Headers the status requires.  Defaults to None.  A 401
                has to carry a challenge naming the scheme it accepts,
                and the body cannot do that.

        Returns:
            response (JSONResponse):
                The document, as 'application/problem+json'.
    """

    return JSONResponse(
        status_code=document['status'],
        content=document,
        media_type=PROBLEM_MEDIA_TYPE,
        headers=headers
    )


def _log_problem(
        request: Request,
        document: Dict[str, Any],
        reason: str
) -> None:
    """ Record a problem against the reference the caller was given.

        The reason is logged whether or not it was returned, so that a
        response saying only "quote the reference" can still be
        answered.

        Args:
            request (Request):
                The request that failed.

            document (Dict[str, Any]):
                The problem document that was returned.

            reason (str):
                What actually went wrong, including what was withheld.

        Returns:
            None.
    """

    message = (
        f'{document["status"]} {document["title"]} '
        f'[{document["reference"]}] '
        f'{request.method} {request.url.path}: {reason}'
    )

    if document['status'] >= status.HTTP_500_INTERNAL_SERVER_ERROR:
        logger.error(message)
    else:
        logger.warning(message)

    return None


def _answer(
        request: Request,
        kind: ProblemKind,
        reason: str,
        *,
        extra: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
) -> JSONResponse:
    """ Return a problem document and log the reason behind it.

        A server error is answered with a fixed sentence rather than
        'reason', because the reason describes the inside of the
        service.  A client error is answered with the reason itself.

        Args:
            request (Request):
                The request that failed.

            kind (ProblemKind):
                What kind of problem it is.

            reason (str):
                What went wrong, as the service knows it.

            extra (Dict[str, Any], optional):
                Further members to include.  Defaults to None.

            headers (Dict[str, str], optional):
                Headers the status requires.  Defaults to None.

        Returns:
            response (JSONResponse):
                The problem document.
    """

    internal = kind.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR

    document = problem_document(
        status_code=kind.status_code,
        title=kind.title,
        detail=INTERNAL_DETAIL if internal else reason,
        problem_type=kind.problem_type,
        extra=extra
    )
    _log_problem(
        request=request,
        document=document,
        reason=reason
    )

    return problem_response(
        document=document,
        headers=headers
    )


async def _handle_core_error(
        request: Request,
        exc: StarPassError
) -> JSONResponse:
    """ Answer one of the core's exceptions.

        Args:
            request (Request):
                The request that failed.

            exc (StarPassError):
                The exception the core raised.

        Returns:
            response (JSONResponse):
                The problem document.
    """

    return _answer(
        request=request,
        kind=CORE_EXCEPTION_PROBLEMS.get(type(exc), UNEXPECTED_KIND),
        reason=str(exc)
    )


async def _handle_http_error(
        request: Request,
        exc: HTTPException
) -> JSONResponse:
    """ Answer a status raised by a route or by the framework.

        Args:
            request (Request):
                The request that failed.

            exc (HTTPException):
                The status and detail that were raised.

        Returns:
            response (JSONResponse):
                The problem document.
    """

    return _answer(
        request=request,
        kind=ProblemKind(
            status_code=exc.status_code,
            problem_type=PROBLEM_TYPE_BLANK,
            title=_status_phrase(status_code=exc.status_code)
        ),
        reason=str(exc.detail),
        headers=getattr(exc, 'headers', None)
    )


async def _handle_request_validation_error(
        request: Request,
        exc: RequestValidationError
) -> JSONResponse:
    """ Answer a request that did not match what the route declared.

        The per-field errors are kept, under an 'errors' member: they
        describe the request the caller sent, so they are the caller's
        to read, and dropping them would leave a validation failure
        saying only that something was wrong.

        Args:
            request (Request):
                The request that failed.

            exc (RequestValidationError):
                What did not validate.

        Returns:
            response (JSONResponse):
                The problem document.
    """

    errors = [
        {
            'location': [str(part) for part in error.get('loc', ())],
            'message': error.get('msg', ''),
            'type': error.get('type', '')
        }
        for error in exc.errors()
    ]

    return _answer(
        request=request,
        kind=VALIDATION_KIND,
        reason='The request did not match the endpoint.',
        extra={'errors': errors}
    )


async def _handle_unexpected_error(
        request: Request,
        exc: Exception
) -> JSONResponse:
    """ Answer anything that reached here uncaught.

        A defect rather than a condition: the core raises typed
        exceptions for everything it expects, so anything else is a bug
        and its message was never written for a caller to read.

        Args:
            request (Request):
                The request that failed.

            exc (Exception):
                The exception that escaped.

        Returns:
            response (JSONResponse):
                The problem document.
    """

    return _answer(
        request=request,
        kind=UNEXPECTED_KIND,
        reason=f'{type(exc).__name__}: {exc}'
    )


def _status_phrase(
        status_code: int
) -> str:
    """ Return the reason phrase for a status code.

        RFC 9457 asks that a problem with no type of its own be titled
        with its status phrase, which is what a bare status means.

        Args:
            status_code (int):
                The HTTP status.

        Returns:
            phrase (str):
                The phrase, or the code as text when it has no name.
    """

    try:
        return HTTPStatus(status_code).phrase

    except ValueError:
        return str(status_code)


def add_problem_handlers(
        api: FastAPI
) -> None:
    """ Route every failure through a problem document.

        Registered for the core's base exception rather than for each
        subclass, so a subclass added later is answered rather than
        escaping as an unexpected error.

        Args:
            api (FastAPI):
                The application to register the handlers on.

        Returns:
            None.
    """

    api.add_exception_handler(StarPassError, _handle_core_error)
    api.add_exception_handler(HTTPException, _handle_http_error)
    api.add_exception_handler(
        RequestValidationError,
        _handle_request_validation_error
    )
    api.add_exception_handler(Exception, _handle_unexpected_error)

    return None
