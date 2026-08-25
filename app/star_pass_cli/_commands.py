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

    A command that writes is the same three things.  What it is given
    arrives as flags rather than as a path value, and the row says what
    turns those into the request the contract publishes -- a function
    rather than a mapping, because a request is allowed to be shaped
    differently from a command line, and the collection's window is.
"""

# Imports - Python Standard Library
import argparse
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple
from uuid import uuid4

# Imports - Local
from star_pass._exceptions import StarPassError
from star_pass_client import ApiProblem, LocalOperationUnavailable
from ._confirm import confirmed, ConfirmationUnavailable
from ._configuration import (
    config_text,
    credential_text,
    unmatched_text
)
from ._mode import API_URL_VARIABLE, client_for
from ._output import write
from ._render import (
    after,
    revisions_table,
    run_detail,
    deleted_text,
    runs_table,
    uncollected_text
)
from ._sending import (
    event_line,
    job_text,
    preview_text,
    send_restatement
)

# Constants
# What a command exits with when it could not answer.  Declining to
# send is neither: the command was told to stop and it stopped.
FAILURE = 1
SUCCESS = 0

# What a send asks before it writes into Amplify (D11).
SEND_QUESTION = 'Create these shifts in Amplify? This cannot be undone.'

# What a send says when there is nothing to ask about, and when the
# answer was no.
NOTHING_TO_SEND = (
    'Amplify already has every shift this run asks for. Nothing sent.'
)
NOT_SENT = 'Nothing was sent.'

# The word each group of commands is selected by, and what it covers.
GROUPS = {
    'runs': 'Collect, read and send runs.',
    'jobs': 'Watch and resume the jobs long operations run as.',
    'config': (
        'Read what the deployment was configured with, test the '
        'credential it runs on, and see what its data model has not '
        'matched.'
    )
}


@dataclass(frozen=True)
class Option:
    """ One value a command takes as a flag.

        Attributes:
            flag (str):
                What it is written as on the command line.

            summary (str):
                What it is for, shown in the help.

            reads (Callable[[str], Any]):
                What turns the typed value into what the request
                carries.  Defaults to leaving it as text.

            example (str, optional):
                A value to show in the help, or None.
    """

    flag: str
    summary: str
    reads: Callable[[str], Any] = str
    example: Optional[str] = None

    @property
    def name(self) -> str:
        """ Return what the parsed value is called.

            Args:
                None.

            Returns:
                name (str):
                    The flag as an identifier.
        """

        return self.flag.lstrip('-').replace('-', '_')


# A command holds one field per thing that makes it work, which is
# more attributes than a class carrying behavior should have.  The
# limit is aimed at classes that do something; this one only holds
# values, and the function below does the doing for all of them.
@dataclass(frozen=True)
class Command:  # pylint: disable=too-many-instance-attributes
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

            options (Tuple[Option, ...]):
                The flags it takes.  Empty for a command that takes
                none.

            body (Callable[..., Dict[str, Any]], optional):
                What turns the flags into the request the contract
                publishes.  Defaults to None, for an operation that is
                sent nothing.  A function rather than a mapping of flag
                to field, because a request is allowed to be shaped
                differently from a command line.

            streams (bool):
                Whether the operation is answered over time, so the
                renderer is given each thing as it arrives rather than
                one answer at the end.

            answer (Callable[..., None], optional):
                What carries the command out, for one the three things
                below do not describe.  Defaults to None, which is
                nearly all of them.
    """

    group: str
    word: str
    summary: str
    operation: str
    render: Callable[..., str]
    argument: Optional[str] = None
    options: Tuple[Option, ...] = ()
    body: Optional[Callable[..., Dict[str, Any]]] = None
    streams: bool = False
    answer: Optional[Callable[..., None]] = None


def _collection(
        args: argparse.Namespace
) -> Dict[str, Any]:
    """ Return what a collection is asked for.

        The last day is turned into the day after it here, through the
        one function that converts between the two, because the window
        crosses the wire with an exclusive end and is spoken about by
        the last day it covers.  A command line takes the day it
        displays.

        Args:
            args (argparse.Namespace):
                The parsed command line.

        Raises:
            ValueError:
                If a date is not a date.

        Returns:
            body (Dict[str, Any]):
                The request the contract publishes.
    """

    return {
        'calendar': args.calendar,
        'window': {
            'start': args.start,
            'end': after(last_day_covered=args.last_day)
        }
    }


def _recollection(
        args: argparse.Namespace
) -> Dict[str, Any]:
    """ Return what a recollection is asked for.

        Args:
            args (argparse.Namespace):
                The parsed command line.

        Returns:
            body (Dict[str, Any]):
                The request the contract publishes.
    """

    return {'expectedChangeCount': args.expected_changes}


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
        word='uncollected',
        summary=(
            'Show what a run\'s window held and the run did not '
            'collect.'
        ),
        operation='list_uncollected',
        render=uncollected_text,
        argument='run_id'
    ),
    Command(
        group='runs',
        word='delete',
        summary='Delete a run that never sent shifts to Amplify.',
        operation='delete_run',
        render=deleted_text,
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
        group='runs',
        word='collect',
        summary='Collect a calendar window into a new run.',
        operation='collect_run',
        render=job_text,
        options=(
            Option(
                flag='--calendar',
                summary='Which configured calendar to read.',
                example='events'
            ),
            Option(
                flag='--start',
                summary='First day to cover, as an ISO date.',
                example='2026-09-01'
            ),
            Option(
                flag='--last-day',
                summary=(
                    'Last day to cover, as an ISO date. The day '
                    'itself, not the day after it.'
                ),
                example='2026-09-30'
            )
        ),
        body=_collection
    ),
    Command(
        group='runs',
        word='recollect',
        summary='Collect a run\'s window again, replacing what it holds.',
        operation='recollect_run',
        render=job_text,
        argument='run_id',
        options=(
            Option(
                flag='--expected-changes',
                summary=(
                    'How many changes this would discard, which '
                    '"runs revisions" reports for the current '
                    'revision. The service refuses a number that no '
                    'longer matches, which is what stops a run that '
                    'has moved on being replaced from a stale reading '
                    'of it.'
                ),
                reads=int,
                example='0'
            ),
        ),
        body=_recollection
    ),
    Command(
        group='runs',
        word='send',
        summary='Create this run\'s shifts in Amplify.',
        operation='send_run',
        render=job_text,
        argument='run_id',
        answer=lambda command, args: _send(command=command, args=args)
    ),
    Command(
        group='jobs',
        word='show',
        summary='Show where a job has got to.',
        operation='get_job',
        render=job_text,
        argument='job_id'
    ),
    Command(
        group='jobs',
        word='watch',
        summary='Follow a job as it reports, until it is over.',
        operation='stream_job_events',
        render=event_line,
        argument='job_id',
        streams=True
    ),
    Command(
        group='jobs',
        word='resume',
        summary='Run an interrupted job again.',
        operation='resume_job',
        render=job_text,
        argument='job_id'
    ),
    Command(
        group='config',
        word='show',
        summary=(
            'Show the settings a collection is carried out under.'
        ),
        operation='get_config',
        render=config_text
    ),
    Command(
        group='config',
        word='credential',
        summary=(
            'Test the Amplify credential and show its last four '
            'characters.'
        ),
        operation='test_credential',
        render=credential_text
    ),
    Command(
        group='config',
        word='unmatched',
        summary=(
            'List the titles the shift data model has not matched.'
        ),
        operation='list_unmatched_titles',
        render=unmatched_text
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


def _add_option(
        parser: argparse.ArgumentParser,
        option: Option
) -> None:
    """ Add one of the values a command is given.

        Required, every one of them.  A write the contract publishes
        takes what it takes, and a flag defaulted here would be this
        module deciding on the operator's behalf what to collect or how
        much to discard.

        Args:
            parser (argparse.ArgumentParser):
                The command's own parser.

            option (Option):
                What to add.

        Returns:
            None.
    """

    parser.add_argument(
        option.flag,
        required=True,
        type=option.reads,
        metavar=option.name.split('_')[-1].upper(),
        help=(
            option.summary
            if option.example is None
            else f'{option.summary} For example: {option.example}.'
        )
    )

    return None


def add_commands(
        parser: argparse.ArgumentParser
) -> Any:
    """ Add the reading commands to a parser.

        Built from 'COMMANDS' rather than written out, so that what the
        command line offers and what the dispatcher answers are the
        same list read twice.

        Returns what it added them to, because argparse allows a parser
        only one set of subparsers and the maintenance command is not
        one of these -- it names no contract operation and takes no
        '--api-url' (see '_maintenance').

        Args:
            parser (argparse.ArgumentParser):
                The parser to add them to.

        Returns:
            commands (Any):
                The subparsers action, for anything else adding a group
                of its own.
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

        for option in command.options:
            _add_option(parser=added, option=option)

    return commands


def _send(
        command: Command,
        args: argparse.Namespace
) -> None:
    """ Read what a send would do, ask, and do it (D11).

        Three operations rather than one, and that is the point.  What
        somebody is asked to confirm is read here and now -- so it
        describes the run and the Amplify of this moment rather than
        of whenever they last looked -- and the count they confirmed is
        the count the send is made with.  The service checks it again
        against its own reading, which is what catches a run that moved
        between the question and the answer.

        The key is minted per attempt rather than asked for.  It stops
        one request being carried out twice; what stops a *row* being
        created twice is the live read the send makes, and that holds
        however many attempts there are.

        Args:
            command (Command):
                The command the words selected.

            args (argparse.Namespace):
                The parsed command line.

        Raises:
            ApiProblem:
                If there is no such run, or it is not one that may be
                sent.

            ConfirmationUnavailable:
                If there is no terminal to answer from.

            StarPassError:
                If the mode cannot be reached as configured.

        Returns:
            None.
    """

    client = client_for(api_url=args.api_url)
    run_id = getattr(args, command.argument)
    run = client.get_run(run_id=run_id)
    preview = client.get_preview(run_id=run_id)
    creating = preview['totals']['willCreate']

    write(send_restatement(run=run, preview=preview))

    if not creating:
        write(NOTHING_TO_SEND)

        return None

    if not confirmed(question=SEND_QUESTION):
        write(NOT_SENT)

        return None

    write(
        command.render(
            answer=client.send_run(
                run_id=run_id,
                body={'expectedShiftCount': creating},
                idempotency_key=uuid4().hex
            )
        )
    )

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

    if command.answer is not None:
        return command.answer(command=command, args=args)

    client = client_for(api_url=args.api_url)
    answer = getattr(client, command.operation)(
        **_asked(command=command, args=args)
    )

    if command.streams:
        # Written as each arrives, rather than gathered and written at
        # the end: the point of watching a job is being told while it
        # is still running.
        for event in answer:
            write(command.render(answer=event))

        return None

    write(command.render(answer=answer))

    return None


def _asked(
        command: Command,
        args: argparse.Namespace
) -> Dict[str, Any]:
    """ Return what one command gives its operation.

        Args:
            command (Command):
                The command the words selected.

            args (argparse.Namespace):
                The parsed command line.

        Raises:
            ValueError:
                If a value the body is built from cannot be read.

        Returns:
            asked (Dict[str, Any]):
                What to call the operation with.
    """

    asked: Dict[str, Any] = {}

    if command.argument is not None:
        asked[command.argument] = getattr(args, command.argument)

    if command.body is not None:
        asked['body'] = command.body(args=args)

    return asked


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

    except (
        ApiProblem,
        ConfirmationUnavailable,
        LocalOperationUnavailable
    ) as error:
        # Nothing has reported these: they are raised by a client or
        # by the gate in front of a send, and neither decides what an
        # operator is shown.
        write(str(error))

        return FAILURE

    except ValueError as error:
        # A value the operator typed that could not be read -- a date
        # that is not one.  Nothing has reported it: argparse checked
        # what it could, and the rest is checked where it is used.
        write(str(error))

        return FAILURE

    except StarPassError:
        # Already logged, with its cause, by whatever raised it.
        return FAILURE

    return SUCCESS
