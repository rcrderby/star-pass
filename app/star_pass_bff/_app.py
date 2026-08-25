#!/usr/bin/env python3
""" Building the front-end service.

    A factory rather than a module-level application, for the reason
    the API service has one: the process starts when something asks
    for it, not when a module is imported, so a test can build one
    against its own settings.

    Three things happen here that happen nowhere else: the connection
    to the API is opened once and closed once, because a client made
    per request would open a connection per request and lose the
    pooling that makes a proxy cheap; a browser without a session is
    given one on the way out, so that the page a person loads can make
    a write without a round trip to fetch a token first; and the page
    itself is served from this origin, because it is the only origin
    it can work from (D4, D18).

    Order matters where the page is mounted.  It answers everything
    under the root, so the proxy is included first and the mount takes
    what is left; the other order would serve a file, or a refusal,
    where an API call was meant to go.  The page's own paths (D28) are
    added between the two for the same reason: the mount would answer
    '/settings' with a 404 before they were reached.
"""

# Imports - Python Standard Library
from contextlib import asynccontextmanager
from typing import AsyncIterator, Awaitable, Callable

# Imports - Third-Party
import httpx2
from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

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


def _answer_the_screens_with_the_page(
        api: FastAPI
) -> None:
    """ Answer each of the page's own paths with the page (D28).

        The page routes itself, so every one of them draws a different
        screen in the browser and every one of them is the same file
        here.  Registered from the tuple rather than written out, so
        that adding a screen is one line in one place and the test
        holding the page's table to this list has one list to hold.

        Args:
            api (FastAPI):
                The application to add them to.

        Returns:
            None.
    """

    async def page() -> FileResponse:
        """ Answer with the page. """
        return FileResponse(_defaults.WEB_ROOT / _defaults.WEB_INDEX)

    for path in _defaults.SCREEN_PATHS:
        api.add_api_route(
            path=path,
            endpoint=page,
            methods=['GET'],
            # Nothing here is a published surface: this service
            # generates no specification at all, and a screen is not
            # an operation a client calls.
            include_in_schema=False
        )


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
    _answer_the_screens_with_the_page(api=api)
    api.mount(
        '/',
        StaticFiles(
            directory=_defaults.WEB_ROOT,
            html=True
        ),
        name='web'
    )

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
