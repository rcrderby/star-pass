#!/usr/bin/env python3
""" The command line client's commands.

    Separate from '__main__.py', which holds the Slack sign-up
    summary.  The contract deliberately publishes no summary, so that
    stays local; the commands in '_commands' are the ones a service can
    answer as well (D2).

    '_maintenance' holds the one command that is neither.  It applies
    the retention policy to the local database, which the contract
    publishes no operation for on purpose, so it names none and offers
    no service to ask.
"""

# Imports - Local
from ._commands import add_commands, run_command, selected
from ._maintenance import (
    add_maintenance,
    maintenance_selected,
    run_maintenance
)
from ._mode import client_for, service_url
from ._output import write

__all__ = [
    'add_commands',
    'add_maintenance',
    'client_for',
    'maintenance_selected',
    'run_maintenance',
    'run_command',
    'selected',
    'service_url',
    'write'
]
