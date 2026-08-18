#!/usr/bin/env python3
""" Asking Amplify whether the credential this process holds still works.

    The one thing the tool publishes about its own credential, and
    deliberately the only one: no endpoint replaces it, because an
    endpoint that could rewrite the service's own production
    credential is the highest-value target in the system for the least
    benefit (D8).  Rotation is changing the secret and restarting.

    So what is left is the question an operator actually asks -- "is
    the thing I set still good?" -- and the answer is **whether a
    request carrying it succeeded**, plus the last four characters,
    which is enough to tell two credentials apart without carrying
    either.  Never the credential, never any part of it but those
    four, and nothing about the account it belongs to.

    The request is a one-row read of what Amplify already holds.  It
    has to be a request Amplify authenticates, or the answer would say
    nothing; it must create nothing; and it must not depend on the
    data model, because a deployment whose model matched no need would
    then be told its credential was broken.  The row that comes back
    is discarded unread: what is being asked is whether the request
    was allowed, not what it returned.
"""

# Imports - Python Standard Library
from dataclasses import dataclass
from os import getenv
from typing import Optional

# Imports - Local
from . import _defaults
from ._exceptions import UpstreamError
from ._helpers import amplify_headers, Helpers
from ._logging import get_logger

# Constants
BASE_AMPLIFY_URL = _defaults.BASE_AMPLIFY_URL
HTTP_TIMEOUT = _defaults.HTTP_TIMEOUT

# Where the credential comes from.  Named here rather than read from
# '_defaults', which holds no secret: the value is read when a request
# is about to be made, so a deployment that rotates it and restarts
# the process sends the current one.
CREDENTIAL_VARIABLE = 'AMPLIFY_TOKEN'

# How much of a credential may be shown.  Enough to tell two apart at
# a glance, and short enough to be no use to whoever reads it (D8).
VISIBLE_CHARACTERS = 4

# The read the check is made with, and the smallest one there is:
# active rows only, one of them, and the body discarded.
CHECK_PATH = 'responses'
CHECK_PARAMETERS = {
    'per_page': 1,
    'show_inactive': 'No'
}

# What is said when nothing was configured.  A request would be sent
# as "Bearer None" and refused, which is a true answer arrived at the
# expensive way and a confusing one to read.
NOT_CONFIGURED = (
    f'No {CREDENTIAL_VARIABLE} is configured, so there is nothing to '
    'test. It is set in the environment and read at startup.'
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
