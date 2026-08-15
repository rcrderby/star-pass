#!/usr/bin/env python3
""" The service, assembled.

    A factory rather than a module level application object, so that a
    test builds one per test and configuration is read when a server
    starts rather than when something imports this module.  Importing a
    module should not open sockets or read the environment; the CLI
    imports the core the same way and must not acquire a server by
    doing so (D2).

    The routes carry no domain logic.  They call the core and turn what
    it returns into a response, which is what keeps the command line
    client and this service able to do the same things (D1).
"""

# Imports - Third-Party
from fastapi import FastAPI

# Imports - Local
from . import _defaults
from ._health import router as health_router
from ._problems import add_problem_handlers, PROBLEM_MEDIA_TYPE


def create_app() -> FastAPI:
    """ Build the service.

        Args:
            None.

        Returns:
            api (FastAPI):
                The application, with its routes and error handling in
                place.
    """

    api = FastAPI(
        title=_defaults.API_TITLE,
        version=_defaults.API_VERSION,
        summary=_defaults.API_SUMMARY,
        description=_defaults.API_DESCRIPTION,
        docs_url=_defaults.API_DOCS_PATH,
        redoc_url=_defaults.API_REDOC_PATH,
        openapi_url=_defaults.API_OPENAPI_PATH,
        # Every failure is a problem document, so the generated
        # specification says so once here rather than on each route.
        responses={
            'default': {
                'description': 'A problem document (RFC 9457).',
                'content': {PROBLEM_MEDIA_TYPE: {}}
            }
        }
    )

    add_problem_handlers(api=api)

    api.include_router(
        health_router,
        prefix=_defaults.API_VERSION_PREFIX
    )

    return api
