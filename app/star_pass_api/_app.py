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

    What happens when the service starts is here too, because it is
    part of what the application is: a job the last process was holding
    is ended, and the one that runs new work is created and shut down
    with the service.
"""

# Imports - Python Standard Library
from contextlib import asynccontextmanager
from typing import AsyncIterator

# Imports - Third-Party
from fastapi import FastAPI
from fastapi.routing import APIRoute

# Imports - Local
from star_pass._job_runner import JobRunner
from star_pass._logging import get_logger
from star_pass._repository import JobRepository
from . import _defaults
from ._configuration import router as config_router
from ._credentials import router as credentials_router
from ._editing import router as editing_router
from ._health import router as health_router
from ._jobs import router as jobs_router
from ._problems import add_problem_handlers, PROBLEM_MEDIA_TYPE
from ._revisions import router as revisions_router
from ._runs import router as runs_router
from ._sending import router as sending_router
from ._security import check_configuration
from ._unmatched import router as unmatched_router
from ._storage import in_database, open_connection
from ._version import router as version_router

# Module logger
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(
        api: FastAPI
) -> AsyncIterator[None]:
    """ End what the last process was holding, and run what comes next.

        A job left queued or running belongs to a process that no
        longer exists.  Ending them here is what keeps a restart from
        leaving a caller watching something nothing is doing, and it
        happens before the service answers anything, so nobody reads a
        status that is about to change (D10).

        Nothing is resumed.  A job that was interrupted is picked up
        again only when somebody asks, because a send that resumed
        itself would write to a live volunteer system from state
        rebuilt after a crash.

        Args:
            api (FastAPI):
                The application starting up.

        Yields:
            None:
                While the service is running.
    """

    interrupted = in_database(
        lambda connection: JobRepository(
            connection=connection
        ).interrupt_unfinished()
    )

    if interrupted:
        message = (
            f'Ended {interrupted} job(s) the previous process was '
            'holding. Resume them from the interface.'
        )
        logger.warning(message)

    api.state.runner = JobRunner(connect=open_connection)

    try:
        yield

    finally:
        # Waits, so a job in hand records how it ended rather than
        # being left for the next start to sweep.
        api.state.runner.shutdown()


def operation_id(
        route: APIRoute
) -> str:
    """ Return the name an operation is published under.

        The name of the function serving the route, rather than the
        default built from its method and path.  The identifier is
        what a generated client names its methods after, so 'get_run'
        reads as a method and
        'get_run_v1_runs__run_id__get' does not.

        Args:
            route (APIRoute):
                The route being published.

        Returns:
            identifier (str):
                What to call the operation in the specification.
    """

    return route.name


def create_app() -> FastAPI:
    """ Build the service.

        Args:
            None.

        Raises:
            ConfigurationError:
                If the service is not configured to authenticate
                anyone.  Raised here rather than at the first request,
                so a deployment missing its token fails at startup
                instead of when someone tries to use it.

        Returns:
            api (FastAPI):
                The application, with its routes and error handling in
                place.
    """

    check_configuration()

    api = FastAPI(
        lifespan=lifespan,
        title=_defaults.API_TITLE,
        version=_defaults.API_VERSION,
        summary=_defaults.API_SUMMARY,
        description=_defaults.API_DESCRIPTION,
        docs_url=_defaults.API_DOCS_PATH,
        redoc_url=_defaults.API_REDOC_PATH,
        openapi_url=_defaults.API_OPENAPI_PATH,
        generate_unique_id_function=operation_id,
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

    for router in (
        health_router,
        version_router,
        config_router,
        credentials_router,
        unmatched_router,
        runs_router,
        revisions_router,
        editing_router,
        sending_router,
        jobs_router
    ):
        api.include_router(
            router,
            prefix=_defaults.API_VERSION_PREFIX
        )

    return api
