#!/usr/bin/env python3
""" Main application script. """

# Imports - Python Standard Library
import argparse
import sys
from json import dumps
from typing import Any, Dict, List, Optional, Sequence, TextIO

# Imports - Third-Party
from slack_sdk.errors import SlackApiError

# Imports - Local
from star_pass.amplify_responses import AmplifyResponses
from star_pass.slack_notify import SlackNotifier
from star_pass._exceptions import StarPassError
from star_pass._helpers import Helpers, require_env_vars
from star_pass._logging import get_logger
from star_pass._reporting import Reporter, ShiftBatch
from star_pass import _defaults
from star_pass_cli import (
    add_commands,
    add_maintenance,
    maintenance_selected,
    run_command,
    run_maintenance,
    selected,
    step_text,
    write
)

# Constants
VERBOSITY_LEVELS = _defaults.VERBOSITY_LEVELS
# Slack destination channels (deployment config; may be None).
SLACK_CHANNEL_ID = _defaults.SLACK_CHANNEL_ID
SLACK_DEV_CHANNEL_ID = _defaults.SLACK_DEV_CHANNEL_ID
# Need IDs summarized when -N is omitted (non-secret deployment config).
SLACK_SUMMARY_NEED_IDS = _defaults.SLACK_SUMMARY_NEED_IDS

# Hand-written usage so the help clearly shows which options are
# mandatory (unbracketed) and optional (bracketed) for each run mode.
USAGE = (
    'star-pass runs list [--api-url URL]\n'
    '       star-pass runs {show,revisions,preview,send,delete} RUN '
    '[--api-url URL]\n'
    '       star-pass runs collect --calendar {events,practices} '
    '--start DATE --last-day DATE\n'
    '       star-pass runs recollect RUN --expected-changes N\n'
    '       star-pass jobs {show,watch,resume} JOB [--api-url URL]\n'
    '       star-pass retention sweep\n'
    '       star-pass -s [-N NEED_ID ...] [-C {true,false}] '
    '[-d DAYS] [-D START_IN_DAYS] [-t TITLE] [-k CHANNEL_ID]'
)

# Initialize helper methods
helpers = Helpers()

# Application logger
logger = get_logger('star_pass.main')


class TerminalReporter(Reporter):
    """ Render core progress and results as terminal text.

        Holds every decision about display: the trailing ellipsis on
        a step, the "done." that closes it, and how much of a sent
        batch to show.
    """

    def __init__(
            self,
            verbosity: str = VERBOSITY_LEVELS[0]
    ) -> None:
        """ TerminalReporter initialization method.

            Args:
                verbosity (str, optional):
                    One of VERBOSITY_LEVELS.  An unrecognized value
                    falls back to the simplest, so a bad value shows
                    less rather than failing a run that is otherwise
                    fine.

            Returns:
                None.
        """

        if verbosity in VERBOSITY_LEVELS:
            self.verbosity = verbosity
        else:
            self.verbosity = VERBOSITY_LEVELS[0]

        # A blank line separates the first step from the command that
        # started it.  The core does not know which step is first.
        self._started = False

        return None

    def step_started(
            self,
            step: str,
            subject: str = ''
    ) -> None:
        """ Open a status line, leaving it for 'step_finished'.

            The core names the step and this words it, through the
            same map the job watcher reads.

            Args:
                step (str):
                    Which one, from 'STEPS'.

                subject (str, optional):
                    What it is working on, where its wording asks for
                    one.  Defaults to an empty string.

            Returns:
                None.
        """

        prefix = '' if self._started else '\n'
        self._started = True
        write(
            f'{prefix}{step_text(step=step, subject=subject)}...',
            end=''
        )

        return None

    def step_finished(self) -> None:
        """ Close an open status line.

            Args:
                None.

            Returns:
                None.
        """

        write('done.')

        return None

    def step_failed(self) -> None:
        """ End an open status line without a result.

            Args:
                None.

            Returns:
                None.
        """

        write('')

        return None

    def sending_started(
            self,
            opportunities: int
    ) -> None:
        """ Announce the send, and how much of it there is.

            Args:
                opportunities (int):
                    How many opportunities the send will work through.

            Returns:
                None.
        """

        noun = 'opportunity' if opportunities == 1 else 'opportunities'
        write(
            f'\nSending shift data to Amplify, across '
            f'{opportunities} {noun}...'
        )

        return None

    def slack_dry_run(
            self,
            payload: List[Dict[str, Any]]
    ) -> None:
        """ Show the Block Kit payload a live run would have posted.

            Args:
                payload (List[Dict[str, Any]]):
                    The blocks that would have been posted.

            Returns:
                None.
        """

        write(_defaults.SLACK_CHECK_MODE_MESSAGE)
        write(dumps(payload, indent=2))

        return None

    def summary_skipped(self) -> None:
        """ Say that the window held nothing to post.

            Args:
                None.

            Returns:
                None.
        """

        write(
            'No shifts in the summary window; skipped posting to Slack.'
        )

        return None

    def opportunity_sent(
            self,
            batch: ShiftBatch
    ) -> None:
        """ Render one opportunity's turn at the chosen verbosity.

            The need ID is not shown at any verbosity: the title
            names the opportunity in a way an operator recognizes.

            What Amplify already held is shown beside what was created,
            and only when there was any, so an opportunity that needed
            nothing does not read as a failure.

            Args:
                batch (ShiftBatch):
                    The opportunity, what was created under it, and
                    what it already held.

            Returns:
                None.
        """

        index = batch.index
        title = batch.title
        url = batch.url
        shifts = batch.shifts
        payload = batch.payload

        shift_count = len(shifts)
        shift_noun = 'shift' if shift_count == 1 else 'shifts'
        already = (
            f', {batch.skipped} already in Amplify'
            if batch.skipped
            else ''
        )

        if self.verbosity == VERBOSITY_LEVELS[0]:
            message = (
                f'{index}. {title} - '
                f'{shift_count} new {shift_noun}{already}'
            )

        elif self.verbosity == VERBOSITY_LEVELS[1]:
            message = (
                f'Opportunity Title: {title}\n'
                f'URL: {url}\n'
                f'Shift Count: {shift_count}{already}\n'
            )

            for shift in shifts:
                date_time_string = shift.get('start')
                simple_date = helpers.format_shift_date_simple(
                    date_time_string=date_time_string
                )
                simple_time = helpers.format_shift_time_simple(
                    date_time_string=date_time_string,
                    shift_duration=shift.get('duration')
                )
                message += f'{simple_date}: {simple_time}\n'

        else:
            message = (
                f'URL: {url}\n'
                f'Opportunity Title: {title}\n'
                f'Shift Count: {shift_count}{already}\n'
                f'Payload:\n{dumps(payload, indent=2)}'
            )

        write(message)

        return None


# argparse boolean type converter
def _bool_arg(
        value: str
) -> bool:
    """ Parse a boolean CLI value, reusing the shared converter.

        Wraps 'Helpers.convert_to_bool' so an unrecognized value raises
        'argparse.ArgumentTypeError', letting argparse surface the
        converter's message (which lists the accepted spellings).

        Args:
            value (str):
                Raw argument value.

        Raises:
            argparse.ArgumentTypeError:
                If 'value' is not a recognized boolean string.

        Returns:
            bool:
                The parsed boolean value.
    """

    try:
        return helpers.convert_to_bool(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def _split_need_ids(
        values: Sequence[str]
) -> list:
    """ Expand comma-separated need IDs into a de-duplicated list.

        Args:
            values (Sequence[str]):
                Raw '-N' values, each possibly comma-separated.

        Returns:
            need_ids (list):
                The IDs in the order given, without duplicates or blanks.
    """

    need_ids = []
    for value in values:
        for need_id in value.split(','):
            need_id = need_id.strip()
            if need_id and need_id not in need_ids:
                need_ids.append(need_id)

    return need_ids


def resolve_need_ids(
        values: Optional[Sequence[str]],
        stdin: Optional[TextIO] = None
) -> list:
    """ Resolve the need IDs to summarize from the available sources.

        Explicit '-N' values win.  A '-N -' value additionally reads IDs
        from stdin, which lets another command supply them.  With no
        '-N' at all the configured 'SLACK_SUMMARY_NEED_IDS' is used, so
        an unattended run needs no IDs on the command line.

        Args:
            values (Sequence[str], optional):
                Raw '-N' values, or None when the option was omitted.

            stdin (TextIO, optional):
                Stream read for a '-' value.  Defaults to 'sys.stdin'.

        Returns:
            need_ids (list):
                The resolved IDs, in order and without duplicates.
    """

    if not values:
        return _split_need_ids(values=SLACK_SUMMARY_NEED_IDS)

    # A '-' stands for the stdin list rather than an ID of its own
    explicit = [value for value in values if value != '-']
    if '-' in values:
        stream = stdin if stdin is not None else sys.stdin
        explicit.extend(stream.read().split())

    return _split_need_ids(values=explicit)


# Build the command-line argument parser
def build_parser() -> argparse.ArgumentParser:
    """ Build the command-line argument parser.

        Two ways in.  A command word - "runs collect", "jobs watch" -
        selects something the API publishes.  '-s/--post-slack-summary'
        selects the Slack sign-up summary, which the API does not
        publish, so it stays a flag.

        Options required only within a run mode cannot be marked
        required at the argparse level, so 'main' validates them; the
        help text and usage line mark them.

        Args:
            None.

        Returns:
            parser (argparse.ArgumentParser):
                The configured argument parser.
    """

    parser = argparse.ArgumentParser(
        prog='star-pass',
        usage=USAGE,
        description=(
            'Automate volunteer-shift management in Galaxy Digital '
            'Amplify.'
        )
    )

    # The one run mode left.  Not required at the argparse level: a
    # command word selects what to do instead, and requiring the flag
    # here would reject every command.  'main' reports the case where
    # neither was given.
    mode_group = parser.add_argument_group('run mode')
    mode_group.add_argument(
        '-s', '--post-slack-summary',
        action='store_true',
        help='Post a shift sign-up summary to Slack.'
    )

    # Options for 'post-slack-summary' mode
    slack_group = parser.add_argument_group('post-slack-summary options')
    slack_group.add_argument(
        '-N', '--need-id',
        action='append',
        default=None,
        help=(
            'Amplify need ID to summarize; repeat or comma-separate for '
            'several, or pass "-" to read IDs from stdin.  Defaults to '
            'SLACK_SUMMARY_NEED_IDS.'
        )
    )
    slack_group.add_argument(
        '-d', '--days',
        type=int,
        default=None,
        help=(
            'Calendar days to summarize, counting today as day one; '
            '1 is today only (default: SLACK_SUMMARY_DAYS, else 1).'
        )
    )
    slack_group.add_argument(
        '-D', '--start-in-days',
        type=int,
        default=None,
        help=(
            'Days from today to the first day covered; 0 starts today, '
            '1 starts tomorrow (default: SLACK_SUMMARY_START_IN_DAYS, '
            'else 0).'
        )
    )
    slack_group.add_argument(
        '-t', '--slack-title',
        default=None,
        help='Message title (default: the summary window dates).'
    )
    slack_group.add_argument(
        '-k', '--slack-channel',
        default=None,
        metavar='CHANNEL_ID',
        help=(
            'Slack channel ID to post to (default: SLACK_CHANNEL_ID, '
            'else SLACK_DEV_CHANNEL_ID).'
        )
    )

    slack_group.add_argument(
        '-C', '--check-mode',
        type=_bool_arg,
        default=None,
        metavar='{true,false}',
        help='Dry run without posting the message (default: true).'
    )

    # The run-based commands, which work against the local database or
    # a service (D2).  Added last so they appear below the run modes.
    #
    # The maintenance command joins the same set of subparsers, because
    # argparse allows a parser only one: it is not one of those
    # commands and deliberately takes no '--api-url', since the
    # contract publishes no deletion for it to ask for.
    add_maintenance(commands=add_commands(parser=parser))

    return parser


def _command_answered(
        parser: argparse.ArgumentParser,
        args: argparse.Namespace
) -> bool:
    """ Run a command word, if one selected this run.

        Holds the whole question of how a run was selected: a
        command, the maintenance command, or a run mode answers it, and
        nothing answering it is the error.

        Args:
            parser (argparse.ArgumentParser):
                The parser, for reporting a selection that is none of
                them.

            args (argparse.Namespace):
                The parsed command line.

        Raises:
            SystemExit:
                With a non-zero status when the command failed, or
                when neither a command nor a run mode was given.

        Returns:
            answered (bool):
                Whether something answered, so the run modes are not
                involved.
    """

    # Checked before the commands, because it is not one of them: it
    # names no contract operation, so 'selected' does not see it.
    if maintenance_selected(args=args):
        run_maintenance()

        return True

    if selected(args=args) is None:
        if not args.post_slack_summary:
            parser.error(
                '-s/--post-slack-summary is required, or a command '
                'such as "runs list"'
            )

        return False

    status = run_command(args=args)

    if status:
        sys.exit(status)

    return True


# Main application function definition
def main(
        argv: Optional[Sequence[str]] = None
) -> None:
    """ Main application.

        Dispatches to a run mode and turns an expected failure into a
        non-zero exit.  The core raises 'StarPassError' rather than
        exiting, so the status code is decided here.

        Everything that raises logs its cause first, so the handler
        exits without repeating the message.  An unexpected exception
        is left to propagate.

        Args:
            argv (Optional[Sequence[str]]):
                Argument list to parse.  Defaults to None, which parses
                'sys.argv'.  Primarily an injection point for tests.

        Raises:
            SystemExit:
                With status 1 when a run mode reports a failure.

        Returns:
            None.
    """

    try:
        _run(argv=argv)
    except (StarPassError, ValueError, SlackApiError) as error:
        # Pre-format the message rather than passing logging arguments:
        # the pylint configuration sets 'logging-format-style=new', and
        # brace-style placeholders are not interpolated by the standard
        # library, which formats with '%'.
        message = f'The run mode reported a failure: {error!r}'
        logger.debug(message)
        sys.exit(1)

    return None


def _run(
        argv: Optional[Sequence[str]] = None
) -> None:
    """ Parse arguments and run the selected run mode.

        Args:
            argv (Optional[Sequence[str]]):
                Argument list to parse.  Defaults to None, which parses
                'sys.argv'.

        Returns:
            None.
    """

    # Parse CLI arguments (argparse exits non-zero on invalid input)
    parser = build_parser()
    args = parser.parse_args(argv)

    if _command_answered(parser=parser, args=args):
        return None

    # The Slack sign-up summary, which is the only run mode left.
    #
    # It stays a run mode because nothing in the API replaces it: the
    # summary is out of scope there by decision, so retiring it would
    # delete a working scheduled job and put nothing in its place.  It
    # reads Amplify and
    # posts to Slack, and it opens no database -- the runner it is
    # scheduled on is ephemeral with no volume, so a file written there
    # would go with the container.
    need_ids = resolve_need_ids(values=args.need_id)
    if not need_ids:
        parser.error(
            '-s/--post-slack-summary requires -N/--need-id or '
            'SLACK_SUMMARY_NEED_IDS'
        )
    if args.days is not None and args.days < 1:
        parser.error(
            '-d/--days must be 1 or greater (1 is today only)'
        )
    if args.start_in_days is not None and args.start_in_days < 0:
        parser.error(
            '-D/--start-in-days must be 0 or greater '
            '(0 starts today)'
        )
    # Apply the check-mode default (dry run) and resolve the channel
    check_mode = (
        True if args.check_mode is None else args.check_mode
    )
    channel = (
        args.slack_channel
        or SLACK_CHANNEL_ID
        or SLACK_DEV_CHANNEL_ID
    )

    # The summary is read from Amplify in both modes; the Slack
    # token is only needed when the message is actually sent
    require_env_vars('AMPLIFY_TOKEN')
    if check_mode is False:
        require_env_vars('SLACK_BOT_TOKEN')

    # Announce the run mode
    logger.info(
        'Run mode is "Post Slack Summary"'
    )
    # Build the sign-up summary and post it to Slack
    summary = AmplifyResponses().build_summary(
        need_ids=need_ids,
        title=args.slack_title,
        days=args.days,
        start_in_days=args.start_in_days
    )
    SlackNotifier(
        channel=channel,
        check_mode=check_mode,
        reporter=TerminalReporter()
    ).post_summary(
        summary=summary
    )

    return None


# Run main application function
if __name__ == '__main__':
    main()
