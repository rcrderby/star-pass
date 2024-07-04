#!/usr/bin/env python3
""" Helper methods for star_pass.py """

# Imports - Python Standard Library
from typing import Any, Dict
from pprint import pprint as pp

# Imports - Third-Party
from requests import request, Response


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

    def send_api_request(
            self,
            method: str,
            url: str,
            headers: Dict[str, str],
            json: Any,
            timeout: int
    ) -> Response:
        """ Send API request.

            Args:
                method (str):
                    HTTP method (GET, POST, PUT, PATCH, DELETE).

                url (str):
                    Fully-qualified API endpoint URI.

                headers (Dict[str, str]):
                    HTTP headers.

                json (Any):
                    JSON body.

                timeout (int):
                    HTTP timeout.

            Returns:
                response (requests.Response):
                    HTTP server response object.
        """

        # Send API request
        response = request(
            method=method,
            url=url,
            headers=headers,
            json=json,
            timeout=timeout
        )

        # Check for HTTP errors
        if response.ok is not True:
            response.raise_for_status()

        return response

    def shift_lookup(self) -> None:
        """ Print messages.

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
