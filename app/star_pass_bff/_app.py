#!/usr/bin/env python3
""" Building the front-end service.

    A factory rather than a module-level application, as the API
    service has: the process starts when something asks for it, not
    when a module is imported, so a test can build one against its own
    settings.

    Three things happen here and nowhere else.  The connection to the
    API is opened once and closed once, so a proxy keeps its pooling.
    A browser without a session is given one on the way out.  And the
    page is served from this origin, the only one it can work from.

    Order matters where the page is mounted.  It answers everything
    under the root, so the proxy is included first and the mount takes
    what is left; the other order would serve a file, or a refusal,
    where an API call was meant to go.  The page's own paths are added
    between the two, or the mount would answer '/settings' with a 404
    before they were reached.
"""

# Imports - Python Standard Library
from contextlib import asynccontextmanager
from typing import AsyncIterator, Awaitable, Callable

# Imports - Third-Party
import httpx2
from fastapi import FastAPI, Request, Response, status
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

# Imports - Local
from . import _defaults
from ._configuration import check_configuration
from ._headers import add_security_headers
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
    """ Answer each of the page's own paths with the page.

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

        _send_the_slashed_form_to_this_one(api=api, path=path)


def _send_the_slashed_form_to_this_one(
        api: FastAPI,
        path: str
) -> None:
    """ Send a screen's trailing-slash address to the screen.

        A person who deletes the run identifier out of '/runs/<id>' is
        left holding '/runs/', which the mount at the root would answer
        with a refusal document as raw JSON.

        A router redirects a trailing slash to the path without one,
        but only where nothing else matches first, and the mount
        matches everything under the root.  This is that redirect,
        registered before the mount is reached, per screen rather than
        as a rule about slashes.

        Temporary rather than permanent: a permanent redirect is cached
        by the browser past any chance to change its mind.

        Args:
            api (FastAPI):
                The application to add it to.

            path (str):
                The screen's own path.

        Returns:
            None.
    """

    # The root's slashed form is the root, and a route answering
    # itself with a redirect to itself is a loop.
    if path == '/':
        return

    async def to_the_screen(request: Request) -> RedirectResponse:
        """ Answer with the address without the slash. """

        # Rebuilt from the request rather than from 'path', which
        # carries the parameter's name where a run identifier goes,
        # and through the address's own 'replace' rather than by
        # editing its text, so that whatever followed the path -- the
        # revision a preview was opened at, for one -- is still there
        # when the screen draws.
        return RedirectResponse(
            url=str(
                request.url.replace(path=request.url.path.rstrip('/'))
            ),
            status_code=status.HTTP_307_TEMPORARY_REDIRECT
        )

    api.add_api_route(
        path=f'{path}/',
        endpoint=to_the_screen,
        methods=['GET'],
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
        # contract, and this is one client of it.  A generated
        # specification of a proxy would describe the same operations
        # a second time and eventually differently.
        openapi_url=None,
        lifespan=_lifespan
    )

    add_problem_handlers(api=api)
    add_security_headers(api=api)
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
