#!/usr/bin/env python3
""" Logging configuration for the front-end service.

    One handler on the root logger, writing JSON to standard error, so
    that a deployment reads one format from both containers.

    What this service records is what it refused and why.  The API
    logs every refusal against the reference the caller was given;
    this process now enforces a session, a token, an origin and a body
    size, and a status code alone cannot say which of them answered.
"""
# The formatter and the level resolution repeat the core's.  Sharing
# one would mean importing the core, and
# 'tests/test_bff_configuration.py' asserts the core never appears in
# this package's import graph.  The repetition is what that boundary
# costs, so this file is named in '.github/linters/.jscpd.json' as
# well; 'tests/test_bff_logging.py' holds the two copies to each other,
# for the reason 'test_bff_headers.py' holds the policy to the
# Caddyfile's.
# pylint: disable=duplicate-code

# Imports - Python Standard Library
from datetime import datetime, timezone
import json
import logging
import sys

# Imports - Local
from . import _defaults
from ._exceptions import ConfigurationError

# Constants
PACKAGE_LOGGER_NAME = 'star_pass_bff'

# The levels a deployment may ask for, by name.  A mapping rather than
# a lookup on the 'logging' module: that module holds attributes in
# capitals which are not levels, and a name it does not hold at all
# would fall back to a default with nothing said about the typo.
LEVELS = {
    'CRITICAL': logging.CRITICAL,
    'ERROR': logging.ERROR,
    'WARNING': logging.WARNING,
    'INFO': logging.INFO,
    'DEBUG': logging.DEBUG
}

# The server's own loggers, which arrive with handlers of their own
# and with 'propagate' off.
SERVER_LOGGERS = (
    'uvicorn',
    'uvicorn.access',
    'uvicorn.error'
)


class JSONFormatter(logging.Formatter):
    """ Render a record as one line of JSON.

        One line, so the reference that ties a refusal to the line
        that produced it is a field rather than something to match
        with a regular expression.

        Records this service writes carry no credential: it holds one,
        and no line here is given it.  A record adopted from the
        server is formatted as the server produced it.
    """

    def format(
            self,
            record: logging.LogRecord
    ) -> str:
        """ Return the record as a JSON object on one line.

            Args:
                record (logging.LogRecord):
                    The record to render.

            Returns:
                line (str):
                    The record as JSON.  Newlines inside the message
                    are escaped by the encoder, so a record is always
                    exactly one line.
        """

        written = {
            'time': datetime.fromtimestamp(
                record.created,
                tz=timezone.utc
            ).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage()
        }

        if record.exc_info is not None:
            written['exception'] = self.formatException(record.exc_info)

        return json.dumps(written)


def resolve_level(
        level_name: str
) -> int:
    """ Return the level a name asks for.

        Args:
            level_name (str):
                Case-insensitive level name, for example 'INFO'.

        Raises:
            ConfigurationError:
                When the name is not a level.

        Returns:
            level (int):
                The matching 'logging' level.
    """

    level = LEVELS.get(level_name.strip().upper())

    if level is None:
        raise ConfigurationError(
            f'LOG_LEVEL must be one of {", ".join(LEVELS)}, and is '
            f'{level_name!r}.'
        )

    return level


def configure_logging() -> logging.Logger:
    """ Put every log line on one stream in one format.

        The handler goes on the root logger, so a package nobody
        thought to name is still formatted rather than falling to
        'logging.lastResort', which prints the bare message at
        WARNING.

        Idempotent: repeated calls do not attach a second handler.

        Args:
            None.

        Raises:
            ConfigurationError:
                When LOG_LEVEL is not a level.

        Returns:
            logging.Logger:
                The package logger.
    """

    root = logging.getLogger()

    if not any(
        isinstance(handler.formatter, JSONFormatter)
        for handler in root.handlers
    ):
        # Standard error, so that a log line never lands in whatever
        # is reading standard output.
        handler = logging.StreamHandler(stream=sys.stderr)
        handler.setFormatter(JSONFormatter())
        root.addHandler(handler)

    logging.getLogger(PACKAGE_LOGGER_NAME).setLevel(
        resolve_level(_defaults.LOG_LEVEL)
    )

    return logging.getLogger(PACKAGE_LOGGER_NAME)


def send_server_logs_the_same_way() -> None:
    """ Put the server's own lines through the same handler.

        Uvicorn configures 'uvicorn' and 'uvicorn.access' with a
        handler each and 'propagate' off, so without this a
        container's output is JSON from the application and plain text
        from the server carrying it.

        Their handlers are taken away rather than re-dressed, so there
        is one handler in the process and one place the format is
        decided.

        Called after the server has started, from the lifespan:
        uvicorn applies its logging configuration as it boots, after
        this module is imported.

        Args:
            None.

        Returns:
            None.
    """

    for name in SERVER_LOGGERS:
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True

    return None


def get_logger(
        name: str = PACKAGE_LOGGER_NAME
) -> logging.Logger:
    """ Return a configured logger.

        Args:
            name (str, optional):
                Logger name.  Defaults to the package logger name.
                Pass '__name__' from a module in this package to tag
                records with their source.

        Returns:
            logging.Logger:
                A configured logger for 'name'.
    """

    configure_logging()

    return logging.getLogger(name)
