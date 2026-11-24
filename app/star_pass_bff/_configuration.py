#!/usr/bin/env python3
""" Refusing to start half-configured.

    Everything this service does needs the API token and the signing
    secret, and it exists to serve a page, so all three are checked
    while the application is built rather than at the first request.
"""

# Imports - Local
from . import _defaults
from ._exceptions import ConfigurationError


def check_configuration() -> None:
    """ Fail now if the service cannot do its job.

        Called while the application is built, so a deployment missing
        a value stops at startup rather than at the first request that
        mattered.

        Args:
            None.

        Raises:
            ConfigurationError:
                If a required value is missing or unusable.

        Returns:
            None.
    """

    if not _defaults.API_TOKEN:
        raise ConfigurationError(
            'No API token. Configure the STAR_PASS_API_TOKEN environment '
            'variable and restart the application.'
        )

    if not _defaults.SESSION_SECRET:
        raise ConfigurationError(
            'No session secret. Configure the STAR_PASS_SESSION_SECRET '
            'environment variable and restart the application.'
        )

    if len(_defaults.SESSION_SECRET) < _defaults.SESSION_SECRET_MINIMUM_LENGTH:
        raise ConfigurationError(
            'STAR_PASS_SESSION_SECRET must be at least '
            f'{_defaults.SESSION_SECRET_MINIMUM_LENGTH} characters. '
            'Generate a new secret and try again.'
        )

    if not (_defaults.WEB_ROOT / _defaults.WEB_INDEX).is_file():
        raise ConfigurationError(
            f'No {_defaults.WEB_INDEX} under {_defaults.WEB_ROOT}. Set '
            'STAR_PASS_WEB_ROOT to the folder with the built web '
            'interface.'
        )

    return None
