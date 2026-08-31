#!/usr/bin/env python3
""" Applying the retention policy by hand, to the local database.

    Not one of the commands beside it.  Every row in 'COMMANDS' names
    an operation the contract publishes and is answered in either
    mode.  The contract publishes no deletion -- retention removes what
    a run leaves behind, a caller does not -- so there is no operation
    to name and no service to ask, and the table would hand it
    '--api-url', a flag naming a service that cannot answer.

    So it sits where the Slack summary sits: the small set of things
    the API does not publish, which the command line carries.

    The service sweeps on a timer, which covers a deployment.  It does
    not cover a person with a checkout and a database file, running a
    collection once a month, and what accumulates unswept is volunteer
    names.
"""

# Imports - Python Standard Library
import argparse
from typing import Any

# Imports - Local
from star_pass._database import connect
from star_pass._retention import sweep, Swept
from ._output import write
from ._render import labelled

# Constants
# The word this is selected by, and the word within it.  A group of one
# rather than a bare word, so that what it belongs to is legible beside
# 'runs' and 'jobs' and so a second maintenance action has somewhere to
# go.
MAINTENANCE_GROUP = 'retention'
SWEEP_WORD = 'sweep'

GROUP_SUMMARY = 'Apply the retention policy to the local database.'
SWEEP_SUMMARY = (
    'Forget the job logs, revisions and unmatched titles the '
    'retention policy no longer keeps.'
)

# What it says when the policy had nothing to do, which is the usual
# answer and is worth saying rather than printing nothing: a command
# that produced no output would leave the operator unsure it ran.
NOTHING_REMOVED = (
    'Nothing had passed its retention window, so nothing was removed.'
)

# Headed, because a reader of these three numbers is checking that the
# thing they expected to go is the thing that went.
REMOVED_HEADING = 'Removed'

# What each count is called.  The windows themselves are not repeated
# here -- 'config show' publishes them -- because a report of what
# happened and a report of the policy are different questions.
JOB_EVENTS_LABEL = 'Job log entries'
REVISIONS_LABEL = 'Revisions'
UNMATCHED_LABEL = 'Unmatched title sightings'

# Said under the counts, because the one thing a person running this
# might fear is the one thing it cannot touch.
SENT_UNTOUCHED = (
    'The record of what a send created is never removed, so nothing '
    'this did can cause a shift to be sent twice.'
)


def add_maintenance(
        commands: Any
) -> None:
    """ Add the maintenance group to the parser's commands.

        Given the subparsers the reading commands were added to rather
        than the parser itself, because argparse allows a parser only
        one set of them.

        Args:
            commands (Any):
                The subparsers action 'add_commands' returned.

        Returns:
            None.
    """

    group = commands.add_parser(
        MAINTENANCE_GROUP,
        help=GROUP_SUMMARY
    ).add_subparsers(
        dest='subcommand',
        metavar='SUBCOMMAND'
    )
    # No '--api-url'.  There is nothing remote to ask: this works on
    # the database in front of it, and offering the flag would suggest
    # otherwise.
    group.add_parser(
        SWEEP_WORD,
        help=SWEEP_SUMMARY
    )

    return None


def maintenance_selected(
        args: argparse.Namespace
) -> bool:
    """ Return whether the maintenance command was the one asked for.

        Args:
            args (argparse.Namespace):
                The parsed command line.

        Returns:
            selected (bool):
                Whether to sweep.
    """

    return (
        getattr(args, 'command', None) == MAINTENANCE_GROUP
        and getattr(args, 'subcommand', None) == SWEEP_WORD
    )


def run_maintenance() -> None:
    """ Apply the retention policy and say what it removed.

        Opens a connection of its own and closes it, because a
        connection belongs to the thread that opened it and this
        process has no other use for one.

        Args:
            None.

        Raises:
            ConfigurationError:
                If the database cannot be opened.

            UpstreamError:
                If anything cannot be removed.

        Returns:
            None.
    """

    connection = connect()

    try:
        write(swept_text(swept=sweep(connection=connection)))

    finally:
        connection.close()

    return None


def swept_text(
        swept: Swept
) -> str:
    """ Return what one sweep removed, as something to read.

        Args:
            swept (Swept):
                What the sweep reported.

        Returns:
            text (str):
                The counts, or a sentence saying there were none.
    """

    if not swept:
        return NOTHING_REMOVED

    return '\n\n'.join(
        (
            REMOVED_HEADING,
            labelled(
                pairs=(
                    (JOB_EVENTS_LABEL, str(swept.job_events)),
                    (REVISIONS_LABEL, str(swept.revisions)),
                    (UNMATCHED_LABEL, str(swept.unmatched_titles))
                )
            ),
            SENT_UNTOUCHED
        )
    )
