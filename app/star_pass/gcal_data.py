#!/usr/local/bin/python3
""" Google Calendar shift management classes and methods. """

# Imports - Python Standard Library
from copy import copy
from datetime import datetime
from math import floor
from os import getenv
from pathlib import Path
from typing import Any, Dict, List
import sys

# Imports - Third-Party
from pandas import DataFrame as df

# Imports - Local
from . import _defaults
from ._helpers import Helpers, load_env_file

# Load environment variables
load_env_file()

# Constants
# Authentication
GCAL_TOKEN = getenv(
    key='GCAL_TOKEN'
)

# HTTP request configuration
BASE_GCAL_HEADERS = copy(_defaults.BASE_HEADERS)
GCAL_CALENDARS = _defaults.GCAL_CALENDARS
BASE_GCAL_ENDPOINT = _defaults.BASE_GCAL_ENDPOINT
BASE_GCAL_PARAMS = _defaults.BASE_GCAL_PARAMS
BASE_GCAL_URL = _defaults.BASE_GCAL_URL
HTTP_TIMEOUT = _defaults.HTTP_TIMEOUT

# Date and time management
DATE_TIME_FORMAT = _defaults.DATE_TIME_FORMAT
FILE_NAME_DATE_TIME_FORMAT = _defaults.FILE_NAME_DATE_TIME_FORMAT

# Shift lookup data
SHIFTS_INFO = _defaults.SHIFTS_INFO

# File management data
FILE_ENCODING = _defaults.FILE_ENCODING
INPUT_DIR_PATH = _defaults.INPUT_DIR_PATH
INPUT_FILE_EXTENSION = _defaults.INPUT_FILE_EXTENSION

# Default date and time values
DEFAULT_GCAL_TIME_MIN = _defaults.GCAL_TIME_MIN
DEFAULT_GCAL_TIME_MAX = _defaults.GCAL_TIME_MAX


class GCALShift:
    """ Object to store Google Calendar shift data. """
    def __init__(
            self,
            gcal_item: Dict
    ) -> None:
        """ Class initialization method.

            Args:
                gcal_item (Dict):
                    Dictionary of raw Google Calendar event data.

                 Object Attributes:
                    need_name (str):
                        Shift name used to look up need details.

                    need_details (Dict):
                        Need details including need IDs, number of
                        slots per need ID, and start and end times
                        offset times.

                    start_date (str):
                        Shift start date string formatted as %Y-%m-%d.

                    start_time (str):
                        Shift start time string formatted as %H:%M.

                    duration (int):
                        Shift duration in minutes.

            Returns:
                None.
        """

        # Set initial attribute values
        self.need_name = gcal_item['summary']
        self.need_details = None
        self.item_start = gcal_item['start']['dateTime']
        self.item_end = gcal_item['start']['dateTime']
        self.duration = None

        return None


class GCALData:
    """ Collect and manage Google Calendar data. """
    def __init__(
            self,
            gcal_name: str,
            auto_prep_data: bool = True,
            **kwargs: Any
    ) -> None:
        """ Class initialization method.

            Args:
                gcal_name (str):
                    Name of the Google Calendar to request data from.
                    Example: 'Practices' or 'Events'

                auto_prep_data (bool, optional):
                    Automatically run methods that:

                    1. Collects shift data from the Google Calendar
                       service.
                    2. Formats the Google Calendar shift data to
                       comply with the Amplify API shift format.
                    3. Converts the shift data to a CSV format.
                    4. Writes the CSV shift data to a file.

                    When 'auto_prep_data' is True, creating an instance
                    of the 'GCALData' class will automatically attempt
                    to prepare data.  When 'auto_prep_data' is False,
                    you may manually run the these functions.

                    Functions that prepare data include:

                        get_gcal_shift_data()
                        process_gcal_data()
                        generate_shift_csv()
                        write_shift_csv_file()

                    The default value is True.

                **kwargs (Any, optional):
                    Unspecified keyword arguments.

            Return:
                None.
        """

        # Initialize helper methods
        self.helpers = Helpers()

        # Set Class initialization values
        self.auto_prep_data = auto_prep_data

        # Validate the 'gcal_name' argument value
        self.gcal_name = gcal_name.lower()
        self.helpers.get_gcal_info(
            gcal_name=gcal_name.lower()
        )

        # Call methods to initialize the workflow
        if self.auto_prep_data is True:
            self.gcal_shift_data = self.get_gcal_shift_data(
                timeMin=DEFAULT_GCAL_TIME_MIN,
                timeMax=DEFAULT_GCAL_TIME_MAX
            )
            self.gcal_shifts = self.process_gcal_shift_data(
                gcal_shift_data=self.gcal_shift_data
            )
            self.csv_data = self.generate_shift_csv(
                gcal_shifts=self.gcal_shifts
            )
            self.write_shift_csv_file(
                csv_data=self.csv_data
            )

        return None

    def _create_gcal_shift(
            self,
            gcal_item: Dict[Dict, str]
    ) -> GCALShift:
        """ Create a GCalData object with relevant shift data.

            Args:
                gcal_item (Dict[Dict, str]):
                    Individual Google Calendar item with shift data.

            Returns:
                gcal_shift (GCALShift):
                    GCALShift object with relevant shift data.
        """

        # Create 'GCALShift' object
        gcal_shift = GCALShift(gcal_item)

        # Get details for the closest 'need_name' match
        gcal_shift.need_details = self.helpers.search_shift_info(
            gcal_name=self.gcal_name,
            need_name=gcal_shift.need_name
        )

        return gcal_shift

    def _calculate_shift_duration(
            self,
            gcal_shift: GCALShift
    ) -> int:
        """ Calculate the duration of a shift

            Offset the start and end times if necessary.

            Args:
                gcal_shift (GCALShift):
                    GCALShift object with relevant shift data.

            Returns:
                shift_duration (int):
                    Length of a shift in minutes
        """

        # TODO
        # Determine the number of shift minutes rounded to the nearest minute
        # gcal_shift.duration = self._calculate_shift_duration(
        #     gcal_shift=gcal_shift
        # )

        # Calculate shift start and end times with any specified offset(s)
        start = gcal_shift.item_start.minute + gcal_shift.need_details.get(
            'offset_start', 0
        )
        end = gcal_shift.item_end.minute + gcal_shift.need_details.get(
            'offset_end', 0
        )

        # Calculate the time delta between 'shift_start' and 'shift_end'
        start_end_delta = start - end

        # Determine the number of shift minutes rounded to the nearest minute
        shift_duration = floor(start_end_delta.seconds / 60)

        return shift_duration

    def get_gcal_shift_data(  # pylint: disable=too-many-locals
            self,
            timeMin: str,  # pylint: disable=invalid-name
            timeMax: str,  # pylint: disable=invalid-name
            timeout: int = HTTP_TIMEOUT
    ) -> Dict[Any, Any]:
        """ Get shift data from the Google Calendar.

            Args:
                timeMin (str):
                    ISO-formatted string start date/time for shifts in
                    calendar query

                    Example:
                        '2024-09-01T00:00:00-00:00'

                timeMax (str):
                    ISO-formatted string end date/time for shifts in
                    calendar query.

                    Example:
                        '2024-10-10T00:00:00-00:00'

                timeout (int, optional):
                    HTTP timeout.  Default is HTTP_TIMEOUT.

            Returns:
                gcal_shift_data (Dict[Any, Any]):
                    Data returned by the Google Calendar service.
        """

        # Display status message
        message = '\nReading data from the Google Calendar service...'
        self.helpers.printer(
            message=message
        )

        # Create a list of shifts for Google Calendar data
        gcal_shift_data = []

        # Set HTTP request variables
        method = 'GET'
        headers = BASE_GCAL_HEADERS

        # Set Google Calendar variables
        gcal_id = GCAL_CALENDARS[self.gcal_name].get('gcal_id')
        query_strings = GCAL_CALENDARS[self.gcal_name].get('query_strings')

        # Confirm the Google calendar variables are not None
        if gcal_id is None or query_strings is None:
            # Display an error message and exit
            message = '\n** Invalid Google Calendar Data **\n'
            self.helpers.printer(
                message=message,
                file=sys.stderr
            )
            self.helpers.exit_program(status_code=1)

        # Construct URL
        url = (
            f'{BASE_GCAL_URL}'
            f'{gcal_id}'
            f'{BASE_GCAL_ENDPOINT}'
        )

        # Construct base URL parameters
        params = {}
        params.update(**BASE_GCAL_PARAMS)
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

            # Add matching results to `gcal_shift_data`
            gcal_shift_data += response.json().get('items')

        return gcal_shift_data

    def process_gcal_shift_data(
            self,
            gcal_shift_data: List[Dict[str, str]]
    ) -> List[GCALShift]:
        """ Read and process Google Calendar data JSON.

            Produce a list of shifts from the Google Calendar JSON.

            Args:
                gcal_shift_data List[Dict[str, str]]):
                    Google Calendar JSON data.

            Returns:
                gcal_shifts (List[GCALShift]:
                    List of GCALShift objects.
        """

        # Display preliminary status message
        message = 'Processing Google Calendar event data...'
        self.helpers.printer(
            message=message,
            end=''
        )

        # Create a list of shifts from Google Calendar
        gcal_shifts = []

        # Add Google Calendar data to 'gcal_shifts'
        for gcal_item in gcal_shift_data:

            # Convert each Google Calendar item to an GCALShift object
            gcal_shift = self._create_gcal_shift(
                gcal_item=gcal_item
            )

            # TODO Start
            # Get the shift duration
            # shift_duration = self._get_shift_length(
            #     shift_start=datetime.fromisoformat(shift_start),
            #     shift_end=datetime.fromisoformat(shift_end)
            # )

            # Format the shift start values as strings
            # shift_start_string = self.helpers.iso_datetime_to_string(
            #     datetime_object=shift_start
            # )

            # start_date, start_time = shift_start_string.split(
            #     sep=' '
            # )

            # Split the start date and start time values to separate variables
            # gcal_shifts.append(
            #     {
            #         'need_name': shift_name,
            #         'need_id': '',
            #         'start_date': start_date,
            #         'start_time': start_time,
            #         'duration': shift_duration,
            #         'slots': ''
            #     }
            # )
            # TODO End

            gcal_shifts.append(gcal_shift)

        # Display status message
        message = "done."
        self.helpers.printer(message=message)

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
                csv_data (str):
                    String of shift data in CSV format.
        """

        # Display preliminary status message
        message = 'Converting Google Calendar events to Amplify shifts...'
        self.helpers.printer(
            message=message,
            end=''
        )

        # Create a list of shifts for Amplify
        amplify_shifts = []

        # Loop up Amplify need IDs for Google Calendar shifts
        for shift in gcal_shifts:
            # Perform keyword lookup
            # Convert 'need_name' to lowercase for searching
            need_name = shift.get('need_name').lower()
            # Loop over keywords to search for a shift match
            for keyword, shift_info in SHIFTS_INFO.get(
                self.gcal_name
            ).items():
                # Search for 'SHIFT_INFO' keywords in 'need_name'
                if need_name.find(keyword) != -1:
                    # Loop over the list of 'need_ids' to add shifts for each
                    for need_id in shift_info['need_ids']:
                        # Create a copy of the current 'shift'
                        new_shift = copy(shift)
                        # Assign a 'need_id' to the new shift
                        new_shift.update({'need_id': need_id.get('id')})
                        # Assign a number of 'slots' to the new shift
                        new_shift.update({'slots': need_id.get('slots')})
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

        # Display status message
        message = "done."
        self.helpers.printer(message=message)

        return csv_data

    def write_shift_csv_file(
            self,
            csv_data: str
    ) -> None:
        """ Write a CSV file of shift data.

            Args:
                csv_data (str):
                    String of shift data in CSV format.

            Returns:
                None.
        """

        # Display preliminary status message
        message = 'Writing Amplify shift data to a CSV file...'
        self.helpers.printer(
            message=message,
            end=''
        )

        # Create timestamped file name
        timestamp = datetime.now().strftime(
            format=FILE_NAME_DATE_TIME_FORMAT
        )
        file_path = INPUT_DIR_PATH
        file_name = f'gcal_shifts_{timestamp}{INPUT_FILE_EXTENSION}'
        file = Path.joinpath(
            file_path,
            file_name
        )

        # Write a CSV file of shift data
        with open(
            file=file,
            mode='wt',
            encoding=FILE_ENCODING
        ) as csv_file:
            csv_file.write(csv_data)

        # Print file information
        message = (
            'done.'
            f'\n\nWrote CSV data to "{file}"\n'
        )
        self.helpers.printer(
            message=message
        )

        return None
