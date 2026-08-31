#!/usr/bin/env python3
""" The service, assembled.

    A factory rather than a module level application object, so a test
    builds one per test and configuration is read when a server starts
    rather than when something imports this module.  The command line
    client imports the core the same way and does not acquire a server
    by doing so.

    The routes carry no domain logic.  They call the core and turn what
    it returns into a response, which keeps the command line client and
    this service able to do the same things.

    What happens when the service starts is here too, because it is
    part of what the application is: a job the last process was holding
    is ended, the one that runs new work is created and shut down with
    the service, and the retention policy is applied and goes on being
    applied.
"""

# Imports - Python Standard Library
import asyncio
from contextlib import asynccontextmanager, suppress
from typing import AsyncIterator

# Imports - Third-Party
from fastapi import FastAPI
from fastapi.routing import APIRoute

# Imports - Local
from star_pass._defaults import RETENTION_SWEEP_HOURS
from star_pass._helpers import require_env_vars
from star_pass._job_runner import JobRunner
from star_pass._logging import get_logger, send_server_logs_the_same_way
from star_pass._repository import JobRepository
from star_pass._retention import sweep
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
        longer exists.  They are ended before the service answers
        anything, so nobody reads a status that is about to change.

        Nothing is resumed.  An interrupted job is picked up again
        only when somebody asks, because a send that resumed itself
        would write to a live volunteer system from state rebuilt
        after a crash.

        Retention is applied here as well and then on an interval.
        Both halves are needed: a process can stand for a year, and a
        service restarted often would never reach an interval sweep.

        Args:
            api (FastAPI):
                The application starting up.

        Yields:
            None:
                While the service is running.
    """

    # The server has finished configuring its own logging by now, so
    # this is the moment its lines can be sent the same way as the
    # application's.  Done at import it would be undone as uvicorn
    # booted.
    send_server_logs_the_same_way()

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

    await _sweep_once()

    api.state.runner = JobRunner(connect=open_connection)
    # Held on the application beside the runner, for the same reason:
    # both outlive a request and both have to be stopped when the
    # service is, so whatever shuts them down has to be able to find
    # them.
    api.state.sweeping = asyncio.create_task(_sweeping())

    try:
        yield

    finally:
        api.state.sweeping.cancel()

        # Awaited rather than left cancelled, so the process does not
        # exit with a sweep half written.
        with suppress(asyncio.CancelledError):
            await api.state.sweeping

        # Waits, so a job in hand records how it ended rather than
        # being left for the next start to sweep.
        api.state.runner.shutdown()


async def _sweep_once() -> None:
    """ Apply the retention policy, and carry on whatever it did.

        On a thread, because the sweep opens a connection and works
        against SQLite: run on the event loop it would hold up every
        request for as long as it took.

        A sweep that fails is logged and nothing else happens.
        Retention falling behind is a thing to fix; it is not a reason
        to refuse to start, and it is not a reason for a service that
        has been running for months to stop.

        Args:
            None.

        Returns:
            None.
    """

    try:
        await asyncio.to_thread(lambda: in_database(sweep))

    except Exception:  # pylint: disable=broad-except
        logger.exception('The retention sweep failed.')

    return None


async def _sweeping() -> None:
    """ Apply the retention policy again, on the interval.

        The first one has already happened by the time this starts, so
        this waits before sweeping rather than after.

        Args:
            None.

        Returns:
            None.
    """

    while True:
        await asyncio.sleep(RETENTION_SWEEP_HOURS * 3600)
        await _sweep_once()


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
                anyone, or holds no credential for the services it
                calls.  Raised here rather than at the first request,
                so a deployment missing a value fails at startup
                instead of when someone tries to use it.

        Returns:
            api (FastAPI):
                The application, with its routes and error handling in
                place.
    """

    check_configuration()

    # The upstream credentials, checked beside the service's own and
    # through the core's gate rather than '_security', which decides
    # who is calling and holds nothing about who is being called.
    # Without this the service starts, answers, and fails inside a
    # job: a collect after minting a run, and a send partway through,
    # leaving it 'partly_sent'.
    require_env_vars(
        'AMPLIFY_TOKEN',
        'GCAL_TOKEN',

        # Beside the credentials because the failure is the same
        # shape: without these a collection reads a calendar this
        # deployment does not own, or none at all.  They carry no
        # default for that reason.
        'GCAL_EVENTS_CAL_ID',
        'GCAL_PRACTICES_CAL_ID'
    )

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
