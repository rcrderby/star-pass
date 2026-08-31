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

# The server's own, which arrive with handlers of their own and with
# 'propagate' off.
SERVER_LOGGERS = (
    'uvicorn',
    'uvicorn.access',
    'uvicorn.error'
)


class JSONFormatter(logging.Formatter):
    """ Render a record as one line of JSON.

        A line was prose, so the reference id that ties a screen's
        refusal to the line that produced it -- the thing that makes
        a log worth attaching to a report at all -- could only be got
        at with a regular expression.

        **What is serialized is what the record already carries.**
        Full upstream detail reaches the log through 'redact_secrets'
        at the call site, so the message handed here is redacted
        before it arrives.  Nothing else about the record is
        serialized: no 'extra', no arguments, no attributes a future
        caller might attach, because each of those is a way to write
        a value into a log that never passed the redaction the
        message did.

        The exception text is the one addition, and it is here to
        keep what the previous formatter did rather than to add
        anything.  Nothing in this application logs with 'exc_info'
        today; dropping it silently if something starts to would lose
        the traceback with no sign that it had gone.
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
    """ Put every log line on one stream in one format.

        **The handler goes on the root logger**, so that a package
        nobody thought to name is still formatted.  Attaching one per
        package looked tidier and was the arrangement that produced
        the split this replaced: the core was configured, the API
        service was not, and its records -- the reference id among
        them -- fell to 'logging.lastResort', which prints the bare
        message at WARNING and drops everything below it.

        **Levels are set per package, and the root keeps its own.**
        The application talks at 'LOG_LEVEL'; everything else it
        imports is left at the root's WARNING, so one format does not
        also mean every library's INFO.  A package left out of the
        list below is still formatted -- it is only quieter than
        intended, which is the milder of the two ways to be wrong.

        Idempotent: repeated calls do not attach a second handler, and
        every 'get_logger' call comes through here.

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
        handler each and 'propagate' off, so its lines reach the
        stream without passing anything of ours: a container's output
        was JSON from the application and plain text from the server
        that was carrying it.

        Their handlers are taken away rather than re-dressed, so there
        is one handler in the process and one place the format is
        decided.

        **Called after the server has started**, from each service's
        lifespan.  Uvicorn applies its logging configuration as it
        boots, which is after this module was imported -- so doing it
        at import would be undone a moment later.

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
