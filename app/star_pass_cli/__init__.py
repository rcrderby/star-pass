#!/usr/bin/env python3
""" The command line client's run-based commands.

    Separate from '__main__.py', which holds the Slack sign-up
    summary.  The contract deliberately publishes no summary, so that
    stays local; the commands here are the ones a service can answer
    as well (D2).
"""

# Imports - Local
from ._commands import add_commands, run_command, selected
from ._mode import client_for, service_url
from ._output import write

__all__ = [
    'add_commands',
    'client_for',
    'run_command',
    'selected',
    'service_url',
    'write'
]
