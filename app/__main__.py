#!/usr/bin/env python3
""" Main application script. """

# Imports - Python Standard Library
from sys import argv
from typing import Dict

# Imports - Third-Party

# Imports - Local
from star_pass.star_pass import CreateShifts

# Load environment variables

# Constants


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

    if len(argv) > 1:
        # Slice the file name from the list of arguments
        arg_list = argv[1:]

        # Create a Dict to store args
        cli_args = {}

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

    # Create CreateShifts object
    shifts = CreateShifts(
        **cli_args
    )

    # Create shifts
    shifts.create_new_shifts()

    return None


# Run main application function
if __name__ == '__main__':
    main()
