#!/usr/bin/env python3
""" Reading a job, and following what it reports.

    A caller that asked for something long was given an identifier
    rather than made to wait.  This is where they come back with it:
    once, for where the job has got to, or held open, to be told as it
    happens.
"""

# Imports - Python Standard Library
import json
import sqlite3
from asyncio import sleep
from typing import Any, AsyncIterator, Dict, Optional

# Imports - Third-Party
from fastapi import APIRouter, HTTPException, Path, Request, status
from fastapi.responses import StreamingResponse

# Imports - Local
from star_pass._records import Job, JOB_STATUSES_FINISHED
from star_pass._repository import JobRepository
from star_pass._reporting import Reporter
from star_pass._resume import work_for
from star_pass_contract import (
    JobView,
    no_such_job,
    resumable,
    to_job_view
)
from . import _defaults
from ._problems import conflict, not_found
from ._security import (
    Principal,
    requires,
    SCOPE_RUNS_READ,
    SCOPE_RUNS_WRITE
)
from ._storage import in_database, in_the_database

# Constants
SSE_MEDIA_TYPE = 'text/event-stream'

# The header a reconnecting client sends, naming the last frame it
# saw.  Defined by the server-sent events specification, and sent by a
# browser without being asked.
LAST_EVENT_ID_HEADER = 'Last-Event-ID'

# The frame that ends a stream.  Named unlike any of the job's own
# events, which are named for the reporting method that produced them.
JOB_FINISHED_EVENT = 'job_finished'

# A comment frame.  It carries nothing and exists to be traffic, so
# that a connection nothing has been sent on is not mistaken for one
# nobody is using.
KEEP_ALIVE = ': keep-alive\n\n'

POLL_SECONDS = _defaults.JOB_EVENT_POLL_SECONDS
HEARTBEAT_SECONDS = _defaults.JOB_EVENT_HEARTBEAT_SECONDS

router = APIRouter(tags=[_defaults.API_TAG_JOBS])


def missing_job(
        job_id: str
) -> HTTPException:
    """ Return the failure for a job that is not there.

        Args:
            job_id (str):
                What the caller asked for.

        Returns:
            error (HTTPException):
                A 404 naming the job.
    """

    return not_found(detail=no_such_job(job_id=job_id))


def _find(
        connection: sqlite3.Connection,
        job_id: str
) -> Optional[Job]:
    """ Read one job.

        Args:
            connection (sqlite3.Connection):
                Connection to read on.

            job_id (str):
                Job to read.

        Returns:
            job (Job | None):
                The job, or None when there is no such job.
    """

    return JobRepository(connection=connection).get(job_id=job_id)


@router.get(
    '/jobs/{job_id}',
    summary='Report where a job has got to',
    description=(
        'Answers for a job whether it is queued, running or over. A '
        'caller watching one polls this, or reads the event stream '
        'for the same job to be told as it happens.'
    ),
    response_model=JobView
)
async def get_job(
        job_id: str = Path(
            description='Identifier the job was created with.'
        ),
        principal: Principal = requires(SCOPE_RUNS_READ)
) -> JobView:
    """ Return one job.

        Args:
            job_id (str):
                Identifier of the job to read.

            principal (Principal):
                The authenticated caller, which the dependency supplies
                after checking the scope.

        Raises:
            HTTPException:
                404 when there is no such job.  Raised here rather than
                left to the repository, which reports a value it cannot
                use and a missing job the same way; only this endpoint
                knows it was asked for one by identifier.

        Returns:
            job (JobView):
                The job as a caller sees it.
    """

    del principal

    job = await in_the_database(
        lambda connection: _find(
            connection=connection,
            job_id=job_id
        )
    )

    if job is None:
        raise missing_job(job_id=job_id)

    return to_job_view(job=job)


def _frame(
        event: str,
        data: Dict[str, Any],
        identifier: Optional[int] = None
) -> str:
    """ Return one server-sent event.

        Args:
            event (str):
                What happened, which is what a client listens for.

            data (Dict[str, Any]):
                What the event carries.

            identifier (int, optional):
                The event's identifier.  Defaults to None, for a frame
                that is not one of the job's own events and so is not
                somewhere a reader can resume from.

        Returns:
            frame (str):
                The event, ready to send.
    """

    lines = []

    if identifier is not None:
        lines.append(f'id: {identifier}')

    lines.append(f'event: {event}')
    lines.append(f'data: {json.dumps(data, sort_keys=True)}')

    # A blank line ends a frame, so the last one is what makes it
    # arrive rather than sit in a buffer waiting for the next.
    return '\n'.join(lines) + '\n\n'


def _resume_from(
        request: Request
) -> int:
    """ Return the event a reconnecting client already has.

        Args:
            request (Request):
                The request, which carries 'Last-Event-ID' when a
                client is reconnecting.  Browsers send it themselves.

        Returns:
            after (int):
                The last event the client saw, or 0 when it is not
                resuming or said something that is not an identifier.
    """

    try:
        return int(request.headers.get(LAST_EVENT_ID_HEADER, 0))

    except ValueError:
        return 0


async def _events(
        request: Request,
        job_id: str,
        after: int
) -> AsyncIterator[str]:
    """ Send what a job reports, until it is over.

        **The status is read before the events, and that order is the
        whole correctness of this loop.**  Read the other way round, an
        event written between the two reads would be missed: the events
        read would not hold it, and the status read afterwards would
        say the job was over and end the stream.  Reading the status
        first means anything written before that moment is in the
        events that follow it, and a finished job writes nothing more.

        Args:
            request (Request):
                The request, so the loop stops when the client goes.

            job_id (str):
                Job to follow.

            after (int):
                Send only events later than this identifier.

        Yields:
            frame (str):
                One server-sent event, or a comment keeping the
                connection open.
    """

    silent_for = 0.0

    while not await request.is_disconnected():
        job = await in_the_database(
            lambda connection: _find(
                connection=connection,
                job_id=job_id
            )
        )

        if job is None:
            # Deleted while it was being watched.  Nothing more to say
            # about it, and nothing that would be true to send.
            return

        reported = await in_the_database(
            lambda connection: JobRepository(
                connection=connection
            ).events(job_id=job_id, after=after)
        )

        for event in reported:
            after = event.id
            yield _frame(
                event=event.kind,
                data=event.payload,
                identifier=event.id
            )

        if job.status in JOB_STATUSES_FINISHED:
            yield _frame(
                event=JOB_FINISHED_EVENT,
                data={
                    'id': job.id,
                    'status': job.status,
                    'detail': job.detail
                }
            )
            return

        silent_for = 0.0 if reported else silent_for + POLL_SECONDS

        if silent_for >= HEARTBEAT_SECONDS:
            silent_for = 0.0
            yield KEEP_ALIVE

        await sleep(POLL_SECONDS)


@router.get(
    '/jobs/{job_id}/events',
    summary='Follow what a job reports, as it reports it',
    description=(
        'A server-sent event stream. Each frame is named for what the '
        'job reported and carries what that report held. The stream '
        'ends with a "job_finished" frame when the job is over.\n\n'
        'It is reattachable: a client that reconnects sends the '
        'identifier of the last frame it saw in "Last-Event-ID", and '
        'is given what it missed rather than what it already has. A '
        'browser sends that header itself.'
    ),
    response_class=StreamingResponse,
    responses={
        200: {
            'description': 'The job\'s events, as they happen.',
            'content': {SSE_MEDIA_TYPE: {}}
        }
    }
)
async def stream_job_events(
        request: Request,
        job_id: str = Path(
            description='Identifier the job was created with.'
        ),
        principal: Principal = requires(SCOPE_RUNS_READ)
) -> StreamingResponse:
    """ Stream one job's events until it is over.

        Args:
            request (Request):
                The request, which carries any 'Last-Event-ID' and
                tells the stream when the client has gone.

            job_id (str):
                Identifier of the job to follow.

            principal (Principal):
                The authenticated caller, which the dependency supplies
                after checking the scope.

        Raises:
            HTTPException:
                404 when there is no such job.  Checked before the
                stream opens, so a mistyped identifier is an error a
                client can read rather than a stream that says nothing.

        Returns:
            response (StreamingResponse):
                The event stream.
    """

    del principal

    job = await in_the_database(
        lambda connection: _find(
            connection=connection,
            job_id=job_id
        )
    )

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=no_such_job(job_id=job_id)
        )

    return StreamingResponse(
        _events(
            request=request,
            job_id=job_id,
            after=_resume_from(request=request)
        ),
        media_type=SSE_MEDIA_TYPE,
        # Nothing between here and the reader may hold frames back to
        # send them together, which is what caching one would do.
        headers={'Cache-Control': 'no-cache'}
    )


@router.post(
    '/jobs/{job_id}/resume',
    status_code=status.HTTP_202_ACCEPTED,
    summary='Run an interrupted job again',
    description=(
        'Queues an interrupted job to be run again, and hands it back '
        'to a worker. A job left queued or running when the service '
        'stopped is marked interrupted at startup and never resumed on '
        'its own: a send that resumed itself would write to a '
        'live volunteer system from state rebuilt after a crash.\n\n'
        'What runs is the ordinary work, pointed at a job that already '
        'exists. A resumed send reads every opportunity immediately '
        'before writing to it and creates exactly the rows the '
        'interrupted attempt did not, so resuming needs no record of '
        'how far that attempt got -- the question is answered by '
        'Amplify rather than by the job.\n\n'
        'The job keeps its identifier and loses what the interrupted '
        'attempt recorded about itself: when it began, when it '
        'stopped, and why. Those described an attempt that is being '
        'made again, and leaving them would describe two runs of it at '
        'once.\n\n'
        'Refused for a job in any other state -- which is what stops a '
        'second click starting a second worker -- and while another '
        'job is working on the same run.'
    ),
    response_model=JobView
)
async def resume_job(
        request: Request,
        job_id: str = Path(
            description='Identifier of the job to run again.'
        ),
        principal: Principal = requires(SCOPE_RUNS_WRITE)
) -> JobView:
    """ Queue an interrupted job again and hand it to the runner.

        Args:
            request (Request):
                The request, which carries the runner that jobs are
                given to.

            job_id (str):
                Identifier of the job to resume.

            principal (Principal):
                The authenticated caller, which the dependency supplies
                after checking the scope.

        Raises:
            HTTPException:
                404 when there is no such job, 409 when it is not one
                that may be resumed.

        Returns:
            job (JobView):
                The job, queued again.
    """

    found = await in_the_database(
        lambda connection: resumable(
            connection=connection,
            job_id=job_id
        )
    )

    if found is None:
        raise missing_job(job_id=job_id)

    job, refusal = found

    if refusal is not None:
        raise conflict(detail=refusal)

    await in_the_database(
        lambda connection: JobRepository(connection=connection).requeue(
            job_id=job.id
        )
    )

    work = work_for(job=job, principal_id=principal.id)

    def resumed(reporter: Reporter) -> None:
        """ Run the work on a connection belonging to the job's thread. """
        in_database(
            lambda connection: work(connection, reporter)
        )

    request.app.state.runner.submit(job_id=job.id, work=resumed)

    return to_job_view(
        job=await in_the_database(
            lambda connection: _find(connection=connection, job_id=job.id)
        )
    )
