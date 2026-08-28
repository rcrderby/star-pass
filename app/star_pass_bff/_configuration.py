#!/usr/bin/env python3
""" Refusing to start half-configured.

    Everything this service does needs the API token and the signing
    secret, and it exists to serve a page, so all three are checked
    while the application is built rather than at the first request.
"""

# Imports - Local
from . import _defaults


class ConfigurationError(Exception):
    """ The service cannot run on what it was given. """


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
            'STAR_PASS_API_TOKEN is not set, so nothing can be asked '
            'of the star-pass API.'
        )

    if not _defaults.SESSION_SECRET:
        raise ConfigurationError(
            'STAR_PASS_SESSION_SECRET is not set, so a session '
            'cannot be told from one somebody made up.'
        )

    if len(_defaults.SESSION_SECRET) < _defaults.SESSION_SECRET_MINIMUM_LENGTH:
        raise ConfigurationError(
            'STAR_PASS_SESSION_SECRET is shorter than '
            f'{_defaults.SESSION_SECRET_MINIMUM_LENGTH} characters. '
            'It is generated rather than typed, so there is no reason '
            'for a short one.'
        )

    if not (_defaults.WEB_ROOT / _defaults.WEB_INDEX).is_file():
        raise ConfigurationError(
            f'No {_defaults.WEB_INDEX} under {_defaults.WEB_ROOT}, so '
            'there is no page to give a browser. This service exists '
            'to serve one and to carry its session; a proxy with '
            'nothing behind it is reachable and unusable. Set '
            'STAR_PASS_WEB_ROOT to where the interface was built.'
        )

    return None
