#!/usr/bin/env python3
""" What the deployment was configured with.

    Read only, and there is no write beside it: a value here is
    changed by changing the environment and restarting, which is what
    keeps the service unable to rewrite the settings it is running on
    (D8).

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
from star_pass_contract import ConfigView, to_config_view
from . import _defaults
from ._security import Principal, requires, SCOPE_CONFIG_READ

router = APIRouter(tags=[_defaults.API_TAG_SERVICE])


@router.get(
    '/config',
    summary='Report what the service was configured with',
    description=(
        'The settings a collection is carried out under, as this '
        'process resolved them at startup. Read only: rotating a '
        'credential or changing a setting is a deployment operation, '
        'and no endpoint writes one (D8).\n\n'
        'This is where a client learns which calendars a collection '
        'may name. Those keys belong to a deployment rather than to '
        'this contract, so a client that hard-coded them would be '
        'describing one installation.'
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

    return to_config_view()
