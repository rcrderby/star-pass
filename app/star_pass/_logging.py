#!/usr/bin/env python3
""" Logging configuration for the star_pass package.

    One idempotently-configured package logger, at 'LOG_LEVEL' and
    defaulting to 'INFO'.

    Diagnostic output goes here.  What a person asked for goes to the
    caller's 'Reporter'; the core does not decide how anything is
    displayed.
"""

# Imports - Python Standard Library
from datetime import datetime, timezone
import json
import logging
import sys

# Imports - Local
from . import _defaults
from ._exceptions import ConfigurationError

# Constants
PACKAGE_LOGGER_NAME = 'star_pass'
LOG_LEVEL = _defaults.LOG_LEVEL

# Every package this application ships.  The list decides what talks
# at 'LOG_LEVEL' rather than what is formatted -- formatting is the
# root's job -- so a package added here later is quieter until it is
# named, not unformatted.
APPLICATION_LOGGERS = (
    'star_pass',
    'star_pass_api',
    'star_pass_bff',
    'star_pass_cli',
    'star_pass_client',
    'star_pass_contract'
)

# The levels a deployment may ask for, by name.  A mapping rather than
# a lookup on the 'logging' module: that module holds attributes in
# capitals which are not levels -- 'BASIC_FORMAT' is a format string --
# and a name it holds none of would fall back to a default with
# nothing said about the typo.
LEVELS = {
    'CRITICAL': logging.CRITICAL,
    'ERROR': logging.ERROR,
    'WARNING': logging.WARNING,
    'INFO': logging.INFO,
    'DEBUG': logging.DEBUG
}

# The server's own, which arrive with handlers of their own and with
# 'propagate' off.
SERVER_LOGGERS = (
    'uvicorn',
    'uvicorn.access',
    'uvicorn.error'
)


class JSONFormatter(logging.Formatter):
    """ Render a record as one line of JSON.

        One line of JSON, so the reference id that ties a screen's
        refusal to the line that produced it is a field rather than
        something to match with a regular expression.

        **What is serialized is what the record already carries.**
        The message arrives redacted, through 'redact_secrets' at the
        call site.  Nothing else is - no 'extra', no arguments, no
        attributes a caller might attach - because each is a way to
        write a value that never passed that redaction.

        The exception text is the one addition, so a traceback is not
        dropped silently.
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


def _resolve_level(
        level_name: str
) -> int:
    """ Convert a level name to a 'logging' level value.

        Configuration arrives from the environment, so it is untrusted
        input, and 'LOG_LEVEL=INF' is a typo somebody makes once.  A
        service that answered it by logging at INFO would be quieter
        than asked for a month, which is the interval this tool runs
        on, with nothing said about why.

        Args:
            level_name (str):
                Case-insensitive level name (for example, 'INFO').

        Raises:
            ConfigurationError:
                When the name is not a level.

        Returns:
            int:
                The matching 'logging' level.
    """

    level = LEVELS.get(level_name.strip().upper())

    if level is None:
        raise ConfigurationError(
            f'LOG_LEVEL must be one of {", ".join(LEVELS)}, and is '
            f'{level_name!r}. It is read from the environment or the '
            '.env file at the repository root (see .env.example).'
        )

    return level


def configure_logging() -> logging.Logger:
    """ Put every log line on one stream in one format.

        **The handler goes on the root logger**, so a package nobody
        thought to name is still formatted.  One per package would
        leave an unconfigured package falling to 'logging.lastResort',
        which prints the bare message at WARNING.

        **Levels are set per package, and the root keeps its own.**
        The application talks at 'LOG_LEVEL'; everything it imports
        stays at the root's WARNING.  A package left out of the list
        below is still formatted, only quieter than intended.

        Idempotent: repeated calls do not attach a second handler.

        Args:
            None.

        Returns:
            logging.Logger:
                The 'star_pass' package logger.
    """

    root = logging.getLogger()

    if not any(
        isinstance(handler.formatter, JSONFormatter)
        for handler in root.handlers
    ):
        # Standard error, not standard output.  One logger serves
        # the services and the command line, and
        # 'star_pass_cli/_output.py' writes what a person asked for to
        # standard output: log lines there would interleave with the
        # answer to 'runs list'.  Docker captures both streams, so
        # 'docker compose logs' reads the same either way.
        handler = logging.StreamHandler(stream=sys.stderr)
        handler.setFormatter(JSONFormatter())
        root.addHandler(handler)

    for name in APPLICATION_LOGGERS:
        logging.getLogger(name).setLevel(_resolve_level(LOG_LEVEL))

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

        **Called after the server has started**, from each service's
        lifespan: uvicorn applies its logging configuration as it
        boots, after this module is imported.

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
