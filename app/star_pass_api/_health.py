#!/usr/bin/env python3
""" Whether the service is up.

    The one endpoint that answers without a credential, because what
    asks it is a container runtime or a proxy deciding whether to send
    traffic here, and neither holds one.

    It reports that this process is serving and nothing else.  A check
    that read the database or called Amplify would tell an
    unauthenticated caller which of the service's dependencies are
    down, and would take the service out of rotation for a fault that
    restarting it cannot fix.
"""

# Imports - Third-Party
from fastapi import APIRouter
from pydantic import BaseModel, Field

# Imports - Local
from ._defaults import API_TAG_SERVICE

# Constants
HEALTH_STATUS_OK = 'ok'

router = APIRouter(tags=[API_TAG_SERVICE])


class Health(BaseModel):
    """ The service's answer about itself. """

    status: str = Field(
        description='Always "ok": a reply at all is the health report.',
        examples=[HEALTH_STATUS_OK]
    )


@router.get(
    '/health',
    summary='Report that the service is serving',
    description=(
        'Answers without authentication, for a container runtime or a '
        'proxy deciding whether to route to this process. It reports '
        'that the process is serving and does not check the database '
        'or any upstream service.'
    ),
    response_model=Health
)
async def get_health() -> Health:
    """ Return the service's status.

        Args:
            None.

        Returns:
            health (Health):
                The status, which is always 'ok' when this replies.
    """

    return Health(status=HEALTH_STATUS_OK)
