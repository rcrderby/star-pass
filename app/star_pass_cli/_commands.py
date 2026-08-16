#!/usr/bin/env python3
""" The commands that read a run, in whichever mode was asked for.

    Each command does the same three things: pick a client, ask it one
    of the contract's operations, and render what came back.  None of
    them knows which mode it is in, because the answer is the same
    document either way (D2) -- that is what makes one renderer
    correct for both.

    A failure the client reports is written and turned into a non-zero
    status here rather than raised at the operator.  The reason is
    already written for a person: a problem document carries a
    sanitized summary, and an operation with no local answer carries
    why it has none.

    A failure the core raises is not written, only counted.  The core
    logs its own cause before raising, which is the same arrangement
    the run modes use, and writing it here as well would show the
    operator the same sentence twice.
"""

# Imports - Python Standard Library
import argparse
from typing import Callable, Dict, Optional, Tuple

# Imports - Local
from star_pass._exceptions import StarPassError
from star_pass_client import ApiProblem, LocalOperationUnavailable
from ._mode import API_URL_VARIABLE, client_for
from ._output import write
from ._render import runs_table

# Constants
# What a command exits with when it could not answer.
FAILURE = 1
SUCCESS = 0

# The commands, by the words that select them.
COMMAND_RUNS = 'runs'
SUBCOMMAND_LIST = 'list'


def remote_options() -> argparse.ArgumentParser:
    """ Return the options every command shares.

        Held on a parent parser rather than repeated, so that a
        command added later cannot be the one that forgets to offer
        the remote mode.

        Args:
            None.

        Returns:
            parser (argparse.ArgumentParser):
                A parser holding only the shared options.
    """

    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument(
        '--api-url',
        default=None,
        metavar='URL',
        help=(
            'Read from a star-pass service instead of the local '
            f'database. Falls back to {API_URL_VARIABLE}.'
        )
    )

    return shared


def add_commands(
        parser: argparse.ArgumentParser
) -> None:
    """ Add the reading commands to a parser.

        Args:
            parser (argparse.ArgumentParser):
                The parser to add them to.

        Returns:
            None.
    """

    shared = remote_options()
    commands = parser.add_subparsers(
        dest='command',
        metavar='COMMAND',
        title='commands'
    )

    runs = commands.add_parser(
        COMMAND_RUNS,
        help='Read collected runs.'
    )
    subcommands = runs.add_subparsers(
        dest='subcommand',
        metavar='SUBCOMMAND'
    )
    subcommands.add_parser(
        SUBCOMMAND_LIST,
        parents=[shared],
        help='List the runs, newest first.'
    )

    return None


def _list_runs(
        args: argparse.Namespace
) -> None:
    """ Write every run as a table.

        Args:
            args (argparse.Namespace):
                The parsed command line.

        Raises:
            ApiProblem:
                If the service reported a failure.

            StarPassError:
                If the mode cannot be reached as configured.

        Returns:
            None.
    """

    client = client_for(api_url=args.api_url)

    write(runs_table(runs=client.list_runs()))

    return None


# Which function answers which command.
HANDLERS: Dict[Tuple[str, Optional[str]], Callable[..., None]] = {
    (COMMAND_RUNS, SUBCOMMAND_LIST): _list_runs
}


def selected(
        args: argparse.Namespace
) -> Optional[Tuple[str, Optional[str]]]:
    """ Return which command was asked for, if one was.

        Args:
            args (argparse.Namespace):
                The parsed command line.

        Returns:
            command (Tuple[str, str | None] | None):
                The command and subcommand, or None when the run was
                selected by a mode flag instead.
    """

    command = getattr(args, 'command', None)

    if command is None:
        return None

    return (command, getattr(args, 'subcommand', None))


def run_command(
        args: argparse.Namespace
) -> int:
    """ Run the selected command and report how it went.

        Args:
            args (argparse.Namespace):
                The parsed command line.

        Returns:
            status (int):
                Zero when the command answered, one when it could not.
    """

    command = selected(args=args)

    if command is None or command not in HANDLERS:
        # A command word with no subcommand, which argparse accepts
        # because the subcommand is what carries the options.
        named = ' '.join(part for part in command or () if part)
        write(
            f'"{named}" is not a complete command. '
            'Use --help for the list.'
        )

        return FAILURE

    try:
        HANDLERS[command](args)

    except (ApiProblem, LocalOperationUnavailable) as error:
        # Nothing has reported these: they are raised by a client, and
        # a client does not decide what an operator is shown.
        write(str(error))

        return FAILURE

    except StarPassError:
        # Already logged, with its cause, by whatever raised it.
        return FAILURE

    return SUCCESS
