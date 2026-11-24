#!/usr/bin/env python3
""" Asking Amplify and the League Calendar whether the credentials
    this process holds still work.

    The answer is whether a request carrying the credential succeeded,
    plus its last four characters.  Never more of the credential, and
    nothing about the account it belongs to.  No endpoint replaces a
    credential: rotation is changing the secret and restarting.

    The Amplify request is a one-row read of what Amplify already
    holds.  The League Calendar request is a one-event read of each
    configured calendar, and each calendar answers on its own.  Both
    bodies are discarded unread.
"""

# Imports - Python Standard Library
from dataclasses import dataclass
from os import getenv
from typing import Optional, Tuple

# Imports - Local
from . import _defaults
from ._exceptions import UpstreamError
from ._helpers import amplify_headers, Helpers
from ._logging import get_logger

# Constants
BASE_AMPLIFY_URL = _defaults.BASE_AMPLIFY_URL
BASE_GCAL_ENDPOINT = _defaults.BASE_GCAL_ENDPOINT
BASE_GCAL_URL = _defaults.BASE_GCAL_URL
HTTP_TIMEOUT = _defaults.HTTP_TIMEOUT

# Where each credential comes from.  Named here rather than read from
# '_defaults', which holds no secret.
CREDENTIAL_VARIABLE = 'AMPLIFY_TOKEN'
CALENDAR_CREDENTIAL_VARIABLE = 'GCAL_TOKEN'

# How much of a credential may be shown.  Enough to tell two apart at
# a glance, and no use to whoever reads it.
VISIBLE_CHARACTERS = 4

# The read the check is made with, and the smallest one there is:
# active rows only, one of them, and the body discarded.
CHECK_PATH = 'responses'
CHECK_PARAMETERS = {
    'per_page': 1,
    'show_inactive': 'No'
}

# The calendar read: one event, and the body discarded.  The key is
# added at the call, so this holds no secret.
CALENDAR_CHECK_PARAMETERS = {
    'maxResults': 1
}

# What is said when nothing was configured, rather than sending
# "Bearer None" and reporting what Amplify made of it.
NOT_CONFIGURED = (
    f'No Amplify token. Configure the {CREDENTIAL_VARIABLE} environment '
    'variable and restart the application.'
)

# The same for the League Calendar key, and for a calendar with no
# identifier to read.
CALENDAR_NOT_CONFIGURED = (
    f'No League Calendar key. Configure the {CALENDAR_CREDENTIAL_VARIABLE} '
    'environment variable and restart the application.'
)
CALENDAR_ID_NOT_CONFIGURED = (
    'This calendar has no ID. Set the appropriate environment variable '
    'and restart the application.'
)

# Module logger
logger = get_logger(__name__)


@dataclass(frozen=True)
class CredentialCheck:
    """ What asking Amplify about the credential answered.

        Attributes:
            working (bool):
                Whether Amplify accepted a request carrying it.

            last_four (str | None):
                The last four characters of the credential, or None
                when there is none to show.

            reason (str | None):
                Why it did not work, written for a person, or None
                when it did.
    """

    working: bool
    last_four: Optional[str]
    reason: Optional[str]


def check_credential(
        timeout: int = HTTP_TIMEOUT
) -> CredentialCheck:
    """ Ask Amplify whether the configured credential is accepted.

        A failed request is reported as an answer rather than raised.
        "Amplify would not take it" is what was asked about, and the
        reason is one of the core's own messages, which is written for
        a person and has already been through redaction.

        Args:
            timeout (int, optional):
                How long to wait for Amplify.  Defaults to the
                configured value.

        Returns:
            checked (CredentialCheck):
                Whether it works, its last four characters, and why
                not when it does not.
    """

    credential = getenv(CREDENTIAL_VARIABLE)

    if not credential:
        logger.error(NOT_CONFIGURED)

        return CredentialCheck(
            working=False,
            last_four=None,
            reason=NOT_CONFIGURED
        )

    shown = credential[-VISIBLE_CHARACTERS:]

    try:
        Helpers().send_api_request(
            api_request_data={
                'method': 'GET',
                'url': f'{BASE_AMPLIFY_URL}/{CHECK_PATH}',
                'headers': amplify_headers(),
                'json': None,
                'timeout': timeout,
                'params': dict(CHECK_PARAMETERS)
            },
            display_request_status=False
        )

    except UpstreamError as error:
        return CredentialCheck(
            working=False,
            last_four=shown,
            reason=str(error)
        )

    message = f'The credential ending {shown} was accepted by Amplify'
    logger.info(message)

    return CredentialCheck(
        working=True,
        last_four=shown,
        reason=None
    )


@dataclass(frozen=True)
class CalendarAccess:
    """ What one configured calendar answered to the key.

        Attributes:
            calendar (str):
                The configured calendar's name, such as 'events'.

            working (bool):
                Whether a read of it carrying the key succeeded.

            reason (str | None):
                Why it did not, written for a person, or None when it
                did.
    """

    calendar: str
    working: bool
    reason: Optional[str]


@dataclass(frozen=True)
class CalendarCredentialCheck:
    """ What asking the League Calendar about the key answered.

        Attributes:
            working (bool):
                Whether every configured calendar accepted it.

            last_four (str | None):
                The last four characters of the key, or None when
                there is none to show.

            reason (str | None):
                Why nothing was asked, written for a person, or None
                when the calendars were asked.

            calendars (Tuple[CalendarAccess, ...]):
                What each configured calendar answered, in the order
                they are configured.  Empty when nothing was asked.
    """

    working: bool
    last_four: Optional[str]
    reason: Optional[str]
    calendars: Tuple[CalendarAccess, ...]


def check_calendar(
        calendar: str,
        gcal_id: Optional[str],
        key: str,
        timeout: int
) -> CalendarAccess:
    """ Ask one calendar whether it accepts the key.

        A failed request is reported as an answer rather than raised,
        for the reason 'check_credential' gives.  The reason has been
        through redaction, which removes the key from the request
        address it quotes.

        Args:
            calendar (str):
                The configured calendar's name.

            gcal_id (str | None):
                Its identifier, or None when none is configured.

            key (str):
                The key to read it with.

            timeout (int):
                How long to wait for the calendar.

        Returns:
            access (CalendarAccess):
                Whether the read succeeded, and why not when it did
                not.
    """

    if not gcal_id:
        return CalendarAccess(
            calendar=calendar,
            working=False,
            reason=CALENDAR_ID_NOT_CONFIGURED
        )

    try:
        Helpers().send_api_request(
            api_request_data={
                'method': 'GET',
                'url': f'{BASE_GCAL_URL}/{gcal_id}{BASE_GCAL_ENDPOINT}',
                'headers': dict(_defaults.BASE_HEADERS),
                'json': None,
                'timeout': timeout,
                'params': {**CALENDAR_CHECK_PARAMETERS, 'key': key}
            },
            display_request_status=False
        )
    except UpstreamError as error:
        return CalendarAccess(
            calendar=calendar,
            working=False,
            reason=str(error)
        )

    return CalendarAccess(calendar=calendar, working=True, reason=None)


def check_calendar_credential(
        timeout: int = HTTP_TIMEOUT
) -> CalendarCredentialCheck:
    """ Ask each configured calendar whether the key is accepted.

        Args:
            timeout (int, optional):
                How long to wait for each calendar.  Defaults to the
                configured value.

        Returns:
            checked (CalendarCredentialCheck):
                Whether every calendar accepts it, its last four
                characters, and what each calendar answered.
    """

    key = getenv(CALENDAR_CREDENTIAL_VARIABLE)

    if not key:
        logger.error(CALENDAR_NOT_CONFIGURED)

        return CalendarCredentialCheck(
            working=False,
            last_four=None,
            reason=CALENDAR_NOT_CONFIGURED,
            calendars=()
        )

    shown = key[-VISIBLE_CHARACTERS:]
    calendars = tuple(
        check_calendar(
            calendar=name,
            gcal_id=settings['gcal_id'],
            key=key,
            timeout=timeout
        )
        for name, settings in _defaults.GCAL_CALENDARS.items()
    )
    working = bool(calendars) and all(
        access.working for access in calendars
    )

    accepted = sum(access.working for access in calendars)
    message = (
        f'The League Calendar key ending {shown} was accepted by '
        f'{accepted} of {len(calendars)} '
        f'{"calendar" if len(calendars) == 1 else "calendars"}'
    )
    logger.info(message)

    return CalendarCredentialCheck(
        working=working,
        last_four=shown,
        reason=None,
        calendars=calendars
    )
