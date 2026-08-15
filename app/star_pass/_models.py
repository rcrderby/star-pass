#!/usr/bin/env python3
""" Read the YAML data models.

    Separate from '_defaults' so that reading a model can log: '_logging'
    reads its level from '_defaults', so a reader living there could not
    import a logger without a cycle.  '_defaults' keeps the paths; this
    module reads what is at them.

    The models are read on first use, not at import.  A module that
    reads a file when it is imported cannot report the failure usefully:
    it happens before logging is configured and before any caller exists
    to catch it, which is why these used to print to stderr and exit.
    Reading them on demand makes a bad model an ordinary
    ConfigurationError, handled like any other.
"""

# Imports - Python Standard Library
from functools import cache
from pathlib import Path
from typing import Any

# Imports - Third-Party
from yaml import safe_load, YAMLError

# Imports - Local
from . import _defaults
from ._exceptions import ConfigurationError
from ._logging import get_logger

# Constants
FILE_ENCODING = _defaults.FILE_ENCODING

# Module logger
logger = get_logger(__name__)


def _read_model(
        path: Path,
        description: str
) -> Any:
    """ Read one YAML data model.

        Args:
            path (Path):
                Full path to the model file.

            description (str):
                How to name the file in an error message.

        Raises:
            ConfigurationError:
                If the file cannot be read or is not valid YAML.

        Returns:
            model (Any):
                The parsed YAML content.
    """

    try:
        with open(
            file=path,
            mode='rt',
            encoding=FILE_ENCODING
        ) as yaml_data:
            return safe_load(
                stream=yaml_data.read()
            )

    except OSError as error:
        message = f'Cannot read the {description} "{path}": {error}'
        logger.error(message)
        raise ConfigurationError(message) from error

    except YAMLError as error:
        message = f'The {description} "{path}" is not valid YAML: {error}'
        logger.error(message)
        raise ConfigurationError(message) from error


@cache
def get_shifts_info() -> Any:
    """ Return the Amplify shift data model.

        Read once and reused.  Required: without it an event title
        cannot be matched to a need.

        Args:
            None.

        Raises:
            ConfigurationError:
                If the model cannot be read or is not valid YAML.

        Returns:
            shifts_info (Any):
                The parsed shift data model.
    """

    return _read_model(
        path=_defaults.SHIFTS_INFO_FILE,
        description='shift data model'
    )


@cache
def _get_role_label_model() -> dict:
    """ Return the Slack role label model.

        Optional, unlike the shift data model: without it a summary
        keeps the full role text from each opportunity title, which is
        correct, only long.  Malformed YAML is still an error, because a
        file that exists is meant to be used.

        Args:
            None.

        Raises:
            ConfigurationError:
                If the file exists but cannot be read or parsed.

        Returns:
            model (dict):
                The parsed model, or an empty dict when absent.
    """

    if not _defaults.SLACK_ROLE_LABELS_FILE.is_file():
        return {}

    return _read_model(
        path=_defaults.SLACK_ROLE_LABELS_FILE,
        description='role label model'
    ) or {}


def get_slack_role_labels() -> dict:
    """ Return the short label for each role, keyed on the role.

        A role with no entry keeps its full text.

        Args:
            None.

        Returns:
            labels (dict):
                Role text mapped to its short form.
    """

    return _get_role_label_model().get('labels') or {}


def get_slack_default_role_label() -> str:
    """ Return the label for an opportunity whose title carries no role.

        Args:
            None.

        Returns:
            label (str):
                The configured default, or 'Officials'.
    """

    return _get_role_label_model().get('default') or 'Officials'
