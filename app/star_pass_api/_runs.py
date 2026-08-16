#!/usr/bin/env python3
""" Reading runs, one in full, its history and what it would send.

    The first callers of the repository layer's run and revision side:
    the list a person opens the tool on, the run itself with
    everything the review screen reads at once, the numbered versions
    its events have been through, and what sending it would create.

    No domain logic lives here.  What a run holds is counted by the
    repository, and what an event does not say is worked out by the
    core's '_derived'; this module reads those answers and shapes them
    for the wire (D1).
"""

# Imports - Python Standard Library
import sqlite3
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# Imports - Third-Party
from fastapi import APIRouter, HTTPException, Path, status

# Imports - Local
from star_pass._defaults import LOCAL_TIMEZONE
from star_pass._derived import (
    blocks_the_run,
    capping_maximum,
    repeated,
    shift_length
)
from star_pass._preview import preview
from star_pass._records import (
    Event,
    LogEntry,
    Opportunity,
    Revision,
    Run
)
from star_pass._repository import (
    ChangeLogRepository,
    EventRepository,
    RevisionRepository,
    RunRepository
)
from . import _defaults
from ._schemas import (
    BlockerView,
    EventRoleView,
    EventView,
    LogEntryView,
    MatchView,
    OpportunityView,
    PreviewRowView,
    PreviewTotalsView,
    PreviewView,
    RevisionView,
    RunCountsView,
    RunDetailView,
    RunView,
    WindowView
)
from ._security import Principal, requires, SCOPE_RUNS_READ
from ._storage import read

router = APIRouter(tags=[_defaults.API_TAG_RUNS])


@dataclass(frozen=True)
class _Detail:
    """ Everything one read of a run gathered.

        Held together rather than fetched a piece at a time, because a
        screen showing the events, the opportunities labelling them and
        the log of what was done to them shows all three at once.  Read
        separately they could disagree, each having seen the run at a
        different moment.

        Attributes:
            run (Run):
                The run itself.

            events (List[Event]):
                The current revision's events.

            opportunities (List[Opportunity]):
                Every opportunity the run resolved.

            log (List[LogEntry]):
                The run's change log.
    """

    run: Run
    events: List[Event]
    opportunities: List[Opportunity]
    log: List[LogEntry]


def _gather(
        connection: sqlite3.Connection,
        run_id: str
) -> Optional[_Detail]:
    """ Read a run and everything shown beside it, in one go.

        All four reads share the connection, so they describe the run
        at one moment rather than at four.

        Args:
            connection (sqlite3.Connection):
                Connection to read on.

            run_id (str):
                Run to read.

        Returns:
            detail (_Detail | None):
                Everything about the run, or None when there is no
                such run.
    """

    runs = RunRepository(connection=connection)
    run = runs.get(run_id=run_id)

    if run is None:
        return None

    return _Detail(
        run=run,
        # A run before its first revision reports revision 0, which
        # holds nothing and reads back as nothing.  No guard for it:
        # the answer is already the right one.
        events=EventRepository(connection=connection).list_all(
            run_id=run_id,
            revision=run.current_revision
        ),
        opportunities=runs.get_opportunities(run_id=run_id),
        log=ChangeLogRepository(connection=connection).list_all(
            run_id=run_id
        )
    )


def _history(
        connection: sqlite3.Connection,
        run_id: str
) -> Optional[Tuple[Run, List[Revision]]]:
    """ Read a run and its revisions together.

        The run is read as well as the revisions, and not only to know
        the run exists: it is what says which revision is the current
        one.  Both reads share the connection, so the answer cannot be
        a list of revisions from one moment marked current from
        another.

        Args:
            connection (sqlite3.Connection):
                Connection to read on.

            run_id (str):
                Run to read the history of.

        Returns:
            history (Tuple[Run, List[Revision]] | None):
                The run and its revisions oldest first, or None when
                there is no such run.
    """

    run = RunRepository(connection=connection).get(run_id=run_id)

    if run is None:
        return None

    return (
        run,
        RevisionRepository(connection=connection).list_all(run_id=run_id)
    )


def _to_send(
        connection: sqlite3.Connection,
        run_id: str
) -> Optional[Tuple[List[Event], List[Opportunity]]]:
    """ Read what a send would work from.

        The events of the current revision and the opportunities
        labelling them, on one connection: a preview assembled from
        two moments could label a shift with a title that no longer
        belongs to it.

        Args:
            connection (sqlite3.Connection):
                Connection to read on.

            run_id (str):
                Run to read.

        Returns:
            gathered (Tuple[List[Event], List[Opportunity]] | None):
                The events and the opportunities, or None when there
                is no such run.
    """

    runs = RunRepository(connection=connection)
    run = runs.get(run_id=run_id)

    if run is None:
        return None

    return (
        EventRepository(connection=connection).list_all(
            run_id=run_id,
            revision=run.current_revision
        ),
        runs.get_opportunities(run_id=run_id)
    )


def _missing(
        run_id: str
) -> HTTPException:
    """ Return the failure for a run that is not there.

        Raised by the endpoint rather than left to the repository,
        which reports a value it cannot use and a missing run the same
        way; only the endpoint knows it was asked for one by
        identifier.

        Args:
            run_id (str):
                What the caller asked for.

        Returns:
            error (HTTPException):
                A 404 naming the run.
    """

    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f'There is no run with the ID "{run_id}".'
    )


def _to_run_view(
        run: Run
) -> RunView:
    """ Return a run as a caller sees it.

        Args:
            run (Run):
                The stored run.

        Returns:
            view (RunView):
                The run, shaped for the wire.
    """

    return RunView(
        id=run.id,
        calendar=run.calendar,
        window=WindowView(
            start=run.window_start,
            end=run.window_end,
            timezone=LOCAL_TIMEZONE
        ),
        status=run.status,
        collected_at=run.collected_at,
        sent_at=run.sent_at,
        revised_at=run.revised_at,
        current_revision=run.current_revision,
        counts=RunCountsView(
            events=run.event_count,
            shifts=run.shift_count,
            unmatched=run.unmatched_count
        ),
        active_job_id=run.active_job_id
    )


def _to_event_view(
        event: Event,
        opportunities: Dict[str, Opportunity],
        repeats: Dict[str, str]
) -> EventView:
    """ Return an event as a caller sees it.

        Args:
            event (Event):
                The stored event.

            opportunities (Dict[str, Opportunity]):
                The run's opportunities, by need ID, which the cap is
                worked out against.

            repeats (Dict[str, str]):
                Which events repeat which, worked out once for the
                whole revision rather than per event.

        Returns:
            view (EventView):
                The event, shaped for the wire.
    """

    match = event.match

    return EventView(
        id=event.id,
        title=event.title,
        date=event.date,
        calendar_start=event.calendar_start,
        calendar_end=event.calendar_end,
        shift_start=event.shift_start,
        shift_end=event.shift_end,
        length_minutes=shift_length(event=event),
        capped_at=capping_maximum(
            event=event,
            opportunities=opportunities
        ),
        category=event.category,
        match=(
            MatchView(
                kind=match.kind,
                keyword=match.keyword,
                score=match.score
            )
            if match is not None
            else None
        ),
        added_by_hand=event.added_by_hand,
        roles=[
            EventRoleView(
                need_id=role.need_id,
                slots=role.slots,
                edited=role.edited
            )
            for role in event.roles
        ],
        duplicate_of=repeats.get(event.id),
        blocking=blocks_the_run(event=event)
    )


def _to_detail_view(
        detail: _Detail
) -> RunDetailView:
    """ Return a run and everything beside it, as a caller sees it.

        Args:
            detail (_Detail):
                What one read of the run gathered.

        Returns:
            view (RunDetailView):
                The run in full, shaped for the wire.
    """

    by_need_id = {
        opportunity.need_id: opportunity
        for opportunity in detail.opportunities
    }
    repeats = repeated(events=detail.events)

    return RunDetailView(
        **_to_run_view(run=detail.run).model_dump(),
        events=[
            _to_event_view(
                event=event,
                opportunities=by_need_id,
                repeats=repeats
            )
            for event in detail.events
        ],
        opportunities=[
            OpportunityView(
                need_id=opportunity.need_id,
                title=opportunity.title,
                url=opportunity.url,
                max_length=opportunity.max_length,
                offset_start=opportunity.offset_start,
                offset_end=opportunity.offset_end,
                default_slots=opportunity.default_slots
            )
            for opportunity in detail.opportunities
        ],
        log=[
            LogEntryView(
                id=entry.id,
                revision=entry.revision,
                logged_at=entry.logged_at,
                principal_id=entry.principal_id,
                entry=entry.entry
            )
            for entry in detail.log
        ]
    )


@router.get(
    '/runs',
    summary='List the runs, newest first',
    description=(
        'Every run the service holds, most recently collected first, '
        'including one still being collected. Each carries what its '
        'current revision holds and the job still working on it, so '
        'the list is enough to decide what to open without reading '
        'each run in turn.'
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

    runs = await read(
        lambda connection: RunRepository(
            connection=connection
        ).list_all()
    )

    return [_to_run_view(run=run) for run in runs]


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

    detail = await read(
        lambda connection: _gather(
            connection=connection,
            run_id=run_id
        )
    )

    if detail is None:
        raise _missing(run_id=run_id)

    return _to_detail_view(detail=detail)


@router.get(
    '/runs/{run_id}/revisions',
    summary='List a run\'s revisions, oldest first',
    description=(
        'Every numbered version of the run\'s events, in the order '
        'they were made. Everything below the current revision is '
        'history and is never written to again: editing adds a '
        'revision holding a copy, and reverting does the same rather '
        'than deleting anything, so the record of what was done '
        'survives being undone.\n\n'
        'Each carries how many changes were made while it was '
        'current, which is what says whether a revision is worth '
        'looking at.'
    ),
    response_model=List[RevisionView]
)
async def list_revisions(
        run_id: str = Path(
            description='Identifier the run was created with.'
        ),
        principal: Principal = requires(SCOPE_RUNS_READ)
) -> List[RevisionView]:
    """ Return a run's revisions.

        Args:
            run_id (str):
                Identifier of the run to read the history of.

            principal (Principal):
                The authenticated caller, which the dependency supplies
                after checking the scope.

        Raises:
            HTTPException:
                404 when there is no such run.  A run that exists and
                has no revision yet answers with an empty list, which
                is a different fact and reads differently.

        Returns:
            revisions (List[RevisionView]):
                Every revision of the run, oldest first.
    """

    del principal

    history = await read(
        lambda connection: _history(
            connection=connection,
            run_id=run_id
        )
    )

    if history is None:
        raise _missing(run_id=run_id)

    run, revisions = history

    return [
        RevisionView(
            number=revision.number,
            created_at=revision.created_at,
            label=revision.label,
            changes=revision.change_count,
            current=revision.number == run.current_revision
        )
        for revision in revisions
    ]


@router.get(
    '/runs/{run_id}/preview',
    summary='Report what sending this run would create',
    description=(
        'What a send would do, grouped by Amplify opportunity and '
        'never by category: several categories share one listing, so '
        'grouping by category would show it twice under two names and '
        'split a total the reader is about to check against Amplify.\n\n'
        'Shifts are counted by identity -- need ID, date, start and '
        'end -- so two events asking for the same row count once, and '
        'a reader is told how many rows repeat rather than left to '
        'wonder why the total is below what they can see.\n\n'
        'An event that cannot become a shift stops the whole send and '
        'is named with every reason it cannot, so fixing one does not '
        'reveal another.\n\n'
        '**This does not yet say which shifts Amplify already has.** '
        'That needs a read of the live opportunity, which arrives with '
        'the send path that re-checks the same thing inside its '
        'transaction, so that both ask the question the same way. '
        'Until then the totals describe what the stored revision would '
        'create, and some of it may already exist.'
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

        Returns:
            preview (PreviewView):
                What a send would do.
    """

    del principal

    gathered = await read(
        lambda connection: _to_send(
            connection=connection,
            run_id=run_id
        )
    )

    if gathered is None:
        raise _missing(run_id=run_id)

    events, opportunities = gathered
    result = preview(
        events=events,
        opportunities={
            opportunity.need_id: opportunity
            for opportunity in opportunities
        }
    )

    return PreviewView(
        totals=PreviewTotalsView(
            will_create=result.will_create,
            repeated_rows=result.repeated_rows,
            blocking_events=result.blocking_events
        ),
        rows=[
            PreviewRowView(
                need_id=row.need_id,
                title=row.title,
                will_create=row.will_create,
                slots=row.slots,
                first_date=row.first_date,
                last_date=row.last_date
            )
            for row in result.rows
        ],
        blockers=[
            BlockerView(
                event_id=blocker.event_id,
                reason=blocker.reason
            )
            for blocker in result.blockers
        ]
    )
