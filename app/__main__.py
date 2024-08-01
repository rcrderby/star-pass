#!/usr/bin/env python3
""" Main application script. """

# Imports - Python Standard Library
from sys import argv
from typing import Dict

# Imports - Third-Party

# Imports - Local
from star_pass.star_pass import AmplifyShifts

# Load environment variables

# Constants


# Check for CLI arguments
def check_cli_args() -> Dict[str, str]:
    """ Check for CLI arguments.

        Args:
            None.

        Returns:
            args (Dict[str, str]):
                Dict of CLI arguments and their values that map to Dict
                keys and values, respectively.
    """

    if len(argv) > 1:
        pass

    return None


# Main application function definition
def main() -> None:
    """ Main application.

        Args:
            None.

        Returns None.

    """

    # Create AmplifyShifts object
    shifts = AmplifyShifts(
        check_mode=True
    )

    # Create shifts
    shifts.create_new_shifts()

    return None


# Run main application function
if __name__ == '__main__':
    main()
