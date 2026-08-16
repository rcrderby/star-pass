#!/usr/bin/env python3
""" The command line client's run-based commands.

    Separate from '__main__.py', which holds the three run modes that
    work from CSV files and predate the API.  Those cannot be reached
    over HTTP -- the contract deliberately publishes nothing addressed
    by a file path -- so they stay local, and the commands here are
    the ones that work either way (D2).
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
