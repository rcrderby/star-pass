#!/usr/bin/env python3
""" Turning what is stored into what a caller is shown.

    One place, because there is more than one caller.  The endpoints
    answer over HTTP and the command line client answers from the same
    database in the same process, and D2 only holds while both produce
    the same answer: two copies of this conversion would drift, and a
    difference between the modes would mean the core boundary had
    leaked.

    Separate from the routes for the same reason it is separate from
    the records.  A route decides what to read and what a failure
    looks like; these functions decide what the answer contains, and
    nothing here knows it is being asked over a network -- which is
    what lets a client that is not asking over one use them.

    What each figure means is not decided here either.  The counts on
    a run come from the repository, and what an event does not store
    comes from the core's '_derived' and '_preview'; this module reads
    those answers and names them for the contract.
"""

# Imports - Python Standard Library
from typing import AbstractSet, Dict, Iterable, List, Sequence

# Imports - Local
from star_pass._defaults import LOCAL_TIMEZONE
from star_pass._editing import Operation
from star_pass._derived import (
    blocks_the_run,
    capping_maximum,
    repeated,
    shift_length
)
from star_pass._preview import Preview, preview
from star_pass._reading import RunDetail
from star_pass._records import (
    Event,
    Job,
    LogEntry,
    Opportunity,
    Revision,
    Run,
    ShiftIdentity,
    UncollectedEvent,
    UNCOLLECTED_REASONS,
    UNCOLLECTED_SEARCH
)
from ._schemas import (
    BlockerView,
    EditRequest,
    EditView,
    EventRoleView,
    EventView,
    JobView,
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
    SkippedShiftView,
    UncollectedEventView,
    UncollectedGroupView,
    WindowView
)


def _by_need_id(
        opportunities: Iterable[Opportunity]
) -> Dict[str, Opportunity]:
    """ Return a run's opportunities, keyed on the need they belong to.

        Built here rather than by each caller, because a caller that
        keyed it differently would be asking the same question and
        getting a different answer.

        Args:
            opportunities (Iterable[Opportunity]):
                Every opportunity the run resolved.

        Returns:
            keyed (Dict[str, Opportunity]):
                The opportunities, by need ID.
    """

    return {
        opportunity.need_id: opportunity
        for opportunity in opportunities
    }


def to_job_view(
        job: Job
) -> JobView:
    """ Return a job as a caller sees it.

        Args:
            job (Job):
                The stored job.

        Returns:
            view (JobView):
                The job, shaped for the contract.
    """

    return JobView(
        id=job.id,
        run_id=job.run_id,
        kind=job.kind,
        status=job.status,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        detail=job.detail
    )


def to_run_view(
        run: Run
) -> RunView:
    """ Return a run as a caller sees it.

        Args:
            run (Run):
                The stored run.

        Returns:
            view (RunView):
                The run, shaped for the contract.
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
            unmatched=run.unmatched_count,
            uncollected=run.uncollected_count
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
                The event, shaped for the contract.
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


def _to_log_entry_view(
        entry: LogEntry
) -> LogEntryView:
    """ Return one change log entry as a caller sees it.

        Below both callers: a run's detail carries its whole log, and
        an edit answers with the entries it just wrote.  Written twice,
        the two could describe the same row differently.

        Args:
            entry (LogEntry):
                The stored entry.

        Returns:
            view (LogEntryView):
                The entry, shaped for the contract.
    """

    return LogEntryView(
        id=entry.id,
        revision=entry.revision,
        logged_at=entry.logged_at,
        principal_id=entry.principal_id,
        entry=entry.entry
    )


def to_detail_view(
        detail: RunDetail
) -> RunDetailView:
    """ Return a run and everything shown beside it.

        Takes what one read gathered rather than its parts, so that
        the two callers cannot pass them in different orders or leave
        one out.

        Args:
            detail (RunDetail):
                Everything one read of the run gathered.

        Returns:
            view (RunDetailView):
                The run in full, shaped for the contract.
    """

    keyed = _by_need_id(opportunities=detail.opportunities)
    repeats = repeated(events=detail.events)

    return RunDetailView(
        **to_run_view(run=detail.run).model_dump(),
        events=[
            _to_event_view(
                event=event,
                opportunities=keyed,
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
            _to_log_entry_view(entry=entry)
            for entry in detail.log
        ]
    )


def to_revision_views(
        run: Run,
        revisions: Sequence[Revision]
) -> List[RevisionView]:
    """ Return a run's revisions as a caller sees them.

        Which one is current comes from the run rather than from the
        position of the last item.  The two agree, but the run is
        where that fact is decided.

        Args:
            run (Run):
                The stored run.

            revisions (Sequence[Revision]):
                Its revisions, oldest first.

        Returns:
            views (List[RevisionView]):
                The revisions, shaped for the contract.
    """

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


def to_uncollected_views(
        uncollected: Sequence[UncollectedEvent]
) -> List[UncollectedGroupView]:
    """ Return what a run's window held and the run left out.

        Grouped by reason, in the order the reasons are declared, so
        the one a reviewer can act on comes first.  A reason nothing
        was left out for is not published as an empty group: a reader
        counting the groups is counting what there is to look at.

        Whether an event may be pulled in is decided here rather than
        by whoever is showing it.  A client working it out from the
        reason would be a second opinion about what the endpoint that
        adds one will accept, and the two would eventually differ.

        Args:
            uncollected (Sequence[UncollectedEvent]):
                Everything the collection left out, earliest first.

        Returns:
            views (List[UncollectedGroupView]):
                One group per reason anything was left out for.
    """

    groups = []

    for reason in UNCOLLECTED_REASONS:
        grouped = [
            event for event in uncollected
            if event.reason == reason
        ]

        if not grouped:
            continue

        groups.append(
            UncollectedGroupView(
                reason=reason,
                events=[
                    UncollectedEventView(
                        id=event.id,
                        title=event.title,
                        date=event.date,
                        calendar_start=event.calendar_start,
                        calendar_end=event.calendar_end,
                        addable=reason == UNCOLLECTED_SEARCH
                    )
                    for event in grouped
                ]
            )
        )

    return groups


def previewed(
        events: Sequence[Event],
        opportunities: Sequence[Opportunity],
        existing: AbstractSet[ShiftIdentity]
) -> Preview:
    """ Return what a send would do, as the core works it out.

        The step before shaping.  A caller deciding something from a
        preview -- whether a send may go ahead, say -- reads the core's
        own answer rather than the published one, so a rename on the
        wire cannot change what a refusal decides.  The keying of the
        opportunities happens here, so both callers preview the same
        revision against the same set.

        Args:
            events (Sequence[Event]):
                The current revision's events.

            opportunities (Sequence[Opportunity]):
                Every opportunity the run resolved.

            existing (AbstractSet[ShiftIdentity]):
                The shifts Amplify already holds.

        Returns:
            preview (Preview):
                What a send would do.
    """

    return preview(
        events=events,
        opportunities=_by_need_id(opportunities=opportunities),
        existing=existing
    )


def to_preview_view(
        events: Sequence[Event],
        opportunities: Sequence[Opportunity],
        existing: AbstractSet[ShiftIdentity]
) -> PreviewView:
    """ Return what sending a revision would create.

        The calculation is the core's; this names its answer for the
        contract.  Both are done here rather than by each caller, so
        that a caller cannot preview the same revision against a
        differently built set of opportunities.

        Args:
            events (Sequence[Event]):
                The current revision's events.

            opportunities (Sequence[Opportunity]):
                Every opportunity the run resolved.

            existing (AbstractSet[ShiftIdentity]):
                The shifts Amplify already holds, read live by
                '_opportunities.shifts_in_amplify'.  Required rather
                than defaulted: a preview answered without asking would
                promise rows that a send then skips, and neither mode
                would have anything to say about the difference.

        Returns:
            view (PreviewView):
                What a send would do, shaped for the contract.
    """

    result = previewed(
        events=events,
        opportunities=opportunities,
        existing=existing
    )

    return PreviewView(
        totals=PreviewTotalsView(
            will_create=result.will_create,
            already_in_amplify=result.already_in_amplify,
            repeated_rows=result.repeated_rows,
            blocking_events=result.blocking_events
        ),
        rows=[
            PreviewRowView(
                need_id=row.need_id,
                title=row.title,
                will_create=row.will_create,
                already_in_amplify=row.already_in_amplify,
                slots=row.slots,
                first_date=row.first_date,
                last_date=row.last_date
            )
            for row in result.rows
        ],
        skipped=[
            SkippedShiftView(
                need_id=shift.need_id,
                date=shift.date,
                shift_start=shift.shift_start,
                shift_end=shift.shift_end
            )
            for shift in result.skipped
        ],
        blockers=[
            BlockerView(
                event_id=blocker.event_id,
                reason=blocker.reason
            )
            for blocker in result.blockers
        ]
    )


def to_edit_view(
        events: Sequence[Event],
        opportunities: Sequence[Opportunity],
        entries: Sequence[LogEntry]
) -> EditView:
    """ Return a revision after an edit, and what the edit logged.

        The whole revision rather than the events that changed: a
        reviewer's screen is redrawn from this, and the derived figures
        beside a row -- whether another event would create the same
        shift, above all -- are answers about the revision as a whole
        and change for rows the edit never named.

        Args:
            events (Sequence[Event]):
                The revision's events as they now are.

            opportunities (Sequence[Opportunity]):
                The run's opportunities, for labelling the roles.

            entries (Sequence[LogEntry]):
                What the edit added to the change log.

        Returns:
            view (EditView):
                The revision and the entries, shaped for the contract.
    """

    keyed = _by_need_id(opportunities=opportunities)
    repeats = repeated(events=events)

    return EditView(
        events=[
            _to_event_view(
                event=event,
                opportunities=keyed,
                repeats=repeats
            )
            for event in events
        ],
        log=[_to_log_entry_view(entry=entry) for entry in entries]
    )


def to_operations(
        asked: EditRequest
) -> List[Operation]:
    """ Return a request's operations as the core takes them.

        Below both halves, like every other conversion here: the
        service and the command line client are given the same shape
        and must hand the core the same record, and two conversions
        could differ about a field that is absent.

        Args:
            asked (EditRequest):
                The request, as it arrived.

        Returns:
            operations (List[Operation]):
                One 'Operation' per operation asked for, in order.
    """

    return [
        Operation(
            op=operation.op,
            event_ids=tuple(operation.event_ids),
            category=operation.category,
            time=operation.time,
            need_id=operation.need_id,
            slots=operation.slots,
            minutes=operation.minutes
        )
        for operation in asked.operations
    ]
