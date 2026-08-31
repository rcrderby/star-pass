#!/usr/bin/env python3
""" Turning a calendar window into a stored run.

    Read the calendar, match each event to a category, and work out
    the shift each of its roles would create.  A revision holds one
    event carrying a role per need ID rather than a row per need ID,
    so a reviewer edits the event rather than the rows it produced.

    A collection also records what it did **not** collect.  The window
    is read twice - once as the deployment searches it and once whole
    - and everything the run will not hold is stored with the reason.

    **What stops the run.**  An event that cannot become a correct
    shift is named rather than dropped.  A category whose need IDs
    disagree about their offsets describes two different shifts and
    cannot be stored as one event; a shift running past midnight
    cannot be read back, because the times are stored as times of day.
    Both are refused here, where the run can still be corrected.
"""

# Imports - Python Standard Library
import sqlite3
from dataclasses import replace
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

# Imports - Local
from . import _defaults
from ._database import transaction
from ._exceptions import ValidationError
from ._gcal_time import gcal_timezone, resolve_window
from .gcal_data import (
    exclusion_reason,
    GCALData,
    item_times,
    WindowRead
)
from ._building import event_from, opportunity_read
from ._calendar_note import as_text
from ._helpers import CategoryMatch, Helpers
from ._logging import get_logger
from ._shift_timing import role_timings
from ._records import (
    Event,
    Opportunity,
    Run,
    RUN_STATUS_FAILED,
    RUN_STATUS_UNSENT,
    UncollectedEvent,
    UNCOLLECTED_SEARCH
)
from ._reporting import (
    Reporter,
    STEP_MATCH_EVENTS,
    STEP_READ_OPPORTUNITIES,
    STEP_STORE_EVENTS
)
from ._derived import blocks_the_run
from ._repository import (
    EventRepository,
    RevisionRepository,
    RunRepository,
    UncollectedRepository,
    UnmatchedTitleRepository
)

# Constants
ISO_DATE_FORMAT = _defaults.ISO_DATE_FORMAT
SIMPLE_TIME_FORMAT = _defaults.SIMPLE_TIME_FORMAT

# Module logger
logger = get_logger(__name__)


def _read_moment(
        value: Any,
        timezone: ZoneInfo
) -> Optional[datetime]:
    """ Return a calendar time in the league's zone, or None.

        Args:
            value (Any):
                What the calendar gave, which is an ISO 8601 datetime
                when the calendar is behaving.

            timezone (ZoneInfo):
                The zone to read it in.

        Returns:
            moment (datetime | None):
                The same instant in the league's zone, or None when
                the value is not a date and time.
    """

    try:
        return datetime.fromisoformat(value).astimezone(timezone)

    except (TypeError, ValueError):
        return None


def _local_moment(
        value: str,
        timezone: ZoneInfo
) -> datetime:
    """ Return a calendar time, or stop the run for want of one.

        The reading an event needs.  A time that cannot be read is a
        shift that cannot be built.  An event the run is only
        describing reads the same value through '_read_moment' and
        settles for not knowing.

        Args:
            value (str):
                An ISO 8601 datetime, as the calendar gives one.

            timezone (ZoneInfo):
                The zone to read it in.

        Raises:
            ValidationError:
                If the value is not a datetime.

        Returns:
            moment (datetime):
                The same instant, in the league's zone.
    """

    moment = _read_moment(
        value=value,
        timezone=timezone
    )

    if moment is None:
        message = (
            f'The calendar gave "{value}", which is not a date and '
            'time a shift can be built from.'
        )
        logger.error(message)
        raise ValidationError(message)

    return moment


def carries_notes(
        calendar: str
) -> bool:
    """ Return whether this calendar's entries carry notes.

        Configuration rather than a name to test against, so that a
        calendar added or renamed carries its own answer (D30).

        Args:
            calendar (str):
                The calendar a run was collected from.

        Returns:
            carries (bool):
                Whether a description on one of its entries is kept
                with the event.
    """

    return bool(
        _defaults.GCAL_CALENDARS.get(calendar, {}).get('notes')
    )


def _note_of(
        item: Dict[str, Any],
        carries: bool
) -> Optional[str]:
    """ Return what to store as this item's calendar note.

        Args:
            item (Dict[str, Any]):
                A calendar item, whose description may be absent,
                plain text, or a fragment of HTML.

            carries (bool):
                Whether this calendar carries notes at all.

        Returns:
            note (str | None):
                The description as text, or None where the calendar
                carries no notes or the item has none.
    """

    if not carries:
        return None

    return as_text(description=item.get('description'))


def _event_from(
        item: Dict[str, Any],
        matched: CategoryMatch,
        timezone: ZoneInfo,
        note: Optional[str]
) -> Event:
    """ Return one calendar item as a revision holds it.

        The reading of the item is here and the making of the event
        is below, so that pulling an event in by hand from a stored
        row produces the same event.

        Args:
            item (Dict[str, Any]):
                A calendar item that passed the filter, so it has a
                title and both of its times.

            matched (CategoryMatch):
                The category its title reached.

            timezone (ZoneInfo):
                The zone its times are read in.

            note (str | None):
                What the calendar's description said, already text,
                or None where this calendar carries no notes.

        Raises:
            ValidationError:
                If the item cannot become a correct shift.

        Returns:
            event (Event):
                The event, with a role per need ID it serves.
    """

    # Attached rather than passed in: the note takes no part in
    # working out a shift, and 'event_from' is where a shift is worked
    # out.  What it is part of is the event, which is why it is here
    # and not on the row alone.
    return replace(
        event_from(
            identifier=item['id'],
            title=item['summary'],
            start=_local_moment(
                value=item['start']['dateTime'],
                timezone=timezone
            ),
            end=_local_moment(
                value=item['end']['dateTime'],
                timezone=timezone
            ),
            matched=matched
        ),
        calendar_note=note
    )


def _uncollected_from(
        item: Dict[str, Any],
        reason: str,
        timezone: ZoneInfo,
        note: Optional[str]
) -> UncollectedEvent:
    """ Return one calendar item as the record of a thing left out.

        Every field but the identifier and the reason may be absent,
        because the reasons name exactly the items missing something.
        A value that cannot be read is recorded as absent rather than
        stopping the run: this item is not becoming a shift either
        way.

        Args:
            item (Dict[str, Any]):
                A calendar item that will not become an event.

            reason (str):
                One of '_records.UNCOLLECTED_REASONS'.

            timezone (ZoneInfo):
                The zone its times are read in.

            note (str | None):
                What the calendar's description said, already text,
                or None where this calendar carries no notes.  Kept
                here as well as on the event so that pulling this row
                in by hand produces the event a collection would
                (D30): adding reads this row and never the calendar.

        Returns:
            uncollected (UncollectedEvent):
                The item, as the run records what it left out.
    """

    times = item_times(gcal_item=item)
    start = (
        _read_moment(value=times[0], timezone=timezone)
        if times is not None
        else None
    )
    end = (
        _read_moment(value=times[1], timezone=timezone)
        if times is not None
        else None
    )

    return UncollectedEvent(
        id=item['id'],
        reason=reason,
        calendar_note=note,
        title=item.get('summary'),
        # An all-day event carries the day it covers instead of a time,
        # which is the one thing worth saying about it.
        date=(
            start.strftime(ISO_DATE_FORMAT)
            if start is not None
            else (item.get('start') or {}).get('date')
        ),
        calendar_start=(
            start.strftime(SIMPLE_TIME_FORMAT)
            if start is not None
            else None
        ),
        calendar_end=(
            end.strftime(SIMPLE_TIME_FORMAT)
            if end is not None
            else None
        )
    )


def _uncollected(
        read: WindowRead,
        timezone: ZoneInfo,
        carries: bool
) -> List[UncollectedEvent]:
    """ Return what the window held that the run will not collect.

        Three reasons come from the item itself.  The fourth cannot:
        an event the query strings never returned is one nobody looked
        for, and only the whole window says which those are.

        Args:
            read (WindowRead):
                The window as searched and as it stands.

            timezone (ZoneInfo):
                The zone the calendar's times are read in.

        Returns:
            uncollected (List[UncollectedEvent]):
                One record per thing left out, without repeats.
    """

    searched = {item['id'] for item in read.searched}
    left_out: Dict[str, UncollectedEvent] = {}

    # The whole window is the only half to walk.  It holds everything
    # the searches returned as well, so what the searches found is
    # read off it by identifier rather than by looking at it twice.
    for item in read.everything:
        identifier = item['id']

        if identifier in left_out:
            continue

        reason = exclusion_reason(gcal_item=item)

        if reason is None and identifier in searched:
            continue

        left_out[identifier] = _uncollected_from(
            item=item,
            reason=reason if reason is not None else UNCOLLECTED_SEARCH,
            timezone=timezone,
            note=_note_of(item=item, carries=carries)
        )

    return list(left_out.values())


def _window_contents(
        run: Run,
        timezone: ZoneInfo,
        reporter: Reporter
) -> Tuple[List[Dict[str, Any]], List[UncollectedEvent]]:
    """ Return what a run's window holds, collected and not.

        The calendar is searched once per query string and the
        results are concatenated, so an event matching two arrives
        twice.  The first arrival is kept.

        What is left out is worked out here from the same reading,
        never from a second read when somebody asks.

        Args:
            run (Run):
                The run being collected, which names the calendar and
                the days.

            timezone (ZoneInfo):
                The zone the calendar's times are read in.

            reporter (Reporter):
                Where progress is described.

        Raises:
            ConfigurationError:
                If the calendar is not one the deployment configured.

            UpstreamError:
                If the calendar cannot be read.

            ValueError:
                If the run's window cannot be resolved.

        Returns:
            contents (Tuple[List[Dict[str, Any]], List[UncollectedEvent]]):
                The items that can become shifts, without repeats, and
                a record of everything else the window held.
    """

    calendar = GCALData(
        gcal_name=run.calendar,
        reporter=reporter
    )
    window_start, window_end = resolve_window(
        start=run.window_start,
        end=run.window_end,
        start_name='the window start',
        end_name='the window end'
    )
    read = calendar.read_window(
        timeMin=window_start,
        timeMax=window_end
    )
    filtered = calendar.filter_gcal_items(gcal_shift_data=read.searched)
    seen: Dict[str, Dict[str, Any]] = {}

    for item in filtered:
        seen.setdefault(item['id'], item)

    return (
        list(seen.values()),
        _uncollected(
            read=read,
            timezone=timezone,
            carries=carries_notes(calendar=run.calendar)
        )
    )


def _collected(
        items: Sequence[Dict[str, Any]],
        run: Run,
        timezone: ZoneInfo,
        helpers: Helpers,
        reporter: Reporter
) -> Tuple[List[Event], List[Opportunity]]:
    """ Return the events a run holds and the opportunities they name.

        The titles are read from Amplify here, so every review row
        can be labelled with one.

        Args:
            items (Sequence[Dict[str, Any]]):
                The calendar items to build events from.

            run (Run):
                The run being collected, which names the calendar the
                titles are matched against.

            timezone (ZoneInfo):
                The zone the calendar's times are read in.

            helpers (Helpers):
                What the opportunity reads are sent through.

            reporter (Reporter):
                Where progress is described.

        Raises:
            ValidationError:
                If an item cannot become a correct shift.

            UpstreamError:
                If an opportunity cannot be read.

        Returns:
            collected (Tuple[List[Event], List[Opportunity]]):
                The events, and one opportunity per need ID they name.
    """

    reporter.step_started(step=STEP_MATCH_EVENTS)

    events = []
    need_ids = set()
    carries = carries_notes(calendar=run.calendar)

    for item in items:
        matched = helpers.match_shift_info(
            gcal_name=run.calendar,
            need_name=item['summary']
        )
        events.append(
            _event_from(
                item=item,
                matched=matched,
                timezone=timezone,
                note=_note_of(item=item, carries=carries)
            )
        )

        # The need IDs alone.  How each one is timed is the business of
        # the role that names it, which the event carries: two
        # categories may time one listing differently, so there is
        # nothing left here for the categories to disagree about.
        need_ids.update(
            role.need_id
            for role in role_timings(
                matched=matched,
                title=item['summary']
            )
        )

    reporter.step_finished()
    reporter.step_started(step=STEP_READ_OPPORTUNITIES)

    opportunities = [
        opportunity_read(helpers=helpers, need_id=need_id)
        for need_id in sorted(need_ids)
    ]

    reporter.step_finished()

    return events, opportunities


def collect(
        connection: sqlite3.Connection,
        run_id: str,
        reporter: Reporter,
        principal_id: str
) -> Run:
    """ Fill in a run from the calendar it names.

        The run exists before this is called, holding the calendar
        and the window asked for, which is what makes the collection
        watchable: the job is recorded against a run.

        The same work whether the run is new or collected again.  A
        run collected again gains a revision holding what the calendar
        has now, and the revisions before it stay readable.

        Everything the collection produces is written in one
        transaction, because it all describes one reading of one
        window.

        Args:
            connection (sqlite3.Connection):
                The database to write to.

            run_id (str):
                Run to collect into.

            reporter (Reporter):
                Where progress is described.

            principal_id (str):
                Who asked for the collection (D13).  Recorded against
                the titles it finds the data model has no match for.

        Raises:
            ValidationError:
                If there is no such run, or an event cannot become a
                correct shift.

            ConfigurationError:
                If the run names a calendar the deployment has not
                configured.

            UpstreamError:
                If the calendar or an opportunity cannot be read.

        Returns:
            run (Run):
                The run as it now stands, with a revision holding what
                the calendar has now.
    """

    runs = RunRepository(connection=connection)
    run = runs.get(run_id=run_id)

    if run is None:
        message = f'There is no run with the identifier "{run_id}".'
        logger.error(message)
        raise ValidationError(message)

    # Whatever went wrong, the run must not be left saying it is
    # being collected.  Broad on purpose: a status corrected only for
    # the failures somebody thought of is a status that strands the
    # run on the first one nobody did.  The failure itself is the
    # caller's to report, so it goes on up.
    try:
        return _into(
            connection=connection,
            run=run,
            reporter=reporter,
            principal_id=principal_id
        )
    except BaseException:  # pylint: disable=broad-except
        runs.set_status(run_id=run.id, status=_after_failing(run=run))
        raise


def _after_failing(
        run: Run
) -> str:
    """ Return the status a run takes when its collection fails.

        The run answers which case this is: by the time the work
        runs the status is already 'collecting', and the one before it
        is gone.

        A run that never completed a collection has no revision to go
        back to, so 'failed' is where it rests.  A recollection has at
        least one complete revision, so the run goes back to holding
        it.  'unsent' is the only status a recollection can have begun
        from, because 'why_not_recollect' refuses any run already
        sent.

        Args:
            run (Run):
                The run as it stood when the collection began.

        Returns:
            status (str):
                'failed', or 'unsent' where a revision survives.
    """

    if run.current_revision == 0:
        return RUN_STATUS_FAILED

    return RUN_STATUS_UNSENT


def _into(
        connection: sqlite3.Connection,
        run: Run,
        reporter: Reporter,
        principal_id: str
) -> Run:
    """ Collect the run's window into it, and return what it holds.

        The body of 'collect', which holds it to one job: correcting
        the status when this raises.

        Args:
            connection (sqlite3.Connection):
                The database to write to.

            run (Run):
                The run being collected.

            reporter (Reporter):
                Where progress is described.

            principal_id (str):
                Who asked for the collection (D13).

        Raises:
            ValidationError:
                If an event cannot become a correct shift.

            ConfigurationError:
                If the run names a calendar the deployment has not
                configured.

            UpstreamError:
                If the calendar or an opportunity cannot be read.

        Returns:
            run (Run):
                The run as it now stands.
    """

    runs = RunRepository(connection=connection)
    run_id = run.id
    timezone = gcal_timezone()
    items, uncollected = _window_contents(
        run=run,
        timezone=timezone,
        reporter=reporter
    )
    events, opportunities = _collected(
        items=items,
        run=run,
        timezone=timezone,
        helpers=Helpers(),
        reporter=reporter
    )

    reporter.step_started(step=STEP_STORE_EVENTS)

    with transaction(connection=connection):
        # Replacing, not continuing.  What the calendar says now is
        # the whole of the revision, so carrying the previous events
        # forward would leave behind ones the calendar no longer has.
        revision = RevisionRepository(connection=connection).create(
            run_id=run_id,
            replacing=True
        )
        EventRepository(connection=connection).add_all(
            run_id=run_id,
            revision=revision.number,
            events=events
        )
        runs.set_opportunities(
            run_id=run_id,
            opportunities=opportunities
        )
        UncollectedRepository(connection=connection).replace(
            run_id=run_id,
            uncollected=uncollected
        )
        _record_unmatched(
            connection=connection,
            run=run,
            events=events,
            principal_id=principal_id
        )
        runs.set_status(
            run_id=run_id,
            status=RUN_STATUS_UNSENT
        )

    reporter.step_finished()

    message = (
        f'Collected {len(events)} event(s) into run {run_id} '
        f'from the "{run.calendar}" calendar'
    )
    logger.info(message)

    return runs.get(run_id=run_id)


def _record_unmatched(
        connection: sqlite3.Connection,
        run: Run,
        events: Sequence[Event],
        principal_id: str
) -> None:
    """ Keep the titles this window held that the model did not match.

        An event the model matched nothing for is collected under
        the fallback category, whose need IDs are empty, so it has no
        roles and blocks the send.  The log is what survives the run,
        for the next edit of the model.

        One sighting per title, however many events carry it and
        however often the window is collected again.

        Args:
            connection (sqlite3.Connection):
                Connection to write on.

            run (Run):
                The run being collected, which says which calendar the
                titles belong to.

            events (Sequence[Event]):
                What the collection produced.

            principal_id (str):
                Who asked for the collection (D13).

        Raises:
            UpstreamError:
                If a title cannot be recorded.

        Returns:
            None.
    """

    unmatched = UnmatchedTitleRepository(connection=connection)

    for title in sorted({
        event.title for event in events if blocks_the_run(event=event)
    }):
        unmatched.record(
            calendar=run.calendar,
            title=title,
            run_id=run.id,
            principal_id=principal_id
        )

    return None
