#!/usr/bin/env python3
""" CLI argument parser the star_pass application. """

# Imports - Python Standard Library
import argparse

# Imports - Local
from . import _defaults

# Constants
DESCRIPTION = '''
Star Pass application for Amplify volunteer shift management.

Use case #1:
\tThis is #1

Use case #2:
\tThis is #2
'''

EPILOG = '''
Examples:
\tGet Google Calendar data from the 'events' calendar:
\t./__main__.py -m get_gcal_data -g events

\tCreate Amplify shifts in check mode with the source file 'data_file.csv':
\t./__main__.py -m create_amplify_shifts -i data_file.csv

\tCreate Amplify shifts in live mode with the source file 'data_file.csv':
\t./__main__.py -m create_amplify_shifts -i data_file.csv -D
'''

FORMATTERS = argparse.RawDescriptionHelpFormatter
GCAL_CALENDAR_NAMES = _defaults.GCAL_CALENDAR_NAMES


def parse_cli_arguments():
    """ TODO """
    # Create an ArgumentParser object
    parser = argparse.ArgumentParser(
        description=DESCRIPTION,
        epilog=EPILOG,
        formatter_class=FORMATTERS
    )

    group = parser.add_argument_group('Group title', 'Group description')
    exclusive_group = group.add_mutually_exclusive_group(required=True)
    exclusive_group.add_argument(
        '-C --create_amplify_shifts',
        action='store_true',
        help='Create Amplify Shifts from Google Calendar data mode.'
    )
    exclusive_group.add_argument(
        '-G --get_gcal_data',
        action='store_true',
        help='Get Google Calendar data mode.'
    )

    # group.add_argument(
    #     '-c --create_amplify_shifts',
    #     action='store_true',
    #     help='Create Amplify Shifts from Google Calendar data mode.'
    # )
    # group.add_argument(
    #     '-g --get_gcal_data',
    #     action='store_true',
    #     help='Get Google Calendar data mode.'
    # )
    subparsers = parser.add_subparsers(
        title='subcommands',
        description='valid subcommands',
        help='additional help'
    )
    parser_a = subparsers.add_parser(
        'mode',
        aliases=['m', 'mo'],
        help='Operational mode'
    )
    parser_a.add_argument('g', type=int, help='bar help')
    parser_a.add_argument('bar', type=int, help='bar help')
    # parser_a.set_defaults(func=shifts.create_new_shifts)

    parser_b = subparsers.add_parser('b', help='b help')
    parser_b.add_argument('--baz', choices='XYZ', help='baz help')

    parser.add_argument(
        '-g --gcal_name',
        choices=GCAL_CALENDAR_NAMES,
        help='Google Calendar name (Practices, Events, etc.).'
    )
    parser.add_argument(
        '-i --input_file',
        help='Input data file name.',
        metavar='INPUT_FILE'
    )
    parser.add_argument(
        '-D --disable_check_mode',
        action='store_false',
        dest='check_mode',
        help='Disable check mode.',
    )
    # Parse arguments
    cli_args = parser.parse_args()

    return cli_args


def main():
    """ TODO """
    cli_args = parse_cli_arguments()
    print(cli_args)


if __name__ == '__main__':
    main()
