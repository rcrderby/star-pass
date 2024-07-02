#!/usr/bin/env python3
""" Main application script. """

# Imports - Python Standard Library

# Imports - Third-Party

# Imports - Local
from star_pass.star_pass import AmplifyShifts

# Load environment variables

# Constants


# Main application function definition
def main() -> None:
    """ Main application.

        Args:
            None.

        Returns None.

    """

    # Create AmplifyShifts object
    shifts = AmplifyShifts(
        dry_run=True
    )

    # Create shifts
    shifts.create_new_shifts()

    return None


# Run main application function
if __name__ == '__main__':
    main()
