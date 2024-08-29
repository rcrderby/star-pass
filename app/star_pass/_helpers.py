#!/usr/bin/env python3
""" Helper methods for star_pass.py """

# Imports - Python Standard Library
from ast import literal_eval
from datetime import datetime
from typing import Any, Dict
from pprint import pprint as pp
import sys

# Imports - Third-Party
from dateparser import parse
from dotenv import load_dotenv
from requests import exceptions, request, Response

# Imports - Local
from . import _defaults

# Constants
DATE_TIME_FORMAT = _defaults.DATE_TIME_FORMAT
ENV_FILE_PATH = _defaults.ENV_FILE_PATH
FILE_ENCODING = _defaults.FILE_ENCODING


# Class definitions
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

            Examples:
                '5/6/24 11:30' --------------> '2024-05-06 11:30'
                '6 may 2024 11:30 am' -------> '2024-05-06 11:30'
                'may 6th, 2024 11:30 a.m.' --> '2024-05-06 11:30'

                See https://dateparser.readthedocs.io/en/latest
                for more information.

            Args:
                date_time_string (str):
                    Space-separated concatenation of a common date
                    format and a common time format.

            Returns:
                formatted_date_time_string (str):
                    Date/time string in the Amplify-specified format.

                    Example:
                        '2024-05-06 11:30'

                    See https://api.galaxydigital.com/docs/#/Need/needAddShifts
        """

        # Parse date/time string into datetime.datetime object
        dt_object = parse(
            date_string=date_time_string
        )

        # Convert 'dt_object' to a formatted string
        formatted_date_time_string = dt_object.strftime(
            format=DATE_TIME_FORMAT
        )

        return formatted_date_time_string

    def iso_datetime_to_string(
            self,
            datetime_object: str,
            datetime_string_format: str = DATE_TIME_FORMAT
    ) -> str:
        """ Convert an ISO-formatted datetime to a simplified format.

            Args:
                datetime_object (str[datetime]):
                    String representation of a datetime.datetime object
                    in ISO format:

                    2024-10-06T12:00:00-07:00

                datetime_string_format (str):
                    Simplified date and time output format.

            Returns:
                datetime_string (str):
                    Date and time as a string, formatted by
                    datetime_string_format.
        """

        # Create a datetime object from the ISO-formatted string
        datetime_object = datetime.fromisoformat(datetime_object)

        # Format the datetime object as a string with `datetime_string_format'`
        datetime_string = datetime_object.strftime(datetime_string_format)

        return datetime_string

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
            api_request_data: Dict,
            display_request_status: bool = True
    ) -> Response:
        """ Send API request.

            Args:
                api_request_data (Dict):
                    Dictionary of key, value pairs for API request.
                    Common values include:

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

                display_request_status (bool, optional):
                    Print a message to display the result of the HTTP
                    request.  Default is 'True'.

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
        try:
            if response.ok is not True:
                response.raise_for_status()

        # Handle non-ok HTTP responses
        except exceptions.HTTPError as error:
            # Display error text and exit
            self.printer(
                message=repr(f'{error!r}')
            )
            sys.exit(1)

        # Display the HTTP request status
        if display_request_status is True:
            # Create display URL that does not expose any paths or parameters
            display_url = response.request.url.replace(
                response.request.path_url,
                ''
            )

            # Set HTTP response output message
            output_heading = (
                '** HTTP API Response **\n'
                f'URL: {display_url}\n'
                f'Response: HTTP {response.status_code} {response.reason}'
            )

            # Create output message
            output_message = (
                f'\n{output_heading}\n'
            )

            # Display output message
            self.printer(
                message=output_message
            )

        return response


# Standalone functions
def load_env_file() -> bool:
    """ Load environment variables from an .env file.

        Args:
            None.

        Returns:
            load_env_status (bool):
                Boolean value indicating whether or not the
                'load_dotenv' function reads environment variables
                from the specified file.
    """

    # Load environment variables
    load_env_status = load_dotenv(
        dotenv_path=ENV_FILE_PATH,
        encoding=FILE_ENCODING
    )

    return load_env_status
