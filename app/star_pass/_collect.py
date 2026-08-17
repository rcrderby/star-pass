#!/usr/bin/env python3
""" Turning a calendar window into a stored run.

    What the CSV path does to a file, this does to the database: read
    the calendar, match each event to a category, and work out the
    shift each of its roles would create.  The difference is the shape
    it lands in.  A CSV row is one need ID, so an event serving both
    skating and non-skating officials is two rows that nothing relates
    to each other; a revision holds one event carrying a role per need
    ID, which is what lets a reviewer edit the event rather than the
    rows it happened to produce.

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
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

# Imports - Local
from . import _defaults
from ._database import transaction
from ._exceptions import ValidationError
from ._gcal_time import gcal_timezone, resolve_window
from .gcal_data import GCALData
from ._helpers import CategoryMatch, Helpers
from ._logging import get_logger
from ._opportunities import public_url, read_need, title_of
from ._records import (
    Event,
    EventRole,
    Opportunity,
    Run,
    RUN_STATUS_UNSENT
)
from ._reporting import Reporter
from ._repository import (
    EventRepository,
    RevisionRepository,
    RunRepository
)

# Constants
ISO_DATE_FORMAT = _defaults.ISO_DATE_FORMAT
SIMPLE_TIME_FORMAT = _defaults.SIMPLE_TIME_FORMAT

# What a revision a collection produced is called.  Which of the two
# it is says whether anything was there before, which is the one thing
# a reader wants from the label.
FIRST_REVISION_LABEL = 'As collected'
LATER_REVISION_LABEL = 'As recollected'

# How many minutes a day holds, for saying that a shift ran past the
# end of one.
MINUTES_PER_DAY = 24 * 60

# Module logger
logger = get_logger(__name__)


@dataclass(frozen=True)
class _RoleTiming:
    """ What one need ID contributes to an event and its shift.

        Attributes:
            role (EventRole):
                The opportunity and how many volunteers it wants.

            offset_start (int):
                Minutes added to the event's start to reach the
                shift's.

            offset_end (int):
                Minutes added to the event's end to reach the shift's.

            max_length (int, optional):
                Longest shift the opportunity accepts, or None.
    """

    role: EventRole
    offset_start: int
    offset_end: int
    max_length: Optional[int]


def _local_moment(
        value: str,
        timezone: ZoneInfo
) -> datetime:
    """ Return a calendar time in the zone the league reads it in.

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

    try:
        return datetime.fromisoformat(value).astimezone(timezone)

    except (TypeError, ValueError) as error:
        message = (
            f'The calendar gave "{value}", which is not a date and '
            'time a shift can be built from.'
        )
        logger.error(message)
        raise ValidationError(message) from error


def _role_timings(
        matched: CategoryMatch,
        title: str
) -> List[_RoleTiming]:
    """ Return what each of a category's need IDs asks for.

        A need ID that is empty contributes nothing.  That is what the
        review fallback holds, and what a category with an unfilled
        need ID holds: either way the event creates no shift and stops
        the run, which the caller reports rather than this.

        Args:
            matched (CategoryMatch):
                The category the event's title reached.

            title (str):
                The event's title, for the message when the category
                cannot be stored as one event.

        Raises:
            ValidationError:
                If the category's need IDs disagree about their
                offsets, which one event cannot express.

        Returns:
            timings (List[_RoleTiming]):
                One per need ID that can become a shift.
    """

    timings = [
        _RoleTiming(
            role=EventRole(
                need_id=str(need['id']),
                slots=int(need['slots'])
            ),
            offset_start=int(need.get('offset_start', 0)),
            offset_end=int(need.get('offset_end', 0)),
            max_length=need.get('max_length')
        )
        for need in matched.need_details.get('need_ids', ())
        if str(need.get('id', '')) != ''
    ]

    offsets = {
        (timing.offset_start, timing.offset_end)
        for timing in timings
    }

    if len(offsets) > 1:
        message = (
            f'The "{matched.category}" category, which "{title}" '
            'matched, gives its need IDs different start and end '
            'offsets. An event records one pair of shift times for '
            'every role it serves, so those need IDs describe two '
            'different shifts and cannot be collected as one event. '
            'Give them the same offsets, or split them into separate '
            'categories.'
        )
        logger.error(message)
        raise ValidationError(message)

    return timings


def _shift_times(
        start: datetime,
        end: datetime,
        timings: Sequence[_RoleTiming],
        title: str
) -> Tuple[str, str]:
    """ Return the times the shift an event creates runs between.

        The offsets move the calendar's times, and the opportunity's
        maximum shortens the result when it is longer than the
        opportunity accepts.  The stored times are the ones Amplify is
        given, so the maximum is applied here rather than left for a
        reader to apply.

        Args:
            start (datetime):
                When the event starts, in the league's zone.

            end (datetime):
                When it ends.

            timings (Sequence[_RoleTiming]):
                What its roles ask for.  All of them agree about the
                offsets by the time this is called.

            title (str):
                The event's title, for the messages.

        Raises:
            ValidationError:
                If the offsets leave the shift ending no later than it
                starts, or running past the end of the day.

        Returns:
            times (Tuple[str, str]):
                The shift's start and end, as times of day.
    """

    first = timings[0]
    shift_start = start + timedelta(minutes=first.offset_start)
    shift_end = end + timedelta(minutes=first.offset_end)
    minutes = round((shift_end - shift_start).total_seconds() / 60)

    if minutes <= 0:
        message = (
            f'"{title}" would create a shift ending no later than it '
            f'starts ({minutes} minutes). The offsets on its category '
            'are wrong for this event.'
        )
        logger.error(message)
        raise ValidationError(message)

    # The smallest maximum among the roles is the one that binds, the
    # same way a reader works out which maximum shortened a shift.
    maximums = [
        timing.max_length
        for timing in timings
        if timing.max_length is not None
    ]

    if maximums and minutes > min(maximums):
        minutes = min(maximums)
        shift_end = shift_start + timedelta(minutes=minutes)

    started = shift_start.hour * 60 + shift_start.minute

    if started + minutes >= MINUTES_PER_DAY:
        message = (
            f'"{title}" would create a shift running past the end of '
            'the day. An event stores its times as times of day, so a '
            'shift crossing midnight cannot be read back as the one '
            'that was stored.'
        )
        logger.error(message)
        raise ValidationError(message)

    return (
        shift_start.strftime(SIMPLE_TIME_FORMAT),
        shift_end.strftime(SIMPLE_TIME_FORMAT)
    )


def _event_from(
        item: Dict[str, Any],
        matched: CategoryMatch,
        timezone: ZoneInfo
) -> Event:
    """ Return one calendar item as a revision holds it.

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

    title = item['summary']
    start = _local_moment(
        value=item['start']['dateTime'],
        timezone=timezone
    )
    end = _local_moment(
        value=item['end']['dateTime'],
        timezone=timezone
    )
    timings = _role_timings(matched=matched, title=title)

    # An event serving no opportunity has no shift to time.  It is
    # stored with the calendar's own times, and blocks the run for
    # having no role at all.
    shift_start, shift_end = (
        _shift_times(
            start=start,
            end=end,
            timings=timings,
            title=title
        )
        if timings
        else (
            start.strftime(SIMPLE_TIME_FORMAT),
            end.strftime(SIMPLE_TIME_FORMAT)
        )
    )

    return Event(
        id=item['id'],
        title=title,
        date=start.strftime(ISO_DATE_FORMAT),
        calendar_start=start.strftime(SIMPLE_TIME_FORMAT),
        calendar_end=end.strftime(SIMPLE_TIME_FORMAT),
        shift_start=shift_start,
        shift_end=shift_end,
        category=matched.category,
        match=matched.match,
        roles=tuple(timing.role for timing in timings)
    )


def _opportunity_from(
        need_id: str,
        timing: _RoleTiming,
        title: str
) -> Opportunity:
    """ Return the opportunity a need ID names.

        Args:
            need_id (str):
                Amplify need ID.

            timing (_RoleTiming):
                What the data model says about it.

            title (str):
                What Amplify calls it.

        Returns:
            opportunity (Opportunity):
                The opportunity as the run stores it.
    """

    return Opportunity(
        need_id=need_id,
        title=title,
        url=public_url(need_id=need_id),
        max_length=timing.max_length,
        offset_start=timing.offset_start,
        offset_end=timing.offset_end,
        default_slots=timing.role.slots
    )


def _calendar_items(
        run: Run,
        reporter: Reporter
) -> List[Dict[str, Any]]:
    """ Return the calendar items a run's window holds.

        The calendar is searched once per configured query string and
        the results are concatenated, so an event matching two of them
        arrives twice.  It is one event either way, and the first
        arrival is the one kept: a revision holding it twice would
        show a reviewer two rows for one thing and send Amplify two
        identical shifts.

        Args:
            run (Run):
                The run being collected, which names the calendar and
                the days.

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
            items (List[Dict[str, Any]]):
                The items that can become shifts, without repeats.
    """

    calendar = GCALData(
        gcal_name=run.calendar,
        auto_prep_data=False,
        reporter=reporter
    )
    window_start, window_end = resolve_window(
        start=run.window_start,
        end=run.window_end,
        start_name='the window start',
        end_name='the window end'
    )
    collected = calendar.get_gcal_shift_data(
        timeMin=window_start,
        timeMax=window_end
    )
    filtered = calendar.filter_gcal_items(gcal_shift_data=collected)
    seen: Dict[str, Dict[str, Any]] = {}

    for item in filtered:
        seen.setdefault(item['id'], item)

    return list(seen.values())


def _require_one_timing(
        need_id: str,
        timing: _RoleTiming,
        against: _RoleTiming
) -> None:
    """ Fail when two categories time the same opportunity differently.

        A run stores one opportunity per need ID, so two categories
        sending shifts to one Amplify listing on different offsets
        cannot both be recorded.  Refused rather than resolved by
        whichever event was read first, which would make the answer
        depend on the order the calendar returned.

        Args:
            need_id (str):
                The opportunity both categories name.

            timing (_RoleTiming):
                What this event asks for.

            against (_RoleTiming):
                What an earlier event asked for.

        Raises:
            ValidationError:
                If the two disagree.

        Returns:
            None.
    """

    if (
        timing.offset_start,
        timing.offset_end,
        timing.max_length
    ) != (
        against.offset_start,
        against.offset_end,
        against.max_length
    ):
        message = (
            f'Need ID {need_id} is timed two different ways by the '
            'categories collected in this window. A run records one '
            'set of offsets per opportunity, so the two cannot both '
            'be stored. Give them the same timing, or send them to '
            'different opportunities.'
        )
        logger.error(message)
        raise ValidationError(message)

    return None


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

    reporter.step_started(label='Matching events to opportunities')

    events = []
    timings: Dict[str, _RoleTiming] = {}

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

        for timing in _role_timings(
            matched=matched,
            title=item['summary']
        ):
            need_id = timing.role.need_id

            if need_id in timings:
                _require_one_timing(
                    need_id=need_id,
                    timing=timing,
                    against=timings[need_id]
                )

            timings.setdefault(need_id, timing)

    reporter.step_finished()
    reporter.step_started(label='Reading the Amplify opportunities')

    opportunities = [
        _opportunity_from(
            need_id=need_id,
            timing=timing,
            title=title_of(
                need=read_need(helpers=helpers, need_id=need_id)
            )
        )
        for need_id, timing in sorted(timings.items())
    ]

    reporter.step_finished()

    return events, opportunities


def collect(
        connection: sqlite3.Connection,
        run_id: str,
        reporter: Reporter
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
        from a run whose opportunities Amplify had forgotten.

        Args:
            connection (sqlite3.Connection):
                The database to write to.

            run_id (str):
                Run to collect into.

            reporter (Reporter):
                Where progress is described.

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

    events, opportunities = _collected(
        items=_calendar_items(run=run, reporter=reporter),
        run=run,
        timezone=gcal_timezone(),
        helpers=Helpers(),
        reporter=reporter
    )

    reporter.step_started(label='Storing the collected events')

    with transaction(connection=connection):
        # Replacing, not continuing.  What the calendar says now is
        # the whole of the revision, so carrying the previous events
        # forward would leave behind ones the calendar no longer has.
        revision = RevisionRepository(connection=connection).create(
            run_id=run_id,
            label=(
                FIRST_REVISION_LABEL
                if run.current_revision == 0
                else LATER_REVISION_LABEL
            ),
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
