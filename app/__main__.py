#!/usr/bin/env python3
""" Main application script. """

# Imports - Local
from star_pass.amplify_shifts import CreateShifts
from star_pass.gcal_data import GCALData
from star_pass._helpers import Helpers
from star_pass._arg_parser import parse_cli_arguments

# Initialize helper methods
helpers = Helpers()

# Parse CLI arguments
cli_args = parse_cli_arguments()


# Main application function definition
def main() -> None:
    """ Main application.

        Args:
            None.

        Returns:
            None.

    """

    return None  # TODO


def create_amplify_shifts():
    """ TODO """

    # Run the application in 'create_amplify_shifts' mode
    # Create output message
    output_message = (
        '\n\n** Run mode is "Create Amplify Shifts" **\n'
    )

    # Display output message
    helpers.printer(
        message=output_message
    )

    # Create CreateShifts object
    shifts = CreateShifts(
        **cli_args
    )

    # Create shifts
    shifts.create_new_shifts()

    return None


def get_gcal_events():
    """ TODO """
    # Run the application in 'get_gcal_events' mode
    output_message = (
        '\n\n** Run mode is "Get Google Calendar Events" **\n'
    )

    # Display output message
    helpers.printer(
        message=output_message
    )

    # Create CreateShifts object
    GCALData(
        **cli_args
    )

    return None


# Run main application function
if __name__ == '__main__':
    main()
