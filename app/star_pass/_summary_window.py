#!/usr/bin/env python3
""" Sign-up summary window and date formatting.

    The window bounds which shifts a summary covers: where it starts,
    where it ends, and which of a need's shifts fall inside it.  The
    formatting turns Amplify's naive local datetimes into the labels
    the Slack message shows.

    Amplify reports datetimes as naive local values, so every datetime
    here is naive and directly comparable.
"""

# Imports - Python Standard Library
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# Imports - Local
from . import _defaults
from ._helpers import parse_amplify_datetime
from ._logging import get_logger

# Constants
LOCAL_TIMEZONE = _defaults.LOCAL_TIMEZONE

# Module logger
logger = get_logger(__name__)


def _shift_start_dt(
        shift: Dict[str, Any]
) -> Optional[datetime]:
    """ Return a shift's start as a datetime, or None when unparseable.

        Args:
            shift (Dict[str, Any]):
                Shift object with a 'start' datetime string.

        Returns:
            start (datetime | None):
                The parsed start datetime, or None.
    """

    return parse_amplify_datetime((shift or {}).get('start'))


def _response_created_dt(
        response: Dict[str, Any]
) -> Optional[datetime]:
    """ Return a response's creation datetime, or None.

        The live API returns 'created_at'; the documented schema names
        this field 'response_date_added'.  Either is accepted.

        Args:
            response (Dict[str, Any]):
                An Amplify response object.

        Returns:
            created (datetime | None):
                The parsed creation datetime, or None.
    """

    raw = response.get('created_at') or response.get('response_date_added')

    return parse_amplify_datetime(raw)


def local_now() -> datetime:
    """ Return the current local wall-clock time, without a time zone.

        The host clock cannot be trusted to be local: a container or a
        CI runner usually runs in UTC, where a Portland evening is
        already the next calendar day.  Reading 'now' in UTC would move
        a same-day summary onto the wrong day entirely, not just
        mislabel it.

        Amplify reports shift times as naive local datetimes, so the
        result is made naive too and stays directly comparable.

        Raises:
            ValueError:
                If 'LOCAL_TIMEZONE' does not name a known time zone.

        Returns:
            now (datetime):
                The current time in 'LOCAL_TIMEZONE', without tzinfo.
    """

    # 'ZoneInfoNotFoundError' subclasses KeyError, which reads as a
    # missing dictionary key rather than a configuration error.
    try:
        timezone = ZoneInfo(LOCAL_TIMEZONE)
    except (ZoneInfoNotFoundError, ValueError) as error:
        message = (
            f'LOCAL_TIMEZONE is not a known time zone: '
            f'{LOCAL_TIMEZONE!r}.  Use an IANA name such as '
            'America/Los_Angeles.'
        )
        logger.error(message)
        raise ValueError(message) from error

    return datetime.now(tz=timezone).replace(tzinfo=None)


def _window_end(
        now: datetime,
        days: int
) -> datetime:
    """ Return the last instant of a summary window.

        The window's first day is day one, so 'days=1' ends at the last
        instant of that day and 'days=2' ends at the last instant of the
        day after it.

        Args:
            now (datetime):
                Start of the window; its calendar date is day one.

            days (int):
                Number of calendar days to cover, one or greater.

        Raises:
            ValueError:
                If 'days' is less than one.

        Returns:
            window_end (datetime):
                The last instant of the final day in the window.
    """

    if days < 1:
        raise ValueError(
            f'Summary window must cover at least one day, got {days}.'
        )

    last_day = now + timedelta(days=days - 1)

    return last_day.replace(
        hour=23,
        minute=59,
        second=59,
        microsecond=999999
    )


def _window_start(
        now: datetime,
        start_in_days: int
) -> datetime:
    """ Return the first instant of a summary window.

        A window starting today begins at 'now', so shifts already
        under way are left out.  A window starting later begins at
        midnight of that day, so it carries the whole day.

        Args:
            now (datetime):
                Reference time; day zero of the offset.

            start_in_days (int):
                Days between 'now' and the window's first day.  Zero
                starts today.

        Raises:
            ValueError:
                If 'start_in_days' is negative.

        Returns:
            window_start (datetime):
                The first instant the window covers.
    """

    if start_in_days < 0:
        raise ValueError(
            'Summary window cannot start in the past, got '
            f'{start_in_days}.'
        )

    if start_in_days == 0:
        return now

    return (now + timedelta(days=start_in_days)).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0
    )


def _upcoming_shifts(
        shifts: List[Dict[str, Any]],
        now: datetime,
        window_end: datetime
) -> List[Dict[str, Any]]:
    """ Select the shifts starting inside the window, ordered by start.

        A long-lived need accumulates hundreds of past shifts that a
        sign-up summary should not repeat, and a summary is a call for
        volunteers over the next day or few, not a full backlog.  Shifts
        that already started are excluded, as are shifts with an
        unparseable start.

        Args:
            shifts (List[Dict[str, Any]]):
                Shift objects from a need.

            now (datetime):
                Start of the window; shifts before this are past.

            window_end (datetime):
                End of the window (see '_window_end').

        Returns:
            upcoming (List[Dict[str, Any]]):
                The shifts inside the window, earliest first.
    """

    dated = []
    for shift in shifts:
        start_dt = _shift_start_dt(shift=shift)
        if start_dt is not None and now <= start_dt <= window_end:
            dated.append((start_dt, shift))
    dated.sort(key=lambda pair: pair[0])

    return [shift for _start_dt, shift in dated]


def _window_title(
        now: datetime,
        window_end: datetime
) -> str:
    """ Build a default summary title describing the window.

        Args:
            now (datetime):
                Start of the window.

            window_end (datetime):
                End of the window (see '_window_end').

        Returns:
            title (str):
                A title naming the window's date, or its date range when
                the window covers more than one day.
    """

    start_label = _format_long_date(value=now)
    end_label = _format_long_date(value=window_end)

    if start_label == end_label:
        return f'Shift sign-ups for {start_label}'

    return f'Shift sign-ups for {start_label} - {end_label}'


def _format_long_date(
        value: datetime
) -> str:
    """ Format a date the way it would be written by hand.

        The day is not zero padded and the year is set off by a comma,
        so a heading reads 'Monday, August 3, 2026'.  The day is
        inserted directly rather than through a '%-d' directive, which
        is not supported on Windows.

        Args:
            value (datetime):
                The date to format.

        Returns:
            date (str):
                The weekday, month, day, and year.
    """

    return f'{value.strftime("%A, %B")} {value.day}, {value.year}'


def _format_short_date(
        value: datetime
) -> str:
    """ Format a date heading within a summary, without the year.

        The summary title already carries the year, so a day heading
        reads 'Wednesday, August 5'.

        Args:
            value (datetime):
                The date to format.

        Returns:
            date (str):
                The weekday, month, and day.
    """

    return f'{value.strftime("%A, %B")} {value.day}'


def _format_clock(
        value: datetime
) -> str:
    """ Format a time the way the sign-up posts are written by hand.

        Args:
            value (datetime):
                The time to format.

        Returns:
            clock (str):
                A 12-hour time with no leading zero, such as
                '6:00 p.m.'.
    """

    hour = value.strftime('%I').lstrip('0') or '12'
    meridiem = 'a.m.' if value.hour < 12 else 'p.m.'

    return f'{hour}:{value.strftime("%M")} {meridiem}'


def _format_time_range(
        start_dt: datetime,
        end_dt: datetime
) -> str:
    """ Format a shift's start and end as a single time range.

        The meridiem is written once when both ends share it, matching
        how the posts read ('6:00-7:00 p.m.').

        Args:
            start_dt (datetime):
                Shift start.

            end_dt (datetime):
                Shift end.

        Returns:
            when (str):
                A formatted time range.
    """

    start = _format_clock(value=start_dt)
    end = _format_clock(value=end_dt)

    # Drop the repeated meridiem from the start of a same-half range
    if start.rsplit(' ', 1)[-1] == end.rsplit(' ', 1)[-1]:
        start = start.rsplit(' ', 1)[0]

    return f'{start}-{end}'


def _format_slot_when(
        shift: Dict[str, Any]
) -> str:
    """ Format the time label for one shift line.

        The date is not included: a day's shifts are shown under a date
        heading, so repeating it on every line would be noise.

        Args:
            shift (Dict[str, Any]):
                Shift object with 'start' and 'end' datetime strings.

        Returns:
            when (str):
                A time range.  Falls back to the raw start value when
                parsing fails.
    """

    start_dt = parse_amplify_datetime(shift.get('start'))
    end_dt = parse_amplify_datetime(shift.get('end'))

    if start_dt is None or end_dt is None:
        return shift.get('start') or 'Time TBD'

    return _format_time_range(start_dt=start_dt, end_dt=end_dt)


def _format_day_heading(
        shift: Dict[str, Any]
) -> str:
    """ Format the date heading a shift belongs under.

        Args:
            shift (Dict[str, Any]):
                Shift object with a 'start' datetime string.

        Returns:
            day (str):
                The shift's date.  Empty when the start cannot be
                parsed, which keeps an unreadable shift out of a day
                heading of its own.
    """

    start_dt = _shift_start_dt(shift=shift)

    if start_dt is None:
        return ''

    return _format_short_date(value=start_dt)
