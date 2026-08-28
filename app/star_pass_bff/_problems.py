#!/usr/bin/env python3
""" Saying no in the shape the API says it.

    A caller sees problem documents (RFC 9457) whichever side refused.
    The API's are passed through untouched; the few this service
    raises are shaped here to match.

    The handler is registered on Starlette's base HTTPException rather
    than FastAPI's subclass: the page mounted at the root raises the
    base for a path it does not hold, and a handler on the subclass
    alone would let that out in a different shape.
"""

# Imports - Third-Party
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

# What a problem document is sent as.
PROBLEM_MEDIA_TYPE = 'application/problem+json'

# The type identifier of a refusal with nothing more specific to say,
# which is what a status code alone means.
PROBLEM_TYPE_BLANK = 'about:blank'


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
        """ Return one refusal as a document. """
        del request

        return JSONResponse(
            status_code=exc.status_code,
            media_type=PROBLEM_MEDIA_TYPE,
            content={
                'type': PROBLEM_TYPE_BLANK,
                'title': 'Request refused',
                'status': exc.status_code,
                'detail': exc.detail
            }
        )

    return None
