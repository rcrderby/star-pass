#!/usr/bin/env python3
""" Turning a calendar window into a stored run.

    Read the calendar, match each event to a category, and work out the
    shift each of its roles would create.  A revision holds one event
    carrying a role per need ID rather than a row per need ID, which is
    what lets a reviewer edit the event rather than the rows it
    happened to produce: an event serving both skating and non-skating
    officials is one thing to retime, not two things to keep in step.

    A collection also records what it did **not** collect.  The window
    is read twice -- once as the deployment searches it and once
    whole -- and everything the run will not hold is stored with the
    reason, so that a reviewer asking where an event went is answered
    from the run rather than from a second calendar request.

    In the core, not the service.  Nothing here is about HTTP, and the
    command line client collects a run without one (D2).

    **What stops the run.**  An event that cannot become a correct
    shift is named rather than dropped: a missing shift is invisible
    until volunteers cannot sign up.  Two of those checks are about
    what a stored event can express rather than about the calendar.  An
    event holds one pair of shift times and a role per need ID, so a
    category whose need IDs disagree about their offsets describes two
    different shifts and cannot be stored as one event; and a shift
    running past midnight cannot be read back, because the times are
    stored as times of day.  Both are refused here, where the run can
    still be corrected, rather than stored and misread later.
"""

# Imports - Python Standard Library
import sqlite3
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
from ._helpers import CategoryMatch, Helpers
from ._logging import get_logger
from ._shift_timing import role_timings
from ._records import (
    Event,
    Opportunity,
    Run,
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
        shift that cannot be built, and a run that stored it would be
        one nobody could send; an event the run is only describing
        reads the same value through '_read_moment' and settles for
        not knowing.

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


def _event_from(
        item: Dict[str, Any],
        matched: CategoryMatch,
        timezone: ZoneInfo
) -> Event:
    """ Return one calendar item as a revision holds it.

        The reading of the item is here and the making of the event is
        below, because a person pulling an event in by hand makes one
        from a stored row rather than from a calendar item, and the
        two have to produce the same event.

        Args:
            item (Dict[str, Any]):
                A calendar item that passed the filter, so it has a
                title and both of its times.

            matched (CategoryMatch):
                The category its title reached.

            timezone (ZoneInfo):
                The zone its times are read in.

        Raises:
            ValidationError:
                If the item cannot become a correct shift.

        Returns:
            event (Event):
                The event, with a role per need ID it serves.
    """

    return event_from(
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
    )


def _uncollected_from(
        item: Dict[str, Any],
        reason: str,
        timezone: ZoneInfo
) -> UncollectedEvent:
    """ Return one calendar item as the record of a thing left out.

        Every field but the identifier and the reason may be absent,
        because the reasons name exactly the items that are missing
        something.  A value the calendar gave that cannot be read is
        recorded as absent rather than stopping the run: this item is
        not becoming a shift either way, and a run refused for the
        shape of an event it was never going to collect would be a run
        nobody could correct.

        Args:
            item (Dict[str, Any]):
                A calendar item that will not become an event.

            reason (str):
                One of '_records.UNCOLLECTED_REASONS'.

            timezone (ZoneInfo):
                The zone its times are read in.

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
        timezone: ZoneInfo
) -> List[UncollectedEvent]:
    """ Return what the window held that the run will not collect.

        Three of the reasons come from the item itself and hold
        whether or not a search found it.  The fourth is the one no
        item can carry: an event the configured query strings never
        returned is one nobody looked for, and only the whole window
        says which those are.

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
            timezone=timezone
        )

    return list(left_out.values())


def _window_contents(
        run: Run,
        timezone: ZoneInfo,
        reporter: Reporter
) -> Tuple[List[Dict[str, Any]], List[UncollectedEvent]]:
    """ Return what a run's window holds, collected and not.

        The calendar is searched once per configured query string and
        the results are concatenated, so an event matching two of them
        arrives twice.  It is one event either way, and the first
        arrival is the one kept: a revision holding it twice would
        show a reviewer two rows for one thing and send Amplify two
        identical shifts.

        What is left out is worked out here, from the same reading, and
        never from a second read at the moment somebody asks: the
        figure is shown on every reading of the run, and a live read
        would cost a calendar request per look and give the run a
        second opinion about its own window.

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
        _uncollected(read=read, timezone=timezone)
    )


def _collected(
        items: Sequence[Dict[str, Any]],
        run: Run,
        timezone: ZoneInfo,
        helpers: Helpers,
        reporter: Reporter
) -> Tuple[List[Event], List[Opportunity]]:
    """ Return the events a run holds and the opportunities they name.

        The titles are read from Amplify here rather than when a
        preview is asked for: every review row is labelled with one, so
        a lookup deferred to preview time would leave the main screen
        unable to name anything.

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

    for item in items:
        matched = helpers.match_shift_info(
            gcal_name=run.calendar,
            need_name=item['summary']
        )
        events.append(
            _event_from(
                item=item,
                matched=matched,
                timezone=timezone
            )
        )

        # The need IDs alone.  How each one is timed is the business of
        # the role that names it, which the event carries: two
        # categories timing one listing differently is what this window
        # is allowed to hold now (D25), so there is nothing left here
        # for the categories to disagree about.
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

        The run exists before this is called, holding the calendar and
        the window that were asked for.  That is what makes a
        collection watchable: the job that does this work is recorded
        against a run, so it has to have one.

        The same work whether the run is new or is being collected
        again.  A run collected again gains a revision holding what
        the calendar has now, and the revisions before it stay
        readable, so what was replaced is still there to look at.

        Everything the collection produces is written in one
        transaction.  A run left holding events but no opportunities
        would label none of them, and a reader could not tell that
        from a run whose opportunities Amplify had forgotten.  What the
        window held and the run left out is written there too, for the
        same reason, and so are the titles the data model had no match
        for: they all describe one reading of one window.

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

        Written here because here is where the fact is discovered: an
        event the model matched nothing for is collected under the
        fallback category, whose need IDs are empty, and that is an
        event with no roles.  It blocks the send, which is what gets
        this run seen to; the log is what survives the run, for the
        next edit of the model.

        One sighting per title, however many events carry it and
        however often the window is collected again -- the repository
        holds a run to one sighting of a title, so what the count
        measures is the runs a title turned up in rather than the
        times somebody read the same window.

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
