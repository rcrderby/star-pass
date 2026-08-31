#!/usr/bin/env python3
""" Which of the two modes a command runs in.

    Local by default and remote only when told.  The command line
    client must not acquire a server as a dependency, so nothing here
    reaches for one unless an address was supplied -- and the default
    path opens a database rather than a socket.

    The address may come from a flag or from the environment, and the
    flag wins.  A flag is what somebody types for one command; the
    environment is what a shell carries for a session, and the more
    specific of the two is the one they meant.
"""

# Imports - Python Standard Library
from os import getenv
from typing import Optional, Union

# Imports - Local
from star_pass._exceptions import ConfigurationError
from star_pass._logging import get_logger
from star_pass_client import Client, LocalClient

# Constants
# Where a service is, when one is being used at all.
API_URL_VARIABLE = 'STAR_PASS_API_URL'

# What the client presents to it.  The same value the service checks
# against: one principal holds every scope while the credential is a
# static token, so there is no second value to carry.
API_TOKEN_VARIABLE = 'STAR_PASS_API_TOKEN'  # nosec B105

# Module logger
logger = get_logger(__name__)


def service_url(
        supplied: Optional[str] = None
) -> Optional[str]:
    """ Return the address of the service to use, if any.

        Args:
            supplied (str, optional):
                What the command line asked for.  Defaults to None,
                which falls back to the environment.

        Returns:
            url (str | None):
                Where the service is, or None to work locally.
    """

    return supplied or getenv(API_URL_VARIABLE) or None


def client_for(
        api_url: Optional[str] = None
) -> Union[Client, LocalClient]:
    """ Return the client a command should ask.

        Args:
            api_url (str, optional):
                Where the service is.  Defaults to None, which falls
                back to the environment and then to working locally.

        Raises:
            ConfigurationError:
                If a service was named and no credential is set.  The
                alternative is a request that fails with a 401 after
                the command looked like it was working.

        Returns:
            client (Client | LocalClient):
                Something answering the contract's operations.
    """

    url = service_url(supplied=api_url)

    if url is None:
        return LocalClient()

    token = getenv(API_TOKEN_VARIABLE)

    if not token:
        message = (
            f'{API_TOKEN_VARIABLE} is not set, and {url} will not '
            'answer without it. Set it, or leave the service address '
            'unset to read the local database instead.'
        )
        logger.error(message)
        raise ConfigurationError(message)

    return Client(base_url=url, token=token)
