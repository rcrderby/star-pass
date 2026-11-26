#!/usr/bin/env python3
""" Testing the credentials the service runs on, and nothing else.

    The whole of what the API says about its own credentials: the
    Amplify credential and the League Calendar key.  There is no
    endpoint that replaces one: rotation is changing the secret and
    restarting, because an endpoint able to overwrite the service's
    own production credential is the highest-value target in the
    system for the least benefit.

    What a caller gets is whether a request carrying it succeeded and
    the last four characters, which is enough to tell two credentials
    apart and no use to whoever reads it.

    **Rate-limited**, which is the point of the endpoint being small.
    Something that reports a true fact about a secret is worth asking
    rarely, and every attempt spends a request on somebody else's
    service; a person clicking Test in Settings needs a handful in a
    minute and nothing needs more.  The limit is per caller, counted
    in this process, and refusing costs nothing upstream.
"""

# Imports - Third-Party
from fastapi import APIRouter
from starlette.concurrency import run_in_threadpool

# Imports - Local
from star_pass._credentials import (
    check_calendar_credential,
    check_credential
)
from star_pass_contract import (
    CalendarCredentialView,
    CredentialView,
    to_calendar_credential_view,
    to_credential_view
)
from . import _defaults
from ._limiting import RateLimit
from ._problems import too_many
from ._security import Principal, requires, SCOPE_CONFIG_READ

router = APIRouter(tags=[_defaults.API_TAG_SERVICE])


def per_window(seconds: float) -> str:
    """ Name a rate limit's window, such as 'minute' or '30 seconds'.

        Args:
            seconds (float):
                The window's length.

        Returns:
            window (str):
                The window, worded to follow "per".
    """

    whole = int(seconds)

    if whole == 60:
        return 'minute'

    if whole % 60 == 0:
        return f'{whole // 60} minutes'

    return f'{whole} seconds'


# What a caller is told when they have asked too often.  The
# Retry-After header says when to ask again.
TOO_OFTEN = (
    'Maximum test attempts exceeded '
    f'({_defaults.CREDENTIAL_TEST_ATTEMPTS} per '
    f'{per_window(_defaults.CREDENTIAL_TEST_WINDOW_SECONDS)}).'
)

# The counts themselves, which live as long as the process does.  One
# per credential, so testing one does not spend the other's allowance.
TESTS = RateLimit(
    allowed=_defaults.CREDENTIAL_TEST_ATTEMPTS,
    window_seconds=_defaults.CREDENTIAL_TEST_WINDOW_SECONDS
)
CALENDAR_TESTS = RateLimit(
    allowed=_defaults.CREDENTIAL_TEST_ATTEMPTS,
    window_seconds=_defaults.CREDENTIAL_TEST_WINDOW_SECONDS
)


def claim_or_refuse(
        limit: RateLimit,
        principal: Principal
) -> None:
    """ Count one test against a caller, or refuse it.

        Args:
            limit (RateLimit):
                The allowance the test is counted against.

            principal (Principal):
                The caller it is counted for.

        Raises:
            HTTPException:
                429 when this caller has asked too often.
    """

    wait = limit.claim(caller=principal.id)

    if wait is not None:
        raise too_many(
            detail=TOO_OFTEN,
            # Rounded up: a client told to wait for the whole seconds
            # left would arrive while the window still holds the
            # attempt that filled it.
            retry_after=int(wait) + 1
        )


@router.post(
    '/credentials/test',
    summary='Test the Amplify credential this service is running on',
    description=(
        'Sends one read request to Amplify, and indicates whether or '
        'not Amplify accepted the token. The token\'s last four '
        'characters are visible in the response. To change the token, '
        'edit its value in your `.env` file and restart '
        '`star-pass`.\n\nA refused token is a result, not an '
        'application error.\n\nThe API rate limits this test per '
        'caller. A request over the limit receives a `429` with a '
        '`Retry-After` header, and does not reach Amplify.\n\nStores '
        'no data and takes no idempotency key.'
    ),
    response_model=CredentialView
)
async def test_credential(
        principal: Principal = requires(SCOPE_CONFIG_READ)
) -> CredentialView:
    """ Report whether Amplify accepts the configured credential.

        Args:
            principal (Principal):
                The authenticated caller, which the dependency
                supplies after checking the scope.  Also what the
                limit is counted against.

        Raises:
            HTTPException:
                429 when this caller has asked too often.

        Returns:
            checked (CredentialView):
                Whether it works, and its last four characters.
    """

    claim_or_refuse(limit=TESTS, principal=principal)

    return to_credential_view(
        # On a worker thread, because it waits on Amplify, and the
        # event loop is what every other request is being served on.
        checked=await run_in_threadpool(check_credential)
    )


@router.post(
    '/credentials/calendar/test',
    summary='Test the League Calendar key this service is running on',
    description=(
        'Reads one event from each configured calendar, and indicates '
        'whether or not each read was successful. The key\'s last four '
        'characters are visible in the response. To change the key, '
        'edit its value in your `.env` file and restart '
        '`star-pass`.\n\nEach calendar produces its own result because '
        'Google\'s API may successfully authenticate a key and '
        'determine the key is not authorized for a calendar. A refused '
        'key is a result, not an error.\n\nThe API rate limits this '
        'test per caller, separately from the Amplify test. A request '
        'over the limit receives a `429` with a `Retry-After` header, '
        'and does not reach Google.\n\nStores no data and takes no '
        'idempotency key.'
    ),
    response_model=CalendarCredentialView
)
async def test_calendar_credential(
        principal: Principal = requires(SCOPE_CONFIG_READ)
) -> CalendarCredentialView:
    """ Report whether each calendar accepts the configured key.

        Args:
            principal (Principal):
                The authenticated caller, which the dependency
                supplies after checking the scope.  Also what the
                limit is counted against.

        Raises:
            HTTPException:
                429 when this caller has asked too often.

        Returns:
            checked (CalendarCredentialView):
                Whether each calendar accepts it, and its last four
                characters.
    """

    claim_or_refuse(limit=CALENDAR_TESTS, principal=principal)

    return to_calendar_credential_view(
        # On a worker thread, because it waits on Google.
        checked=await run_in_threadpool(check_calendar_credential)
    )
