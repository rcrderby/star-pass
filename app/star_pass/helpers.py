#!/usr/bin/env python3
""" Helper methods for star_pass.py """

# Imports - Python Standard Library
from typing import Any
from pprint import pprint as pp


class Helpers:
    """ star_pass helper methods. """

    def __init__(self) -> None:
        """ Helpers initialization method.

            Args:
                None.

            Returns:
                None.
        """

        return None

    def printer(
            self,
            message: Any,
            end: str = '\n',
            pretty_print: bool = False
    ) -> None:
        """ Message printer.

            Args:
                message (Any):
                    Pre-formatted content to print.

                end (str):
                    String appended at the end of the message.  Default
                    is a new line.  Ignored when pretty_print is True.

                pretty_print (bool):
                    Display the output using pprint.pprint.  Default is
                    False.

            Returns:
                None.
        """

        # Print formatted output
        if pretty_print is False:
            # Standard print
            print(
                message,
                end=end
            )
        else:
            # Pretty Print
            pp(message)

        return None

    def shift_lookup(self) -> None:
        """ Print messages.

            Args:
                None.

            Returns:
                None.
        """

        return None
