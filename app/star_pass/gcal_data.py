#!/usr/local/bin/python3
""" Google Calendar shift management classes and methods. """

# Imports - Python Standard Library
from copy import copy
from datetime import datetime
from math import floor
from os import getenv
from typing import Any, Dict, Iterable, List

# Imports - Third-Party
from dotenv import load_dotenv
from pandas import DataFrame as df

# Imports - Local
from . import _defaults
from .helpers import Helpers

# Load environment variables
load_dotenv(
    dotenv_path='./.env',
    encoding='utf-8'
)

# Constants
# Authentication
GCAL_TOKEN = getenv(
    key='GCAL_TOKEN'
)

# HTTP request configuration
BASE_HEADERS = _defaults.BASE_HEADERS
GCAL_PRACTICE_CAL_ID = _defaults.GCAL_PRACTICE_CAL_ID
BASE_GCAL_ENDPOINT = _defaults.BASE_GCAL_ENDPOINT
BASE_GCAL_PARAMS = _defaults.BASE_GCAL_PARAMS

BASE_GCAL_URL = getenv(
    key='BASE_GCAL_URL',
    default=_defaults.BASE_GCAL_URL
)
HTTP_TIMEOUT = int(
    getenv(
        key='HTTP_TIMEOUT',
        default=_defaults.HTTP_TIMEOUT
    )
)

# Date and time management
DEFAULT_SLOTS = _defaults.DEFAULT_SLOTS
DATE_TIME_FORMAT = _defaults.DATE_TIME_FORMAT

# Shift lookup data
SHIFT_INFO = _defaults.SHIFT_INFO


class GCALData:
    """ Collect and manage Google Calendar data. """
    def __init__(
            self,
    ) -> None:
        """ Class initialization method.

            Args:
                None.

            Return:
                None.
        """

        # Initialize helper methods
        self.helpers = Helpers()

        return None

    def get_shift_length(
            self,
            shift_start: datetime,
            shift_end: datetime
    ) -> int:
        """ Determine the length of a shift.

            Args:
                shift_start (datetime):
                    datetime.datetime object with the shift start date and
                    time.

                shift_end (datetime):
                    datetime.datetime object with the shift end date and
                    time.

            Returns:
                shift_length (int):
                    Integer of shift length in minutes.
        """

        # Calculate the time delta between 'shift_start' and 'shift_end'
        delta = shift_end - shift_start

        # Determine the number of minutes rounded down to the nearest minute
        shift_length = floor(delta.seconds / 60)

        return shift_length

    def datetime_to_string(
            self,
            datetime_object: str,
            datetime_string_format: str = DATE_TIME_FORMAT
    ) -> str:
        """ Format an ISO datetime object as a string.

            Args:
                datetime_object (str[datetime]):
                    String representation of a datetime.datetime object
                    in ISO format:

                    2024-10-06T12:00:00-07:00

                datetime_string_format (str):
                    Output string format for datetime object.

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

    def get_gcal_shift_data(
            self,
            query_strings: Iterable[str] | str,
            timeMin: datetime,  # pylint: disable=invalid-name
            timeMax: datetime,  # pylint: disable=invalid-name
            timeout: int = HTTP_TIMEOUT
    ) -> Dict[Any, Any]:
        """ Get shift date from the Google Calendar.

            Args:
                query_strings (Iterable[str] | str):
                    Iterable of query strings or single query string
                    to pass to the Google Calendar service in order to
                    filter results for specific events.

                    Example:
                        Use 'scrimmage' to get scrimmage events and use
                        'officials' to get officiating practice events.

                timeMin (datetime):
                    Start date/time for shifts in calendar query.

                timeMax (datetime):
                    End date/time for shifts in calendar query.

                timeout (int):
                    HTTP timeout.  Default is HTTP_TIMEOUT.

            Returns:
                gcal_data (Dict[Any, Any]):
                    Data returned by the Google Calendar service.
        """

        # Create a list of shifts for Google Calendar data
        gcal_data = []

        # Set HTTP request variables
        method = 'GET'
        headers = BASE_HEADERS

        # Construct URL
        url = (
            f'{BASE_GCAL_URL}'
            f'{GCAL_PRACTICE_CAL_ID}'
            f'{BASE_GCAL_ENDPOINT}'
        )

        # Construct base URL parameters
        params = {}
        params.update(**BASE_GCAL_PARAMS)
        params.update({'q': ''})
        params.update({'timeMin': timeMin})
        params.update({'timeMax': timeMax})
        params.update({'key': GCAL_TOKEN})

        # Loop over keywords to construct consolidated results
        for query_string in query_strings:

            # Update the 'q' query string parameter
            params.update({'q': query_string})

            # Construct API request data
            api_request_data = {
                'method': method,
                'url': url,
                'headers': headers,
                'params': params,
                'timeout': timeout
            }

            # Send API request
            response = self.helpers.send_api_request(
                api_request_data=api_request_data
            )

            # Add matching results to `gcal_data`
            gcal_data.append(response.json().get('items'))

        return gcal_data

    def process_gcal_data(
            self,
            gcal_data: Dict[Any, Any]
    ) -> List[Dict[str, str]]:
        """ Read and process Google Calendar data JSON.

            Produce a list of shifts from the Google Calendar JSON.

            Args:
                gcal_data (Dict[Any, Any]):
                    Google Calendar JSON data.

            Returns:
                gcal_shifts (List[Dict[str, str]]:
                    List of shift dictionaries in the format:
                    [
                        {
                            need_name: <summary>,
                            need_id: ''
                            start_date: split of <start[dateTime]>,
                            start_time: split of <start[dateTime]>
                            duration: <end[dateTime]>-<start[dateTime]>,
                            slots: ''
                        },
                        {
                            need_name: <summary>,
                            need_id: ''
                            start_date: split of <start[dateTime]>,
                            start_time: split of <start[dateTime]>
                            duration: <end[dateTime]>-<start[dateTime]>,
                            slots: ''
                        }
                    ]
        """

        # Create a list of shifts from Google Calendar
        gcal_shifts = []

        # Add Google Calendar data to 'gcal_shifts'
        for item in gcal_data:
            # Get the shift name, start, and end values
            shift_name = item['summary']
            shift_start = item['start']['dateTime']
            shift_end = item['end']['dateTime']

            # Get the shift duration
            shift_duration = self.get_shift_length(
                shift_start=datetime.fromisoformat(shift_start),
                shift_end=datetime.fromisoformat(shift_end)
            )

            # Format the shift start values as strings
            shift_start_string = self.datetime_to_string(
                datetime_object=shift_start
            )

            start_date, start_time = shift_start_string.split(
                sep=' '
            )

            # Split the start date and start time values to separate variables
            gcal_shifts.append(
                {
                    'need_name': shift_name,
                    'need_id': '',
                    'start_date': start_date,
                    'start_time': start_time,
                    'duration': shift_duration,
                    'slots': DEFAULT_SLOTS
                }
            )

        return gcal_shifts

    def generate_shift_csv(
            self,
            gcal_shifts: List[Dict[str, str]]
    ) -> str:
        """ Generate CSV file from shift data.

            Args:
                gcal_shifts (List[Dict[str, str]]:
                    List of shift dictionaries in the format:
                    [
                        {
                            need_name: <summary>,
                            need_id: ''
                            start_date: split of <start[dateTime]>,
                            start_time: split of <start[dateTime]>
                            duration: <end[dateTime]>-<start[dateTime]>,
                            slots: ''
                        },
                        {
                            need_name: <summary>,
                            need_id: ''
                            start_date: split of <start[dateTime]>,
                            start_time: split of <start[dateTime]>
                            duration: <end[dateTime]>-<start[dateTime]>,
                            slots: ''
                        }
                    ]

            Returns:
                csv_shift_data (str):
                    String of shift data in CSV format.
        """

        # Create a list of shifts for Amplify
        amplify_shifts = []

        # Loop up Amplify need IDs for Google Calendar shifts
        for shift in gcal_shifts:
            # Perform keyword lookup
            # Convert 'need_name' to lowercase for searching
            need_name = shift.get('need_name').lower()
            # Loop over keywords to search for a shift match
            for keyword, shift_info in SHIFT_INFO.items():
                # Search for 'SHIFT_INFO' keywords in 'need_name'
                if need_name.find(keyword) != -1:
                    # Loop over the list of 'need_ids' to add shifts for each
                    for need_id in shift_info['need_ids']:
                        # Create a copy of the current 'shift'
                        new_shift = copy(shift)
                        # Assign a 'need_id' to the new shift
                        new_shift.update({'need_id': need_id})
                        # Add a new shift to the 'amplify_shifts' list
                        amplify_shifts.append(new_shift)
                    # Exit the loop after a successful match
                    break

        # Convert the shift data to a Pandas DataFrame for CSV export
        amplify_shifts_data_frame = df(amplify_shifts)

        # Convert the Pandas DataFrame to CSV data
        csv_data = amplify_shifts_data_frame.to_csv(
            index=False
        )

        return csv_data
