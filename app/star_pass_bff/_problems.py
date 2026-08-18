#!/usr/bin/env python3
""" Saying no in the shape the API says it.

    A caller of this service sees problem documents (RFC 9457)
    whichever side refused: the API's arrive already shaped and are
    passed through untouched, and the few this service raises itself
    are shaped here to match.  A front-end that refused in its own
    format would make every client handle two.

    Written here rather than imported from the API package, which
    would pull the core in with it.  Nothing in this process holds
    domain logic, and the import graph is where that stays true (D17).

    The refusal handled is the framework's base one rather than the
    web framework's subclass of it, because not every refusal here is
    raised by code in this package: the page mounted at the root
    answers a path it does not hold by raising the base, and a handler
    registered on the subclass alone would let that one out in a
    different shape.
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
