#!/usr/bin/env python3
""" Building the front-end service.

    A factory rather than a module-level application, for the reason
    the API service has one: the process starts when something asks
    for it, not when a module is imported, so a test can build one
    against its own settings.

    Two things happen here that happen nowhere else: the connection to
    the API is opened once and closed once, because a client made per
    request would open a connection per request and lose the pooling
    that makes a proxy cheap; and a browser without a session is given
    one on the way out, so that the page a person loads can make a
    write without a round trip to fetch a token first.
"""

# Imports - Python Standard Library
from contextlib import asynccontextmanager
from typing import AsyncIterator, Awaitable, Callable

# Imports - Third-Party
import httpx2
from fastapi import FastAPI, Request, Response

# Imports - Local
from . import _defaults
from ._configuration import check_configuration
from ._problems import add_problem_handlers
from ._proxy import router as proxy_router
from ._sessions import session_of, started


@asynccontextmanager
async def _lifespan(
        api: FastAPI
) -> AsyncIterator[None]:
    """ Hold one connection pool to the API for the process's life.

        Args:
            api (FastAPI):
                The application being started.

        Yields:
            None:
                While the service is running.
    """

    async with httpx2.AsyncClient(
        base_url=_defaults.API_URL,
        timeout=_defaults.REQUEST_TIMEOUT_SECONDS
    ) as client:
        api.state.api = client

        yield


def create_app() -> FastAPI:
    """ Return the front-end service, ready to serve.

        Args:
            None.

        Raises:
            ConfigurationError:
                If the service was not given what it needs.

        Returns:
            api (FastAPI):
                The application.
    """

    check_configuration()

    api = FastAPI(
        title='star-pass front end',
        # Nothing here is a published surface: the API is the
        # contract, and this is one client of it (D1).  A generated
        # specification of a proxy would describe the same operations
        # a second time and eventually differently.
        openapi_url=None,
        lifespan=_lifespan
    )

    add_problem_handlers(api=api)
    api.include_router(proxy_router)

    @api.middleware('http')
    async def _give_a_session(
            request: Request,
            call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """ Give a browser without a session one, on the way out. """
        response = await call_next(request)

        if session_of(request=request) is None:
            started(response=response)

        return response

    return api
