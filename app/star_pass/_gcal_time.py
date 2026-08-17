#!/usr/bin/env python3
""" Google Calendar search window.

    Reads and validates the bounds of a calendar search.  A run carries
    its own window, so the bounds arrive as arguments rather than from
    the environment: a window that moves with every run has no default
    that would not go stale and silently collect zero events.

    A bound written without a UTC offset is local time in
    'GCAL_TIMEZONE', which is what makes Daylight Saving automatic.
"""

# Imports - Python Standard Library
from datetime import datetime
from os import getenv
from typing import Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# Imports - Local
from . import _defaults
from ._logging import get_logger

# Time zone applied to a search window value written without a UTC
# offset (see 'resolve_window').
GCAL_TIMEZONE = _defaults.GCAL_TIMEZONE

# Module logger
logger = get_logger(__name__)


def gcal_timezone() -> ZoneInfo:
    """ Read the time zone applied to offset-less window values.

        Raises:
            ValueError:
                If 'GCAL_TIMEZONE' does not name a known time zone.

        Returns:
            timezone (ZoneInfo):
                The configured time zone.
    """

    name = getenv('GCAL_TIMEZONE', GCAL_TIMEZONE)

    # 'ZoneInfoNotFoundError' subclasses KeyError, which reads as a
    # missing dictionary key rather than a configuration error.
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as error:
        message = (
            f'GCAL_TIMEZONE is not a known time zone: {name!r}.  Use an '
            'IANA name such as America/Los_Angeles.'
        )
        logger.error(message)
        raise ValueError(message) from error


def _parse_gcal_time(
        name: str,
        value: str,
        timezone: ZoneInfo
) -> datetime:
    """ Parse a calendar search window value.

        A value without a UTC offset is a local time, and is placed in
        'timezone'.  That is what makes Daylight Saving automatic: the
        zone supplies the offset in effect on that date, so the same
        plain date means midnight local time in both January and July.
        A value that carries its own offset is honored as written.

        Args:
            name (str):
                Environment variable name, for the error message.

            value (str):
                An ISO 8601 date or datetime.  Examples: '2099-01-01',
                '2099-01-01T00:00', '2099-01-01T00:00:00-08:00'.

            timezone (ZoneInfo):
                Time zone applied when 'value' has no UTC offset.

        Raises:
            ValueError:
                If 'value' is not a valid ISO 8601 date or datetime.

        Returns:
            parsed (datetime):
                The parsed, time zone aware datetime.
    """

    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as error:
        message = (
            f'{name} is not a valid date and time: {value!r}.  Use a '
            'local date such as 2099-01-01, or an ISO 8601 datetime '
            'such as 2099-01-01T00:00:00-08:00.'
        )
        logger.error(message)
        raise ValueError(message) from error

    # An offset-less value is local time in the configured zone.  A
    # local time inside a Daylight Saving transition is resolved rather
    # than rejected; window bounds are whole dates in practice, and the
    # transitions happen at 02:00.
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone)

    return parsed


def resolve_window(
        start: str,
        end: str,
        start_name: str,
        end_name: str
) -> Tuple[str, str]:
    """ Return a search window as the values a request carries.

        Below both callers: the environment supplies one window and a
        request supplies another, and a window read one way and one
        read the other must select the same days.  Only where the two
        values come from differs, which is why that is all the caller
        above decides.

        Args:
            start (str):
                First moment the window covers, as an ISO 8601 date or
                datetime.

            end (str):
                Moment the window stops covering, exclusive.

            start_name (str):
                What to call the first value in a message, so a reader
                is told which of theirs is wrong.

            end_name (str):
                What to call the second value in a message.

        Raises:
            ValueError:
                If either value cannot be read, if the window does not
                move forward in time, or if 'GCAL_TIMEZONE' does not
                name a known time zone.

        Returns:
            window (Tuple[str, str]):
                The two values as ISO 8601 strings with an explicit UTC
                offset, ready to send as request parameters.
    """

    # A malformed value fails the same way a stale one does, silently,
    # so reject it here rather than send it to the API.
    timezone = gcal_timezone()
    parsed_start = _parse_gcal_time(
        name=start_name,
        value=start,
        timezone=timezone
    )
    parsed_end = _parse_gcal_time(
        name=end_name,
        value=end,
        timezone=timezone
    )

    # Compare the resolved instants, so a window mixing a local value
    # with an offset value is ordered correctly.
    if parsed_start >= parsed_end:
        message = (
            f'{start_name} ({start}) must be earlier than '
            f'{end_name} ({end}); the current values select an '
            'empty search window.'
        )
        logger.error(message)
        raise ValueError(message)

    # Send the resolved values: the API requires an explicit offset, and
    # logging them makes the applied offset visible.
    resolved_start = parsed_start.isoformat()
    resolved_end = parsed_end.isoformat()
    message = (
        f'Google Calendar search window: {resolved_start} to {resolved_end}'
    )
    logger.info(message)

    return resolved_start, resolved_end
