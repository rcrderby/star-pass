#!/usr/bin/env python3
""" Logging configuration for the star_pass package.

    Provides a single, idempotently-configured package logger so that
    diagnostic and status output flows through the standard 'logging'
    framework instead of bare 'print' calls.  The log level is read from
    the 'LOG_LEVEL' environment variable (see _defaults), defaulting to
    'INFO'.  User-facing report data (shift previews, JSON) is still
    written with 'Helpers.printer'.
"""

# Imports - Python Standard Library
import logging
import sys

# Imports - Local
from . import _defaults

# Constants
PACKAGE_LOGGER_NAME = 'star_pass'
LOG_LEVEL = _defaults.LOG_LEVEL
LOG_FORMAT = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'


def _resolve_level(
        level_name: str
) -> int:
    """ Convert a level name to a 'logging' level value.

        Args:
            level_name (str):
                Case-insensitive level name (for example, 'INFO').

        Returns:
            int:
                The matching 'logging' level, or 'logging.INFO' when
                'level_name' is not a recognized level.
    """

    return getattr(
        logging,
        level_name.strip().upper(),
        logging.INFO
    )


def configure_logging() -> logging.Logger:
    """ Configure and return the package logger.

        Idempotent: repeated calls do not attach duplicate handlers.
        The logger keeps 'propagate' enabled so test fixtures (pytest's
        'caplog') can capture records; in production the root logger has
        no handler, so output is not duplicated.

        Args:
            None.

        Returns:
            logging.Logger:
                The configured 'star_pass' package logger.
    """

    logger = logging.getLogger(PACKAGE_LOGGER_NAME)
    if not logger.handlers:
        handler = logging.StreamHandler(stream=sys.stderr)
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        logger.addHandler(handler)
        logger.setLevel(_resolve_level(LOG_LEVEL))

    return logger


def get_logger(
        name: str = PACKAGE_LOGGER_NAME
) -> logging.Logger:
    """ Return a configured logger.

        Args:
            name (str, optional):
                Logger name.  Defaults to the package logger name.  Pass
                a dotted child name (for example, '__name__' from a
                module inside the package) to tag records with their
                source while still routing through the package handler.

        Returns:
            logging.Logger:
                A configured logger for 'name'.
    """

    configure_logging()
    return logging.getLogger(name)
