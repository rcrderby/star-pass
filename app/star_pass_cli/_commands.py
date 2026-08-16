#!/usr/bin/env python3
""" The commands that read a run, in whichever mode was asked for.

    Each command does the same three things: pick a client, ask it one
    of the contract's operations, and render what came back.  None of
    them knows which mode it is in, because the answer is the same
    document either way (D2) -- that is what makes one renderer
    correct for both.

    Because all of them do the same three things, none of them is
    written out.  A command is a row in 'COMMANDS' naming the operation
    to ask and the renderer to show it with, and one function does the
    three things for all of them.  The rows also build the parser, so a
    command cannot be one the command line offers and the dispatcher
    does not answer, or the reverse.

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
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple

# Imports - Local
from star_pass._exceptions import StarPassError
from star_pass_client import ApiProblem, LocalOperationUnavailable
from ._mode import API_URL_VARIABLE, client_for
from ._output import write
from ._render import (
    job_text,
    preview_text,
    revisions_table,
    run_detail,
    runs_table
)

# Constants
# What a command exits with when it could not answer.
FAILURE = 1
SUCCESS = 0

# The word each group of commands is selected by, and what it reads.
GROUPS = {
    'runs': 'Read collected runs.',
    'jobs': 'Read the jobs that long operations are watched through.'
}


@dataclass(frozen=True)
class Command:
    """ One command, and everything that makes it work.

        Attributes:
            group (str):
                The word selecting the group it belongs to, which is a
                key of 'GROUPS'.

            word (str):
                The word selecting it within that group.

            summary (str):
                What it does, shown in the help.

            operation (str):
                The contract operation to ask, named as the generated
                client names it.  Both clients inherit that surface, so
                the name is the same in either mode.

            render (Callable[..., str]):
                What turns the answer into something to read.

            argument (str, optional):
                The path value the operation takes, named as the
                operation names it.  Defaults to None, for an operation
                that addresses nothing.
    """

    group: str
    word: str
    summary: str
    operation: str
    render: Callable[..., str]
    argument: Optional[str] = None


# Every command, in the order the help lists them.
COMMANDS = (
    Command(
        group='runs',
        word='list',
        summary='List the runs, newest first.',
        operation='list_runs',
        render=runs_table
    ),
    Command(
        group='runs',
        word='show',
        summary='Show one run, what it holds and what changed it.',
        operation='get_run',
        render=run_detail,
        argument='run_id'
    ),
    Command(
        group='runs',
        word='revisions',
        summary='List a run\'s revisions, oldest first.',
        operation='list_revisions',
        render=revisions_table,
        argument='run_id'
    ),
    Command(
        group='runs',
        word='preview',
        summary='Show what sending a run would create.',
        operation='get_preview',
        render=preview_text,
        argument='run_id'
    ),
    Command(
        group='jobs',
        word='show',
        summary='Show where a job has got to.',
        operation='get_job',
        render=job_text,
        argument='job_id'
    )
)

# Which command the words on the command line select.
BY_WORDS: Dict[Tuple[str, Optional[str]], Command] = {
    (command.group, command.word): command
    for command in COMMANDS
}


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


def _add_argument(
        parser: argparse.ArgumentParser,
        argument: str
) -> None:
    """ Add the value a command addresses something by.

        What it is called on the command line comes from what the
        operation calls it, so the two cannot drift apart.

        Args:
            parser (argparse.ArgumentParser):
                The command's own parser.

            argument (str):
                The operation's name for the value.

        Returns:
            None.
    """

    named = argument.split('_')[0]

    parser.add_argument(
        argument,
        metavar=named.upper(),
        help=f'Identifier of the {named} to read.'
    )

    return None


def add_commands(
        parser: argparse.ArgumentParser
) -> None:
    """ Add the reading commands to a parser.

        Built from 'COMMANDS' rather than written out, so that what the
        command line offers and what the dispatcher answers are the
        same list read twice.

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
    groups: Dict[str, Any] = {}

    for command in COMMANDS:
        if command.group not in groups:
            groups[command.group] = commands.add_parser(
                command.group,
                help=GROUPS[command.group]
            ).add_subparsers(
                dest='subcommand',
                metavar='SUBCOMMAND'
            )

        added = groups[command.group].add_parser(
            command.word,
            parents=[shared],
            help=command.summary
        )

        if command.argument is not None:
            _add_argument(parser=added, argument=command.argument)

    return None


def _answer(
        command: Command,
        args: argparse.Namespace
) -> None:
    """ Ask one command's operation and write what it answered.

        Args:
            command (Command):
                The command the words selected.

            args (argparse.Namespace):
                The parsed command line.

        Raises:
            ApiProblem:
                If the service reported a failure.

            LocalOperationUnavailable:
                If local mode has no answer for the operation.

            StarPassError:
                If the mode cannot be reached as configured.

        Returns:
            None.
    """

    client = client_for(api_url=args.api_url)
    parameters = (
        {}
        if command.argument is None
        else {command.argument: getattr(args, command.argument)}
    )

    write(
        command.render(
            answer=getattr(client, command.operation)(**parameters)
        )
    )

    return None


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

    if command is None or command not in BY_WORDS:
        # A command word with no subcommand, which argparse accepts
        # because the subcommand is what carries the options.
        named = ' '.join(part for part in command or () if part)
        write(
            f'"{named}" is not a complete command. '
            'Use --help for the list.'
        )

        return FAILURE

    try:
        _answer(command=BY_WORDS[command], args=args)

    except (ApiProblem, LocalOperationUnavailable) as error:
        # Nothing has reported these: they are raised by a client, and
        # a client does not decide what an operator is shown.
        write(str(error))

        return FAILURE

    except StarPassError:
        # Already logged, with its cause, by whatever raised it.
        return FAILURE

    return SUCCESS
