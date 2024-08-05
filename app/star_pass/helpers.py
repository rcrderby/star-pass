#!/usr/bin/env python3
""" Helper methods for star_pass.py """

# Imports - Python Standard Library
from ast import literal_eval
from datetime import datetime as dt
from typing import Any, Dict
from pprint import pprint as pp
import sys

# Imports - Third-Party
from dateparser import parse
from requests import exceptions, request, Response


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

    def convert_to_bool(
            self,
            arg_value: str
    ) -> str:
        """ Convert a string representation of a boolean to a bool.

            Args:
                arg_value (str):
                    String representation of a boolean.

            Returns:
                arg_bool (bool):
                    bool object converted from a string.
        """

        # Normalize the string capitalization of 'bool_dict_value'
        arg_value = arg_value.lower().capitalize()

        # Convert `bool_dict_value` to a boolean
        arg_bool = literal_eval(arg_value)

        return arg_bool

    def format_date_time(
            self,
            date_time_string: str
    ) -> str:
        """ Format a date and time for Amplify compatibility.

            Args:
                date_time_string (str):
                    Raw date/time string.

            Returns:
                formatted_date_time_string (str):
                    Date/time string.
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

    def send_api_request(
            self,
            api_request_data: Dict
    ) -> Response:
        """ Send API request.

            Args:
                api_request_data (Dict):
                    Dictionary of key, value pairs for API request.

                    method (str):
                        HTTP method (GET, POST, PUT, PATCH, DELETE).

                    url (str):
                        Fully-qualified API endpoint URI.

                    headers (Dict[str, str]):
                        HTTP headers.

                    json (Any | None):
                        JSON body, or None.

                    timeout (int):
                        HTTP timeout.

            Returns:
                response (requests.Response):
                    HTTP server response object.
        """

        # Send API request
        try:
            response = request(**api_request_data)

        # Handle TCP Connection Errors
        except exceptions.ConnectionError as error:
            # Display error text and exit
            self.printer(
                message=repr(f'{error!r}')
            )
            sys.exit(1)

        # Check for HTTP errors
        if response.ok is not True:
            response.raise_for_status()

        return response
