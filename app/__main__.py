#!/usr/bin/env python3
""" Main application script. """

# Imports - Python Standard Library
import argparse
import sys
from typing import Optional, Sequence, TextIO

# Imports - Third-Party
from slack_sdk.errors import SlackApiError

# Imports - Local
from star_pass.amplify_responses import AmplifyResponses
from star_pass.amplify_shifts import CreateShifts
from star_pass.gcal_data import GCALData
from star_pass.slack_notify import SlackNotifier
from star_pass._helpers import Helpers, require_env_vars
from star_pass._logging import get_logger
from star_pass import _defaults

# Constants
VERBOSITY_LEVELS = _defaults.VERBOSITY_LEVELS
# Valid Google Calendar names, derived from the configured calendars so
# the choices stay in sync with any deployment overrides.
GCAL_NAMES = tuple(_defaults.GCAL_CALENDARS)
# Slack destination channels (deployment config; may be None).
SLACK_CHANNEL = _defaults.SLACK_CHANNEL
SLACK_DEV_CHANNEL = _defaults.SLACK_DEV_CHANNEL
# Need IDs summarized when -N is omitted (non-secret deployment config).
SLACK_SUMMARY_NEED_IDS = _defaults.SLACK_SUMMARY_NEED_IDS

# Hand-written usage so the help clearly shows which options are
# mandatory (unbracketed) and optional (bracketed) for each run mode.
USAGE = (
    'star-pass -g -n {events,practices}\n'
    '       star-pass -c -i INPUT_FILE [-C {true,false}] '
    '[-o {basic,simple,detailed}]\n'
    '       star-pass -s [-N NEED_ID ...] [-C {true,false}] '
    '[-d DAYS] [-t TITLE] [-k CHANNEL]'
)

# Initialize helper methods
helpers = Helpers()

# Application logger
logger = get_logger('star_pass.main')


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

        The run mode is selected by one of three mutually-exclusive flags
        ('-g/--get-gcal-events', '-c/--create-amplify-shifts', or
        '-s/--post-slack-summary'); each input is an option with a short
        and long form.  '-C/--check-mode' is shared by the create and
        Slack modes.  Options that are required for a mode cannot be
        marked required at the argparse level (they are only required
        within a mode), so 'main' validates them explicitly; the help
        text and usage line mark them.

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

    # Run mode: exactly one flag is required
    mode_group = parser.add_argument_group('run mode (choose one)')
    mode = mode_group.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        '-g', '--get-gcal-events',
        action='store_true',
        help='Collect events from a Google Calendar into a CSV file.'
    )
    mode.add_argument(
        '-c', '--create-amplify-shifts',
        action='store_true',
        help='Create Amplify shifts from a formatted CSV file.'
    )
    mode.add_argument(
        '-s', '--post-slack-summary',
        action='store_true',
        help='Post a shift sign-up summary to Slack.'
    )

    # Options for 'get-gcal-events' mode
    get_group = parser.add_argument_group('get-events options')
    get_group.add_argument(
        '-n', '--gcal-name',
        choices=GCAL_NAMES,
        default=None,
        help='Google Calendar to collect (required with -g).'
    )

    # Options for 'create-amplify-shifts' mode
    create_group = parser.add_argument_group('create-shifts options')
    create_group.add_argument(
        '-i', '--input-file',
        default=None,
        help='CSV file to read shift data from (required with -c).'
    )
    create_group.add_argument(
        '-o', '--output-verbosity',
        choices=VERBOSITY_LEVELS,
        default=None,
        help='Amount of detail to display (default: basic).'
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
        '-t', '--slack-title',
        default=None,
        help='Message title (default: the summary window dates).'
    )
    slack_group.add_argument(
        '-k', '--slack-channel',
        default=None,
        help=(
            'Slack channel ID to post to (default: SLACK_CHANNEL, '
            'else SLACK_DEV_CHANNEL).'
        )
    )

    # Shared option: valid with -c and -s
    shared_group = parser.add_argument_group('shared options (-c and -s)')
    shared_group.add_argument(
        '-C', '--check-mode',
        type=_bool_arg,
        default=None,
        metavar='{true,false}',
        help='Dry run without sending requests (default: true).'
    )

    return parser


# Main application function definition
def main(
        argv: Optional[Sequence[str]] = None
) -> None:
    """ Main application.

        Dispatches to a run mode and converts an expected failure into a
        non-zero exit.  'get_gcal_time_window', 'SlackNotifier.post', and
        the Slack Web API all log the cause before raising, so the
        handler exits without repeating the message or printing a
        traceback over a report the operator has already been given.  An
        unexpected exception is deliberately left to propagate.

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
    except (ValueError, SlackApiError) as error:
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

    # Run the application in 'get_gcal_events' mode
    if args.get_gcal_events:
        # Validate that only get-mode options were supplied
        if args.gcal_name is None:
            parser.error(
                '-g/--get-gcal-events requires -n/--gcal-name'
            )
        if any(
            value is not None
            for value in (
                args.input_file,
                args.output_verbosity,
                args.need_id,
                args.days,
                args.slack_title,
                args.slack_channel,
                args.check_mode
            )
        ):
            parser.error(
                'only -n/--gcal-name is valid with '
                '-g/--get-gcal-events'
            )

        # Fail before the first request when the credential is missing
        require_env_vars('GCAL_TOKEN')

        # Announce the run mode
        logger.info(
            'Run mode is "Get Google Calendar Events"'
        )
        # Create GCALData object
        GCALData(
            gcal_name=args.gcal_name
        )

    # Run the application in 'create_amplify_shifts' mode
    elif args.create_amplify_shifts:
        # Validate that only create-mode options were supplied
        if args.input_file is None:
            parser.error(
                '-c/--create-amplify-shifts requires -i/--input-file'
            )
        if any(
            value is not None
            for value in (
                args.gcal_name,
                args.need_id,
                args.days,
                args.slack_title,
                args.slack_channel
            )
        ):
            parser.error(
                '-n/--gcal-name and the -s/--post-slack-summary '
                'options are not valid with -c/--create-amplify-shifts'
            )

        # Apply defaults for the optional create-mode arguments
        check_mode = (
            True if args.check_mode is None else args.check_mode
        )
        output_verbosity = (
            args.output_verbosity
            if args.output_verbosity is not None
            else VERBOSITY_LEVELS[0]
        )

        # The opportunity title lookup is sent even in check mode, so
        # the token is required in both modes
        require_env_vars('AMPLIFY_TOKEN')

        # Announce the run mode
        logger.info(
            'Run mode is "Create Amplify Shifts"'
        )
        # Create CreateShifts object
        shifts = CreateShifts(
            input_file=args.input_file,
            check_mode=check_mode,
            output_verbosity=output_verbosity
        )
        # Create shifts
        shifts.create_new_shifts()

    # Run the application in 'post_slack_summary' mode (argparse
    # guarantees exactly one mode flag, so this is the Slack case)
    else:
        # Validate that only Slack-mode options were supplied
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
        if any(
            value is not None
            for value in (
                args.gcal_name,
                args.input_file,
                args.output_verbosity
            )
        ):
            parser.error(
                '-n/--gcal-name, -i/--input-file, and '
                '-o/--output-verbosity are not valid with '
                '-s/--post-slack-summary'
            )

        # Apply the check-mode default (dry run) and resolve the channel
        check_mode = (
            True if args.check_mode is None else args.check_mode
        )
        channel = (
            args.slack_channel
            or SLACK_CHANNEL
            or SLACK_DEV_CHANNEL
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
            days=args.days
        )
        SlackNotifier(
            channel=channel,
            check_mode=check_mode
        ).post_summary(
            summary=summary
        )

    return None


# Run main application function
if __name__ == '__main__':
    main()
