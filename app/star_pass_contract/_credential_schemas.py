#!/usr/bin/env python3
""" The shapes a credential test answers with.

    Whether Amplify takes the credential this service runs on, and
    whether each League Calendar takes its key.  A module of its own
    beside '_schemas.py', which is at the thousand-line cap the linter
    holds a module to.

    Read back into '_schemas.py' by nothing.  A caller reaches them
    through the package.
"""

# Imports - Python Standard Library
from typing import List, Optional

# Imports - Third-Party
from pydantic import Field

# Imports - Local
from ._schemas import ApiModel


class CredentialView(ApiModel):
    """ What asking Amplify about the service's credential answered. """

    working: bool = Field(
        description=(
            'Whether Amplify accepted a request carrying the '
            'credential this service is running on. False also covers '
            'a credential that is not configured at all, and the '
            'reason says which.'
        ),
        examples=[True]
    )
    last_four: Optional[str] = Field(
        default=None,
        description=(
            'The last four characters of the credential, which is '
            'enough to tell two apart and no use to whoever reads it. '
            'The credential itself is never published, and no '
            'endpoint replaces it: rotation is changing the secret '
            'and restarting. Absent when none is configured.'
        ),
        examples=['4f2a']
    )
    reason: Optional[str] = Field(
        default=None,
        description=(
            'Why the credential did not work, written for a person. '
            'Absent when it did.'
        ),
        examples=[None]
    )


class CalendarAccessView(ApiModel):
    """ What one configured calendar answered to the key. """

    calendar: str = Field(
        description='Which configured calendar was read.',
        examples=['events']
    )
    working: bool = Field(
        description='Whether a read of it carrying the key succeeded.',
        examples=[True]
    )
    reason: Optional[str] = Field(
        default=None,
        description=(
            'Why the read did not succeed, written for a person. '
            'Absent when it did.'
        ),
        examples=[None]
    )


class CalendarCredentialView(ApiModel):
    """ What asking the League Calendar about the key answered. """

    working: bool = Field(
        description=(
            'Whether every configured calendar accepted a read '
            'carrying the key this service is running on. False also '
            'covers a key that is not configured at all, and the '
            'reason says which.'
        ),
        examples=[True]
    )
    last_four: Optional[str] = Field(
        default=None,
        description=(
            'The last four characters of the key, which is enough to '
            'tell two apart and no use to whoever reads it. The key '
            'itself is never published, and no endpoint replaces it: '
            'rotation is changing the secret and restarting. Absent '
            'when none is configured.'
        ),
        examples=['9c1e']
    )
    reason: Optional[str] = Field(
        default=None,
        description=(
            'Why no calendar was read, written for a person. Absent '
            'when the calendars were read, and each one\'s own reason '
            'is under calendars.'
        ),
        examples=[None]
    )
    calendars: List[CalendarAccessView] = Field(
        description=(
            'What each configured calendar answered, in the order '
            'they are configured. Empty when no calendar was read.'
        )
    )
