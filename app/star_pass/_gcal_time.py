#!/usr/bin/env python3
""" Google Calendar search window.

    Reads and validates 'GCAL_TIME_MIN' and 'GCAL_TIME_MAX', the bounds
    of the calendar search.  They have no defaults: the window moves
    with every run, so a default would go stale and silently collect
    zero events.

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
# offset (see 'get_gcal_time_window').
GCAL_TIMEZONE = _defaults.GCAL_TIMEZONE

# Module logger
logger = get_logger(__name__)


def _get_gcal_timezone() -> ZoneInfo:
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


def get_gcal_time_window() -> Tuple[str, str]:
    """ Read and validate the Google Calendar search window.

        'GCAL_TIME_MIN' and 'GCAL_TIME_MAX' bound the calendar search and
        have no default: the window moves with every run, so a default
        would go stale and silently collect zero events.  They are read
        here, when a calendar request is about to run, rather than at
        import time, so the other run modes ('-c' and '-s') do not
        require Google Calendar configuration.

        Each value may be a plain local date or datetime, which is
        interpreted in 'GCAL_TIMEZONE' with the UTC offset in effect on
        that date, so Daylight Saving needs no attention.  A value that
        carries its own offset is honored as written.

        Raises:
            ValueError:
                If either value is unset, unparseable, or the window does
                not move forward in time, or if 'GCAL_TIMEZONE' does not
                name a known time zone.

        Returns:
            window (Tuple[str, str]):
                The validated ('GCAL_TIME_MIN', 'GCAL_TIME_MAX') values
                as RFC 3339 strings with an explicit UTC offset, ready to
                send as request parameters.
    """

    time_min = getenv('GCAL_TIME_MIN')
    time_max = getenv('GCAL_TIME_MAX')

    # Both values are required for a calendar request
    missing = [
        name
        for name, value in (
            ('GCAL_TIME_MIN', time_min),
            ('GCAL_TIME_MAX', time_max)
        )
        if not value
    ]
    if missing:
        message = (
            f'{" and ".join(missing)} must be set to collect Google '
            'Calendar events.  Set the calendar search window in your '
            '.env file (see .env.example); there is no default, because '
            'a stale window silently collects zero events.'
        )
        logger.error(message)
        raise ValueError(message)

    # A malformed value fails the same way a stale one does, silently,
    # so reject it here rather than send it to the API.
    timezone = _get_gcal_timezone()
    parsed_min = _parse_gcal_time(
        name='GCAL_TIME_MIN',
        value=time_min,
        timezone=timezone
    )
    parsed_max = _parse_gcal_time(
        name='GCAL_TIME_MAX',
        value=time_max,
        timezone=timezone
    )

    # Compare the resolved instants, so a window mixing a local value
    # with an offset value is ordered correctly.
    if parsed_min >= parsed_max:
        message = (
            f'GCAL_TIME_MIN ({time_min}) must be earlier than '
            f'GCAL_TIME_MAX ({time_max}); the current values select an '
            'empty search window.'
        )
        logger.error(message)
        raise ValueError(message)

    # Send the resolved values: the API requires an explicit offset, and
    # logging them makes the applied offset visible.
    resolved_min = parsed_min.isoformat()
    resolved_max = parsed_max.isoformat()
    message = (
        f'Google Calendar search window: {resolved_min} to {resolved_max}'
    )
    logger.info(message)

    return resolved_min, resolved_max
