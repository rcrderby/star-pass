#!/usr/bin/env python3
""" Main application script. """

# Imports - Python Standard Library
from sys import argv
from typing import Dict

# Imports - Local
from star_pass.amplify_shifts import CreateShifts
from star_pass.gcal_data import GCALData
from app.star_pass._helpers import Helpers
from star_pass import _defaults

# Constants
RUN_MODES = _defaults.RUN_MODES

# Initialize helper methods
helpers = Helpers()


# Check for CLI arguments
def get_cli_args() -> Dict[str, str]:
    """ Check for CLI arguments.

        Args:
            None.

        Returns:
            args (Dict[str, str]):
                Dict of CLI arguments and their values that map to Dict
                keys and values, respectively.
    """

    # Create a Dict to store args
    cli_args = {}

    if len(argv) > 1:
        # Slice the file name from the list of arguments
        arg_list = argv[1:]

        # Parse keys and values from arg_list to add to the 'args' Dict
        for arg in arg_list:
            # Split the argument and its value to separate variables
            arg_key, arg_value = arg.split('=')

            # Remove leading '-' chars and strip outer spaces from 'arg_key'
            arg_key = arg_key.lstrip('-').strip()

            # Strip outer spaces from 'arg_value'
            arg_value = arg_value.strip()

            # Add `arg_key` and `arg_value` to the `args` Dict
            cli_args.update({arg_key: arg_value})

    return cli_args


# Main application function definition
def main() -> None:
    """ Main application.

        Args:
            None.

        Returns None.

    """

    # Get CLI arguments
    cli_args = get_cli_args()

    # Display help
    # Add app usage instructions

    # Initially set the run mode to invalid
    run_mode_valid = False

    # Determine the validity of the 'mode' argument
    run_mode = cli_args.get('mode', '').lower()
    if run_mode in RUN_MODES:
        # Set the run mode to valid
        run_mode_valid = True

    # Run the application in the specified mode
    if run_mode_valid is True:

        # Run the application in 'create_amplify_shifts' mode
        if run_mode in ('create_amplify_shifts', 'c'):
            # Create output message
            output_message = (
                '\n\n** Run mode is "Create Amplify Shifts" **\n'
            )
            # Create CreateShifts object
            shifts = CreateShifts(
                **cli_args
            )
            # Create shifts
            shifts.create_new_shifts()

        # Run the application in 'get_gcal_events' mode
        if run_mode in ('get_gcal_events', 'g'):
            # Create output message
            output_message = (
                '\n\n** Run mode is "Get Google Calendar Events" **\n'
            )
            # Create CreateShifts object
            GCALData(
                **cli_args
            )

    # Display usage instructions and exit if the mode is unset or invalid
    else:
        # Create output message
        output_message = (
            '\n\n** Invalid or unset "mode" argument **\n'
        )

        # Display output message
        helpers.printer(
            message=output_message
        )

    return None


# Run main application function
if __name__ == '__main__':
    main()
