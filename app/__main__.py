#!/usr/bin/env python3
""" Main application script. """

# Imports - Python Standard Library
import argparse
from typing import Optional, Sequence

# Imports - Local
from star_pass.amplify_shifts import CreateShifts
from star_pass.gcal_data import GCALData
from star_pass._helpers import Helpers
from star_pass._logging import get_logger
from star_pass import _defaults

# Constants
VERBOSITY_LEVELS = _defaults.VERBOSITY_LEVELS
# Valid Google Calendar names, derived from the configured calendars so
# the choices stay in sync with any deployment overrides.
GCAL_NAMES = tuple(_defaults.GCAL_CALENDARS)

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


# Build the command-line argument parser
def build_parser() -> argparse.ArgumentParser:
    """ Build the command-line argument parser.

        Defines a subcommand per run mode ('create_amplify_shifts' and
        'get_gcal_events', each with a single-letter alias) so the tool
        exposes a real '--help', validates arguments, and returns a
        non-zero exit code on misuse.

        Args:
            None.

        Returns:
            parser (argparse.ArgumentParser):
                The configured top-level argument parser.
    """

    parser = argparse.ArgumentParser(
        prog='star-pass',
        description=(
            'Automate volunteer-shift management in Galaxy Digital '
            'Amplify.'
        )
    )

    # A run mode is required; each subcommand carries its own arguments.
    subparsers = parser.add_subparsers(
        dest='mode',
        required=True,
        metavar='mode'
    )

    # Run mode: create Amplify shifts from a CSV file (alias: c)
    create_parser = subparsers.add_parser(
        'create_amplify_shifts',
        aliases=['c'],
        help='Create Amplify shifts from a formatted CSV file.'
    )
    create_parser.add_argument(
        '--input-file',
        required=True,
        help='Name of the CSV file to read shift data from.'
    )
    create_parser.add_argument(
        '--check-mode',
        type=_bool_arg,
        default=True,
        metavar='{true,false}',
        help='Prepare requests without sending them. Default: true.'
    )
    create_parser.add_argument(
        '--output-verbosity',
        choices=VERBOSITY_LEVELS,
        default=VERBOSITY_LEVELS[0],
        help=f'Amount of detail to display. Default: {VERBOSITY_LEVELS[0]}.'
    )

    # Run mode: collect Google Calendar events into a CSV file (alias: g)
    gcal_parser = subparsers.add_parser(
        'get_gcal_events',
        aliases=['g'],
        help='Collect events from a Google Calendar into a CSV file.'
    )
    gcal_parser.add_argument(
        '--gcal-name',
        required=True,
        choices=GCAL_NAMES,
        help='Name of the Google Calendar to collect events from.'
    )

    return parser


# Main application function definition
def main(
        argv: Optional[Sequence[str]] = None
) -> None:
    """ Main application.

        Args:
            argv (Optional[Sequence[str]]):
                Argument list to parse.  Defaults to None, which parses
                'sys.argv'.  Primarily an injection point for tests.

        Returns:
            None.
    """

    # Parse CLI arguments (argparse exits non-zero on invalid input)
    parser = build_parser()
    args = parser.parse_args(argv)

    # Run the application in 'create_amplify_shifts' mode
    if args.mode in ('create_amplify_shifts', 'c'):
        # Announce the run mode
        logger.info(
            'Run mode is "Create Amplify Shifts"'
        )
        # Create CreateShifts object
        shifts = CreateShifts(
            input_file=args.input_file,
            check_mode=args.check_mode,
            output_verbosity=args.output_verbosity
        )
        # Create shifts
        shifts.create_new_shifts()

    # Run the application in 'get_gcal_events' mode
    elif args.mode in ('get_gcal_events', 'g'):
        # Announce the run mode
        logger.info(
            'Run mode is "Get Google Calendar Events"'
        )
        # Create GCALData object
        GCALData(
            gcal_name=args.gcal_name
        )

    return None


# Run main application function
if __name__ == '__main__':
    main()
