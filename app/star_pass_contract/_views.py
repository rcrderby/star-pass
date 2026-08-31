#!/usr/bin/env python3
""" Turning what is stored into what a caller is shown.

    One place, because there is more than one caller: the endpoints
    answer over HTTP and the command line client answers from the same
    database in the same process.  Two copies of this conversion would
    drift, and a difference between the modes would mean the core
    boundary had leaked.  **That is the reason for everything in this
    module, and it is not repeated below.**

    A route decides what to read and what a failure looks like; these
    functions decide what an answer contains, and nothing here knows
    it is being asked over a network.

    What each figure means is decided elsewhere.  The counts come from
    the repository and what an event does not store comes from
    '_derived' and '_preview'; this module names those answers for the
    contract.
"""

# Imports - Python Standard Library
from datetime import date, timedelta
from typing import AbstractSet, Dict, Iterable, List, Sequence

# Imports - Local
from star_pass._defaults import (
    FUZZY_MATCH_THRESHOLD,
    GCAL_CALENDARS,
    GCAL_PREFIX_FILTERS,
    GCAL_TIMEZONE,
    RETENTION_JOB_LOG_DAYS,
    RETENTION_REVISION_DAYS,
    RETENTION_UNMATCHED_TITLE_DAYS
)
from star_pass._editing import Operation
from star_pass._event_edits import was_edited
from star_pass._helpers import Helpers
from star_pass._models import get_shifts_info
from star_pass._derived import (
    blocks_the_run,
    capping_maximum,
    may_unassign,
    repeated,
    shift_length
)
from star_pass._credentials import CredentialCheck
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
    UNCOLLECTED_SEARCH,
    UnmatchedTitle
)
from ._messages import why_not_delete
from ._requests import EditRequest
from ._preview_schemas import (
    BlockerView,
    PreviewRowView,
    PreviewTotalsView,
    PreviewView,
    SkippedShiftView
)
from ._schemas import (
    CalendarView,
    CategoryView,
    ConfigView,
    CredentialView,
    EditView,
    EventRoleView,
    EventView,
    JobView,
    LogEntryView,
    MatchView,
    OpportunityView,
    RetentionView,
    RevisionView,
    RunCountsView,
    RunDetailView,
    RunView,
    UncollectedEventView,
    UncollectedGroupView,
    UnmatchedTitleView,
    WindowView
)


def _window_view(
        run: Run
) -> WindowView:
    """ Return a run's window, said both ways.

        The stored end is exclusive and stays that way: it is what
        is compared and what a collection is asked for.  The last day
        it covers is published beside it, so no client subtracts.

        Args:
            run (Run):
                The run whose window is being shown.

        Returns:
            view (WindowView):
                The window, with its last day and its zone.
    """

    return WindowView(
        start=run.window_start,
        end=run.window_end,
        last_day=str(
            date.fromisoformat(run.window_end) - timedelta(days=1)
        ),
        timezone=GCAL_TIMEZONE
    )


def _categories_of(
        calendar: str
) -> List[CategoryView]:
    """ Return the categories a calendar's data model offers.

        What a reviewer may put an event under, which is a different
        list from the opportunities a run happens to hold: the run has
        the ones its own events reached, and an event that matched
        nothing needs one no other event used.

        The fallback is not among them, and neither is a category
        configured with no usable need ID: an event under either could
        not become a shift, so offering it would offer a choice the
        write refuses.

        Args:
            calendar (str):
                Which calendar's model to read.

        Returns:
            categories (List[CategoryView]):
                The categories, in the order the model names them.
    """

    model = get_shifts_info()['calendar'].get(calendar, {})
    categories = []

    for key, category in (model.get('categories') or {}).items():
        need_ids = [
            str(need['id'])
            for need in (category.get('need_ids') or [])
            if str(need.get('id', '')).strip()
        ]

        if not need_ids:
            continue

        categories.append(
            CategoryView(
                key=key,
                label=category.get('description') or key,
                need_ids=need_ids
            )
        )

    return categories


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

        The window carries the zone the calendar is read in, which is
        what a bound with no UTC offset means.  It is the calendar's
        setting rather than the league's clock; the two are the same
        until a deployment sets the calendar's.

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
        window=_window_view(run=run),
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
        active_job_id=run.active_job_id,
        interrupted_job_id=run.interrupted_job_id,

        # The same function the operation refuses by, asked as a
        # question rather than restated as one. A predicate written
        # beside it would be a second copy of the rule, which is the
        # thing publishing this is meant to prevent.
        may_delete=why_not_delete(run=run) is None
    )


def _to_event_view(
        event: Event,
        repeats: Dict[str, str],
        calendar: str,
        helpers: Helpers
) -> EventView:
    """ Return an event as a caller sees it.

        Args:
            event (Event):
                The stored event.

            repeats (Dict[str, str]):
                Which events repeat which, worked out once for the
                whole revision rather than per event.

            calendar (str):
                Calendar the run was collected from, which the data
                model is read under to say whether the event has been
                edited.

            helpers (Helpers):
                Where that model is read through.  Built once per
                answer rather than per event: every row is asked the
                same question of the same model.

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
        calendar_note=event.calendar_note,
        shift_start=event.shift_start,
        shift_end=event.shift_end,
        length_minutes=shift_length(event=event),
        capped_at=capping_maximum(event=event),
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
        edited=was_edited(
            event=event,
            calendar=calendar,
            helpers=helpers
        ),
        roles=[
            EventRoleView(
                need_id=role.need_id,
                slots=role.slots,
                edited=role.edited,
                offset_start=role.offset_start,
                offset_end=role.offset_end,
                max_length=role.max_length,
                default_slots=role.default_slots
            )
            for role in event.roles
        ],
        duplicate_of=repeats.get(event.id),
        blocking=blocks_the_run(event=event),
        may_unassign=may_unassign(event=event)
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
        action=entry.action,
        subject=entry.subject,
        subject_count=entry.subject_count,
        category=entry.category,
        shift_time=entry.shift_time,
        minutes=entry.minutes,
        slots=entry.slots,
        need_id=entry.need_id
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

    repeats = repeated(events=detail.events)
    helpers = Helpers()

    return RunDetailView(
        **to_run_view(run=detail.run).model_dump(),
        events=[
            _to_event_view(
                event=event,
                repeats=repeats,
                calendar=detail.run.calendar,
                helpers=helpers
            )
            for event in detail.events
        ],
        opportunities=[
            OpportunityView(
                need_id=opportunity.need_id,
                title=opportunity.title,
                url=opportunity.url
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
            kind=revision.kind,
            source_revision=revision.source_revision,
            changes=revision.change_count,
            current=revision.number == run.current_revision
        )
        for revision in revisions
    ]


def to_uncollected_views(
        uncollected: Sequence[UncollectedEvent],
        in_revision: AbstractSet[str] = frozenset()
) -> List[UncollectedGroupView]:
    """ Return what a run's window held and the run left out.

        Grouped by reason, in the order the reasons are declared, so
        the one a reviewer can act on comes first.  A reason nothing
        was left out for is not published as an empty group: a reader
        counting the groups is counting what there is to look at.

        Whether an event may be pulled in is decided here, so no
        client forms a second opinion about what the endpoint that
        adds one will accept.

        An event already in the revision is not addable and its row is
        still published: reverting to the first revision drops the
        hand-added events, and the row is what the reviewer gets
        back.

        Args:
            uncollected (Sequence[UncollectedEvent]):
                Everything the collection left out, earliest first.

            in_revision (AbstractSet[str]):
                The identifiers the run's current revision holds.
                Defaults to none, for a caller asking about a run that
                holds nothing.

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
                        calendar_note=event.calendar_note,
                        addable=(
                            reason == UNCOLLECTED_SEARCH
                            and event.id not in in_revision
                        )
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
        preview reads the core's own answer rather than the published
        one, so a rename on the wire cannot change what a refusal
        decides.

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
        contract.

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
        entries: Sequence[LogEntry],
        calendar: str
) -> EditView:
    """ Return a revision after an edit, and what the edit logged.

        The whole revision rather than the events that changed: the
        derived figures beside a row are answers about the revision as
        a whole, and change for rows the edit never named.

        Args:
            events (Sequence[Event]):
                The revision's events as they now are.

            entries (Sequence[LogEntry]):
                What the edit added to the change log.

            calendar (str):
                Calendar the run was collected from.  A parameter
                rather than something read here, because this function
                is given a revision's events and not the run they
                belong to, and the answer says of every row whether
                undoing it would change it.

        Returns:
            view (EditView):
                The revision and the entries, shaped for the contract.
    """

    repeats = repeated(events=events)
    helpers = Helpers()

    return EditView(
        events=[
            _to_event_view(
                event=event,
                repeats=repeats,
                calendar=calendar,
                helpers=helpers
            )
            for event in events
        ],
        log=[_to_log_entry_view(entry=entry) for entry in entries]
    )


def to_operations(
        asked: EditRequest
) -> List[Operation]:
    """ Return a request's operations as the core takes them.

        Both halves are given the same shape and must hand the core
        the same record.

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


def to_config_view() -> ConfigView:
    """ Return what the deployment was configured with.

        Read from the settings rather than from a record.

        The calendars are in key order rather than the order they were
        configured, so what is published is a property of the
        configuration rather than of how it was written down.

        Args:
            None.

        Returns:
            view (ConfigView):
                The settings a caller is shown, shaped for the
                contract.
    """

    return ConfigView(
        timezone=GCAL_TIMEZONE,
        match_threshold=FUZZY_MATCH_THRESHOLD,
        excluded_title_terms=list(GCAL_PREFIX_FILTERS),
        calendars=[
            CalendarView(
                key=key,
                search_terms=list(GCAL_CALENDARS[key]['query_strings']),
                notes=bool(GCAL_CALENDARS[key].get('notes')),
                categories=_categories_of(calendar=key)
            )
            for key in sorted(GCAL_CALENDARS)
        ],
        retention=RetentionView(
            job_log_days=RETENTION_JOB_LOG_DAYS,
            revision_days=RETENTION_REVISION_DAYS,
            unmatched_title_days=RETENTION_UNMATCHED_TITLE_DAYS
        )
    )


def to_credential_view(
        checked: CredentialCheck
) -> CredentialView:
    """ Return what a credential test answered.

        One answer to what "working" means.

        Args:
            checked (CredentialCheck):
                What asking Amplify produced.

        Returns:
            view (CredentialView):
                The answer a caller is shown, shaped for the contract.
    """

    return CredentialView(
        working=checked.working,
        last_four=checked.last_four,
        reason=checked.reason
    )


def to_unmatched_view(
        unmatched: UnmatchedTitle
) -> UnmatchedTitleView:
    """ Return one title the data model did not match.

        Args:
            unmatched (UnmatchedTitle):
                The title and its sightings, as they are stored.

        Returns:
            view (UnmatchedTitleView):
                The entry a caller is shown, shaped for the contract.
    """

    return UnmatchedTitleView(
        calendar=unmatched.calendar,
        title=unmatched.title,
        times_seen=unmatched.times_seen,
        first_seen=unmatched.first_seen,
        last_seen=unmatched.last_seen
    )


def to_unmatched_title_views(
        unmatched: Sequence[UnmatchedTitle]
) -> List[UnmatchedTitleView]:
    """ Return every title the data model has not matched.

        Args:
            unmatched (Sequence[UnmatchedTitle]):
                The titles, in the order to publish them.

        Returns:
            views (List[UnmatchedTitleView]):
                One entry per title in a calendar.
    """

    return [to_unmatched_view(unmatched=entry) for entry in unmatched]
