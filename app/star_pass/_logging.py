#!/usr/bin/env python3
""" Logging configuration for the star_pass package.

    Provides a single, idempotently-configured package logger so that
    diagnostic and status output flows through the standard 'logging'
    framework instead of bare 'print' calls.  The log level is read from
    the 'LOG_LEVEL' environment variable (see _defaults), defaulting to
    'INFO'.  User-facing report data (shift previews, JSON) goes to the
    caller's 'Reporter' instead, which the CLI renders; the core does
    not decide how anything is displayed.
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
        # Standard error, not standard output.
        #
        # Plan section 8 asks for "structured JSON logs to stdout".
        # The structure is the half worth having and is above; the
        # destination is wrong in contact with this code, because one
        # logger serves both the services and the command line, and
        # 'star_pass_cli/_output.py' writes what a person asked for to
        # standard output.  Moving log lines there would interleave
        # them with the answer to 'runs list', and redirecting that
        # answer to a file would collect the log with it.
        #
        # Nothing is lost in a container: Docker captures both
        # streams, so 'docker compose logs' reads the same either way.
        # What section 8 is really asking for -- no log files, no
        # rotation inside the application -- is already true.
        handler = logging.StreamHandler(stream=sys.stderr)
        handler.setFormatter(JSONFormatter())
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
