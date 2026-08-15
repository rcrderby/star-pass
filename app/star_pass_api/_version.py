#!/usr/bin/env python3
""" Which version of star-pass is serving.

    Behind authentication, unlike the health endpoint.  Health has to
    answer a proxy that holds no credential; a version number answers
    nobody's question but an operator's, and telling an unauthenticated
    caller exactly which release is running hands them the list of
    which published faults apply to it.
"""

# Imports - Third-Party
from fastapi import APIRouter
from pydantic import BaseModel, Field

# Imports - Local
from . import _defaults
from ._security import Principal, requires, SCOPE_CONFIG_READ

router = APIRouter(tags=[_defaults.API_TAG_SERVICE])


class Version(BaseModel):
    """ The running version of the application. """

    version: str = Field(
        description='The star-pass release this service is running.',
        examples=[_defaults.API_VERSION]
    )


@router.get(
    '/version',
    summary='Report the running version',
    response_model=Version
)
async def get_version(
        principal: Principal = requires(SCOPE_CONFIG_READ)
) -> Version:
    """ Return the running version.

        Args:
            principal (Principal):
                The authenticated caller, which the dependency supplies
                after checking the scope.

        Returns:
            version (Version):
                The version of the application that is serving.
    """

    del principal

    return Version(version=_defaults.API_VERSION)
