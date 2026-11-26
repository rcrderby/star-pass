#!/usr/bin/env python3
""" What the deployment was configured with.

    Read only, and there is no write beside it: a value here is
    changed by changing the environment and restarting, which is what
    keeps the service unable to rewrite the settings it is running
    on.

    Nothing secret is published.  What a caller is shown is the zone
    dates are read in, the threshold a title match has to clear, the
    terms a title is never collected under, and which calendars a
    collection may name -- every one of them a fact about how a run
    will be collected, and the question they answer is "why did this
    event not become a shift".  The calendar identifiers, the
    credentials and the addresses of the upstream services are not
    part of that answer.
"""

# Imports - Third-Party
from fastapi import APIRouter

# Imports - Local
from star_pass_contract import (
    ConfigView,
    CredentialTestLimitView,
    to_config_view
)
from . import _defaults
from ._security import Principal, requires, SCOPE_CONFIG_READ

router = APIRouter(tags=[_defaults.API_TAG_SERVICE])


@router.get(
    '/config',
    summary='Report what the service was configured with',
    description=(
        'The settings collections use, as the service read them at '
        'startup. To change a setting or a credential, edit its value '
        'in your `.env` file and restart `star-pass`.\n\nLists the '
        'calendars a collection request may name.'
    ),
    response_model=ConfigView
)
async def get_config(
        principal: Principal = requires(SCOPE_CONFIG_READ)
) -> ConfigView:
    """ Return the settings the service is running on.

        Args:
            principal (Principal):
                The authenticated caller, which the dependency supplies
                after checking the scope.

        Returns:
            config (ConfigView):
                What the deployment was configured with.
    """

    del principal

    return to_config_view(
        credential_test_limit=CredentialTestLimitView(
            attempts=_defaults.CREDENTIAL_TEST_ATTEMPTS,
            window_seconds=int(_defaults.CREDENTIAL_TEST_WINDOW_SECONDS)
        )
    )
