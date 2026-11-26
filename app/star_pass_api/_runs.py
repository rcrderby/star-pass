#!/usr/bin/env python3
""" Reading runs, collecting them, and what one would send.

    The first callers of the repository layer's run side: the list a
    person opens the tool on, the run itself with everything the
    review screen reads at once, what the window held and the run left
    out, what sending it would create, and the two writes that fill a
    run from a calendar.  The revisions its events have been through
    are their own subject and their own module.

    No domain logic lives here, and no shaping either.  A route
    decides what to read and what a failure looks like; the
    contract package turns
    what was read into what a caller is shown, because the command
    line client shows the same answers from the same database and the
    two must not drift.
"""

# Imports - Python Standard Library
import sqlite3
from typing import List, Optional, Tuple

# Imports - Third-Party
from fastapi import (
    APIRouter,
    HTTPException,
    Path,
    Request,
    Response,
    status
)
from starlette.concurrency import run_in_threadpool

# Imports - Local
from star_pass._collect import collect
from star_pass._database import transaction
from star_pass._defaults import GCAL_CALENDARS
from star_pass._gcal_time import resolve_window
from star_pass._opportunities import shifts_in_amplify
from star_pass._reading import (
    changes_in_current,
    read_run_detail,
    read_run_for_send,
    read_run_history,
    read_run_uncollected
)
from star_pass._records import (
    JOB_KIND_COLLECT,
    JOB_KIND_RECOLLECT,
    Run,
    RUN_STATUS_COLLECTING
)
from star_pass._reporting import Reporter
from star_pass._repository import JobRepository, RunRepository
from star_pass_contract import (
    CollectRequest,
    JobView,
    no_such_run,
    RecollectRequest,
    PreviewView,
    RunDetailView,
    RunView,
    to_detail_view,
    to_job_view,
    to_preview_view,
    to_run_view,
    to_uncollected_views,
    UncollectedGroupView,
    why_not_delete,
    why_not_recollect,
    WriteRefusals
)
from . import _defaults
from ._security import (
    Principal,
    requires,
    SCOPE_RUNS_READ,
    SCOPE_RUNS_WRITE
)
from ._problems import conflict, not_found, unprocessable
from ._storage import in_database, in_the_database

router = APIRouter(tags=[_defaults.API_TAG_RUNS])


def missing_run(
        run_id: str
) -> HTTPException:
    """ Return the failure for a run that is not there.

        Args:
            run_id (str):
                What the caller asked for.

        Returns:
            error (HTTPException):
                A 404 naming the run.
    """

    return not_found(detail=no_such_run(run_id=run_id))


# How this half says no to a keyed write.  A status code belongs to
# the transport, so the shared sequence is given these rather than
# choosing them.
REFUSALS = WriteRefusals(
    missing=missing_run,
    conflict=conflict,
    refuse=unprocessable
)


@router.get(
    '/runs',
    summary='List the runs, newest first',
    description=(
        'All runs, newest to oldest, including runs being collected. '
        'Each run includes its current revision\'s counts and the job '
        'working on it, if any.'
    ),
    response_model=List[RunView]
)
async def list_runs(
        principal: Principal = requires(SCOPE_RUNS_READ)
) -> List[RunView]:
    """ Return every run.

        Args:
            principal (Principal):
                The authenticated caller, which the dependency supplies
                after checking the scope.

        Returns:
            runs (List[RunView]):
                Every run, newest first.
    """

    del principal

    runs = await in_the_database(
        lambda connection: RunRepository(
            connection=connection
        ).list_all()
    )

    return [to_run_view(run=run) for run in runs]


@router.get(
    '/runs/{run_id}',
    summary='Read one run in full',
    description=(
        'The run, the events of its current revision, the Amplify '
        'opportunities labelling them, and the log of everything done '
        'to it. Read together because a screen showing one shows all '
        'of them, and separate reads could disagree.\n\n'
        'Each event carries what its stored row does not say: how long '
        'the shift is, the maximum that shortened it, whether an '
        'earlier event would create the same shift, and whether it '
        'blocks the send.'
    ),
    response_model=RunDetailView
)
async def get_run(
        run_id: str = Path(
            description='Identifier the run was created with.'
        ),
        principal: Principal = requires(SCOPE_RUNS_READ)
) -> RunDetailView:
    """ Return one run and everything shown beside it.

        Args:
            run_id (str):
                Identifier of the run to read.

            principal (Principal):
                The authenticated caller, which the dependency supplies
                after checking the scope.

        Raises:
            HTTPException:
                404 when there is no such run.

        Returns:
            run (RunDetailView):
                The run in full.
    """

    del principal

    detail = await in_the_database(
        lambda connection: read_run_detail(
            connection=connection,
            run_id=run_id
        )
    )

    if detail is None:
        raise missing_run(run_id=run_id)

    return to_detail_view(detail=detail)


@router.delete(
    '/runs/{run_id}',
    status_code=status.HTTP_204_NO_CONTENT,
    summary='Delete a run that has not sent shifts',
    description=(
        'Deletes the run, and removes its revisions, events, '
        'opportunities, change log, jobs, and uncollected events. Any '
        'unmatched titles from the run remain in the unmatched title '
        'log.\n\nYou may not delete a run that is collecting events, '
        'is sending shifts to Amplify, or already sent shifts to '
        'Amplify.'
    ),
    response_class=Response
)
async def delete_run(
        run_id: str = Path(
            description='Identifier the run was created with.'
        ),
        principal: Principal = requires(SCOPE_RUNS_WRITE)
) -> Response:
    """ Delete a run, if it is one that may go.

        Args:
            run_id (str):
                Identifier of the run to delete.

            principal (Principal):
                The authenticated caller, which the dependency supplies
                after checking the scope.

        Raises:
            HTTPException:
                404 when there is no such run, 409 when the run is not
                one that may be deleted.

        Returns:
            response (Response):
                Nothing, with a 204.
    """

    del principal

    run = await in_the_database(
        lambda connection: RunRepository(connection=connection).get(
            run_id=run_id
        )
    )

    if run is None:
        raise missing_run(run_id=run_id)

    refusal = why_not_delete(run=run)

    if refusal is not None:
        raise conflict(detail=refusal)

    await in_the_database(
        lambda connection: RunRepository(connection=connection).delete(
            run_id=run_id
        )
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    '/runs/{run_id}/uncollected',
    summary=(
        'List the events in a run\'s date range that the run did not '
        'collect'
    ),
    description=(
        'Events in the run\'s date range that are not in the run, '
        'grouped by reason: outside the calendar search, excluded by '
        'title, all-day event, or untitled. Earliest first within each '
        'group. Only reasons with events are included.\n\nAnswered '
        'from the data stored at collection, not from a new League '
        'Calendar read. To update it, collect the run again.\n\nYou '
        'may only add events outside the calendar search (`search`) to '
        'the run.'
    ),
    response_model=List[UncollectedGroupView]
)
async def list_uncollected(
        run_id: str = Path(
            description='Identifier the run was created with.'
        ),
        principal: Principal = requires(SCOPE_RUNS_READ)
) -> List[UncollectedGroupView]:
    """ Return what a run's window held and the run left out.

        Args:
            run_id (str):
                Identifier of the run to read.

            principal (Principal):
                The authenticated caller, which the dependency supplies
                after checking the scope.

        Raises:
            HTTPException:
                404 when there is no such run.  A run whose window
                held nothing else answers with an empty list, which is
                a different fact and reads differently.

        Returns:
            groups (List[UncollectedGroupView]):
                One group per reason anything was left out for.
    """

    del principal

    found = await in_the_database(
        lambda connection: read_run_uncollected(
            connection=connection,
            run_id=run_id
        )
    )

    if found is None:
        raise missing_run(run_id=run_id)

    return to_uncollected_views(
        uncollected=found.uncollected,
        in_revision=found.in_revision
    )


@router.get(
    '/runs/{run_id}/preview',
    summary='Report what sending this run would create',
    description=(
        'Shifts a send would create in Amplify for each opportunity, '
        'the shifts already in Amplify, and the reasons any events may '
        'not be sent to Amplify. Several categories may share one '
        'opportunity.\n\nShifts are counted by need ID, date, start, '
        'and end. Two events that would create the same shift count '
        'once.\n\nAn event that cannot become a shift blocks the '
        'entire send. A blocking event is listed once for each '
        'reason.\n\nThe service reads every opportunity from Amplify '
        'to answer. A send checks Amplify again before it writes.'
    ),
    response_model=PreviewView
)
async def get_preview(
        run_id: str = Path(
            description='Identifier the run was created with.'
        ),
        principal: Principal = requires(SCOPE_RUNS_READ)
) -> PreviewView:
    """ Return what sending the run's current revision would create.

        Args:
            run_id (str):
                Identifier of the run to preview.

            principal (Principal):
                The authenticated caller, which the dependency supplies
                after checking the scope.

        Raises:
            HTTPException:
                404 when there is no such run.

            UpstreamError:
                If an opportunity cannot be read.  A preview that
                answered anyway would report every shift as new.

        Returns:
            preview (PreviewView):
                What a send would do.
    """

    del principal

    gathered = await in_the_database(
        lambda connection: read_run_for_send(
            connection=connection,
            run_id=run_id
        )
    )

    if gathered is None:
        raise missing_run(run_id=run_id)

    events, opportunities = gathered

    # Off the event loop, like the database read above and for the same
    # reason: this is a request per opportunity, and the service has
    # other callers to answer while it waits for them.
    existing = await run_in_threadpool(
        shifts_in_amplify,
        events=events
    )

    return to_preview_view(
        events=events,
        opportunities=opportunities,
        existing=existing
    )


async def _handed_over(
        request: Request,
        job_id: str,
        run_id: str,
        principal_id: str
) -> JobView:
    """ Give the collecting to the runner and answer with the job.

        The same three steps whether the run is new or is being
        collected again, because the work is the same work: the run
        says which calendar and which days, and the difference is only
        what was there before.

        Args:
            request (Request):
                The request, which carries the runner.

            job_id (str):
                Job the work is recorded against, already queued.

            run_id (str):
                Run to collect into.

            principal_id (str):
                Who asked for it.

        Returns:
            job (JobView):
                The job, as it stands when the answer is sent.
    """

    def work(reporter: Reporter) -> None:
        """ Collect, on a connection belonging to the job's thread. """
        in_database(
            lambda connection: collect(
                connection=connection,
                run_id=run_id,
                reporter=reporter,
                principal_id=principal_id
            )
        )

    request.app.state.runner.submit(job_id=job_id, work=work)

    job = await in_the_database(
        lambda connection: JobRepository(
            connection=connection
        ).get(job_id=job_id)
    )

    return to_job_view(job=job)


def checked_calendar(
        calendar: str
) -> str:
    """ Return a calendar name the deployment configured.

        Checked here rather than left to the core, which reports an
        unconfigured name as a configuration error -- a 500, which
        deliberately carries no reason.  The caller chose this value
        and is the one who can correct it, so it is a 422 naming the
        alternatives.

        Public because more than one group of endpoints takes a
        calendar name from a caller, and two copies of an allowlist
        are two chances for one of them to fall behind the settings.

        Args:
            calendar (str):
                What the caller asked for.

        Raises:
            HTTPException:
                422 when the name is not configured.

        Returns:
            calendar (str):
                The name, unchanged.
    """

    if calendar in GCAL_CALENDARS:
        return calendar

    raise unprocessable(
        detail=(
            f'"{calendar}" is not a calendar this service reads. '
            f'Use one of: {", ".join(sorted(GCAL_CALENDARS))}.'
        )
    )


def _checked_window(
        window: CollectRequest
) -> Tuple[str, str]:
    """ Return a window that names days a search can cover.

        The values are checked before a run is created, so a window
        nobody could collect is a refusal the caller reads rather than
        a run that exists and a job that fails.

        Args:
            window (CollectRequest):
                What the caller asked for.

        Raises:
            HTTPException:
                422 when the window cannot be read or does not move
                forward in time.

        Returns:
            window (Tuple[str, str]):
                The two dates, unchanged.  What is returned is what the
                caller sent, not the resolved instants: a run stores
                plain local dates, and the resolution happens again
                when the calendar is read.
    """

    try:
        resolve_window(
            start=window.window.start,
            end=window.window.end,
            start_name='The first day',
            end_name='the last day'
        )

    except ValueError as error:
        raise unprocessable(detail=str(error)) from error

    return window.window.start, window.window.end


def _started(
        connection: sqlite3.Connection,
        calendar: str,
        window: Tuple[str, str],
        principal_id: str
) -> Tuple[Run, str]:
    """ Create the run a collection fills in, and the job that does it.

        Both in one transaction.  A run with no job would be one
        nothing is working on and nothing will; a job with no run
        cannot be written at all, because a job is recorded against
        one.

        Args:
            connection (sqlite3.Connection):
                The database to write to.

            calendar (str):
                Which calendar the run collects.

            window (Tuple[str, str]):
                The first day and the day after the last.

            principal_id (str):
                Who asked.

        Raises:
            ValidationError:
                If either cannot be written.

        Returns:
            started (Tuple[Run, str]):
                The run, and the identifier of the job filling it in.
    """

    with transaction(connection=connection):
        run = RunRepository(connection=connection).create(
            calendar=calendar,
            window_start=window[0],
            window_end=window[1]
        )
        job = JobRepository(connection=connection).create(
            run_id=run.id,
            kind=JOB_KIND_COLLECT,
            principal_id=principal_id
        )

    return run, job.id


@router.post(
    '/runs',
    status_code=status.HTTP_202_ACCEPTED,
    summary=(
        'Collect a calendar\'s events within a date range into a new '
        'run'
    ),
    description=(
        'Collects a calendar\'s events in a date range into a new run, '
        'ready to review.\n\nAnswers when the run is created, with the '
        'job that collects the events. To follow its progress, read '
        'the job or its event stream. The run appears in the run list '
        'immediately.\n\nThe date range is a first day and the day '
        'after the last day, in the service\'s time zone, with no '
        'length limit. An event with no opportunity is collected, and '
        'blocks the send.'
    ),
    response_model=JobView
)
async def collect_run(
        request: Request,
        collection: CollectRequest,
        principal: Principal = requires(SCOPE_RUNS_WRITE)
) -> JobView:
    """ Create a run and start collecting into it.

        Args:
            request (Request):
                The request, which carries the runner that jobs are
                given to.

            collection (CollectRequest):
                Which calendar to read, and over which days.

            principal (Principal):
                The authenticated caller, which the dependency supplies
                after checking the scope.

        Raises:
            HTTPException:
                422 when the calendar is not configured, or the window
                does not name days a search can cover.

        Returns:
            job (JobView):
                The job collecting the run, queued.
    """

    calendar = checked_calendar(calendar=collection.calendar)
    window = _checked_window(window=collection)

    run, job_id = await in_the_database(
        lambda connection: _started(
            connection=connection,
            calendar=calendar,
            window=window,
            principal_id=principal.id
        )
    )

    return await _handed_over(
        request=request,
        job_id=job_id,
        run_id=run.id,
        principal_id=principal.id
    )


def _current_change_count(
        connection: sqlite3.Connection,
        run_id: str
) -> Optional[Tuple[Run, int]]:
    """ Return a run and how much has been done to its current revision.

        Args:
            connection (sqlite3.Connection):
                The database to read.

            run_id (str):
                Run to read.

        Returns:
            found (Tuple[Run, int] | None):
                The run and its current revision's change count, or
                None when there is no such run.  A run with no
                revision yet counts as none, which is true: nothing
                has been changed in a revision that does not exist.
    """

    history = read_run_history(
        connection=connection,
        run_id=run_id
    )

    if history is None:
        return None

    run, revisions = history

    return run, changes_in_current(run=run, revisions=revisions)


@router.post(
    '/runs/{run_id}/recollect',
    status_code=status.HTTP_202_ACCEPTED,
    summary='Collect a run\'s events again',
    description=(
        'Replaces the run\'s events with the current League Calendar '
        'events, from the same calendar and date range. The run keeps '
        'its identifier and date range. A new revision contains the '
        'new events, and earlier revisions remain readable.\n\n'
        '**Collecting a run again discards any changes made to it '
        'since it was collected.** Set `expectedChangeCount` to the '
        'number of changes `GET /v1/runs/{run_id}/revisions` reports '
        'for the current revision. If the number does not match, the '
        'run is not collected again.\n\nYou may not collect a run '
        'again while another job is working on it, or after it sent '
        'shifts to Amplify.'
    ),
    response_model=JobView
)
async def recollect_run(
        request: Request,
        recollection: RecollectRequest,
        run_id: str = Path(
            description='Identifier the run was created with.'
        ),
        principal: Principal = requires(SCOPE_RUNS_WRITE)
) -> JobView:
    """ Collect a run's window again, replacing what it holds.

        Args:
            request (Request):
                The request, which carries the runner that jobs are
                given to.

            recollection (RecollectRequest):
                How many changes the operator was told would be
                discarded.

            run_id (str):
                Identifier of the run to collect again.

            principal (Principal):
                The authenticated caller, which the dependency supplies
                after checking the scope.

        Raises:
            HTTPException:
                404 when there is no such run, 409 when the run is not
                one a recollection may replace.

        Returns:
            job (JobView):
                The job collecting the run again, queued.
    """

    found = await in_the_database(
        lambda connection: _current_change_count(
            connection=connection,
            run_id=run_id
        )
    )

    if found is None:
        raise missing_run(run_id=run_id)

    run, changed = found
    refusal = why_not_recollect(
        run=run,
        changed=changed,
        expected=recollection.expected_change_count
    )

    if refusal is not None:
        raise conflict(detail=refusal)

    job_id = await in_the_database(
        lambda connection: _restarted(
            connection=connection,
            run_id=run_id,
            principal_id=principal.id
        )
    )

    return await _handed_over(
        request=request,
        job_id=job_id,
        run_id=run_id,
        principal_id=principal.id
    )


def _restarted(
        connection: sqlite3.Connection,
        run_id: str,
        principal_id: str
) -> str:
    """ Mark a run as being collected again, and record the job doing it.

        Both in one transaction, so a run cannot be left saying it is
        being collected with nothing collecting it.

        Args:
            connection (sqlite3.Connection):
                The database to write to.

            run_id (str):
                Run being collected again.

            principal_id (str):
                Who asked.

        Raises:
            ValidationError:
                If either cannot be written.

        Returns:
            job_id (str):
                Identifier of the job doing the work.
    """

    with transaction(connection=connection):
        RunRepository(connection=connection).set_status(
            run_id=run_id,
            status=RUN_STATUS_COLLECTING
        )

        return JobRepository(connection=connection).create(
            run_id=run_id,
            kind=JOB_KIND_RECOLLECT,
            principal_id=principal_id
        ).id
