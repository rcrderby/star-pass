#!/usr/bin/env python3
""" Saying no in the shape the API says it, and recording that it said so.

    A caller sees problem documents (RFC 9457) whichever side refused.
    The API's are passed through untouched; the few this service
    raises are shaped here to match, reference included, because a
    refusal a caller can quote is one that can be answered.

    Every refusal is logged against that reference.  This service
    enforces a session, a token, an origin and a body size, and a
    status code in an access log cannot say which of them answered.

    The handler is registered on Starlette's base HTTPException rather
    than FastAPI's subclass: the page mounted at the root raises the
    base for a path it does not hold, and a handler on the subclass
    alone would let that out in a different shape.
"""

# Imports - Python Standard Library
from uuid import uuid4

# Imports - Third-Party
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

# Imports - Local
from ._logging import get_logger

# What a problem document is sent as.
PROBLEM_MEDIA_TYPE = 'application/problem+json'

# The type identifier of a refusal with nothing more specific to say,
# which is what a status code alone means.
PROBLEM_TYPE_BLANK = 'about:blank'

# Module logger
logger = get_logger(__name__)


def add_problem_handlers(
        api: FastAPI
) -> None:
    """ Shape this service's own refusals as problem documents.

        Args:
            api (FastAPI):
                The application to add them to.

        Returns:
            None.
    """

    @api.exception_handler(HTTPException)
    async def _handle(
            request: Request,
            exc: HTTPException
    ) -> JSONResponse:
        """ Return one refusal as a document, and record it. """
        reference = uuid4().hex

        _log_refusal(
            request=request,
            status_code=exc.status_code,
            reference=reference,
            detail=str(exc.detail)
        )

        return JSONResponse(
            status_code=exc.status_code,
            media_type=PROBLEM_MEDIA_TYPE,
            content={
                'type': PROBLEM_TYPE_BLANK,
                'title': 'Request refused',
                'status': exc.status_code,
                'detail': exc.detail,
                'reference': reference
            }
        )

    return None


def _log_refusal(
        request: Request,
        status_code: int,
        reference: str,
        detail: str
) -> None:
    """ Record one refusal against the reference the caller was given.

        The method and path, and nothing else off the request: a query
        string is the caller's to write, and this line is not the place
        to find out what they put in it.

        Args:
            request (Request):
                What was refused.

            status_code (int):
                The status it was refused with.

            reference (str):
                What the caller may quote.

            detail (str):
                Why, as the caller was told.

        Returns:
            None.
    """

    message = (
        f'{status_code} Request refused [{reference}] '
        f'{request.method} {request.url.path}: {detail}'
    )

    logger.warning(message)

    return None
