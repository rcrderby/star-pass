#!/usr/local/bin/python3
""" Google Calendar shift management classes and methods. """

# Imports - Python Standard Library
from copy import copy
from datetime import datetime, timedelta
from math import floor
from os import getenv
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Imports - Third-Party
from pandas import DataFrame as df

# Imports - Local
from . import _defaults
from ._helpers import Helpers, load_env_file
from ._logging import get_logger

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
AMPLIFY_DATE_TIME_FORMAT = _defaults.AMPLIFY_DATE_TIME_FORMAT
FILE_NAME_DATE_TIME_FORMAT = _defaults.FILE_NAME_DATE_TIME_FORMAT

# Shift lookup data
SHIFTS_INFO = _defaults.SHIFTS_INFO

# File management data
FILE_ENCODING = _defaults.FILE_ENCODING
INPUT_DIR_PATH = _defaults.INPUT_DIR_PATH
INPUT_FILE_EXTENSION = _defaults.INPUT_FILE_EXTENSION

# Calendar search window format (no default value -- see
# 'get_gcal_time_window').
GCAL_TIME_FORMAT = _defaults.GCAL_TIME_FORMAT

# Module logger
logger = get_logger(__name__)


def _parse_gcal_time(
        name: str,
        value: str
) -> datetime:
    """ Parse a calendar search window value.

        Args:
            name (str):
                Environment variable name, for the error message.

            value (str):
                An ISO 8601 datetime with a UTC offset, for example
                '2099-01-01T00:00:00-00:00'.

        Raises:
            ValueError:
                If 'value' is not a valid ISO 8601 datetime with an
                offset.

        Returns:
            parsed (datetime):
                The parsed datetime.
    """

    try:
        return datetime.strptime(value, GCAL_TIME_FORMAT)
    except (TypeError, ValueError) as error:
        message = (
            f'{name} is not a valid date and time: {value!r}.  Use the '
            f'ISO 8601 format 2099-01-01T00:00:00-00:00.'
        )
        logger.error(message)
        raise ValueError(message) from error


def get_gcal_time_window() -> Tuple[str, str]:
    """ Read and validate the Google Calendar search window.

        'GCAL_TIME_MIN' and 'GCAL_TIME_MAX' bound the calendar search and
        have no default: the window moves with every run, so a default
        would go stale and silently collect zero events.  They are read
        here, when a calendar request is about to run, rather than at
        import time, so the other run modes ('-c' and '-s') do not
        require Google Calendar configuration.

        Raises:
            ValueError:
                If either value is unset, unparseable, or the window does
                not move forward in time.

        Returns:
            window (Tuple[str, str]):
                The validated ('GCAL_TIME_MIN', 'GCAL_TIME_MAX') values,
                unchanged, ready to send as request parameters.
    """

    time_min = getenv('GCAL_TIME_MIN')
    time_max = getenv('GCAL_TIME_MAX')

    # Both values are required for a calendar request
    missing = [
        name
        for name, value in (
            ('GCAL_TIME_MIN', time_min),
            ('GCAL_TIME_MAX', time_max)
        )
        if not value
    ]
    if missing:
        message = (
            f'{" and ".join(missing)} must be set to collect Google '
            'Calendar events.  Set the calendar search window in your '
            '.env file (see .env.example); there is no default, because '
            'a stale window silently collects zero events.'
        )
        logger.error(message)
        raise ValueError(message)

    # A malformed value fails the same way a stale one does, silently,
    # so reject it here rather than send it to the API.
    parsed_min = _parse_gcal_time(name='GCAL_TIME_MIN', value=time_min)
    parsed_max = _parse_gcal_time(name='GCAL_TIME_MAX', value=time_max)

    if parsed_min >= parsed_max:
        message = (
            f'GCAL_TIME_MIN ({time_min}) must be earlier than '
            f'GCAL_TIME_MAX ({time_max}); the current values select an '
            'empty search window.'
        )
        logger.error(message)
        raise ValueError(message)

    return time_min, time_max


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
                    item_end (str):
                        Google Shift end time in ISO format.

                    item_start (str):
                        Google Shift start time in ISO format.

                    need_ids (List):
                        List of need IDs extracted from the
                        `need_details` attribute.

                    need_details (Dict):
                        Need details including need IDs, number of
                        slots per need ID, and start and end times
                        offset times.

                    need_name (str):
                        Shift name used to look up need details.

            Returns:
                None.
        """

        # Set initial attribute values
        self.item_end = gcal_item['end']['dateTime']
        self.item_start = gcal_item['start']['dateTime']
        self.need_details = None
        self.need_ids = None
        self.need_name = gcal_item['summary']

        return None


# pylint: disable=too-many-arguments, too-many-positional-arguments
class AmplifyShift:
    """ Object to store prepared Amplify shift data. """
    def __init__(
            self,
            need_name: str | None = None,
            need_id: int | str | None = None,
            start_date: str | None = None,
            start_time: str | None = None,
            duration: int | str | None = None,
            slots: int | str | None = None
    ) -> None:
        """ Class initialization method.

            Args:
                None.

                Object Attributes:
                    need_name (str | None, optional):
                        Google Calendar shift name.

                    need_id (int | str | None, optional):
                        Amplify need ID.

                    start_date (str | None, optional):
                        Shift start date string formatted as %Y-%m-%d.

                    start_time (str | None, optional):
                        Shift start time string formatted as %H:%M.

                    duration (str | int | None, optional):
                        Shift duration in minutes.

                    slots (str | int | None, optional):
                        Number of available shift slots.

            Returns:
                None
        """

        # Set initial attribute values
        self.need_name = need_name
        self.need_id = need_id
        self.start_date = start_date
        self.start_time = start_time
        self.duration = duration
        self.slots = slots

        return None

    def args_to_dict(self) -> Dict:
        """ Return instance attributes in a dictionary.

            Args:
                None.

            Returns:
                attributes_dict (Dict):
                    Dictionary of instance attributes in the format:

                    {
                        'need_name': 'Need Name',
                        'need_id': 000000,
                        'start_date': '2099-01-01',
                        'start_time': '12:00',
                        'duration': 60,
                        'slots': 20
                    }
        """

        # Convert instance attributes to a dictionary
        attributes_dict = vars(self)

        return attributes_dict


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
                        filter_shifts()
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
            # Read the search window here, so an unset or invalid value
            # fails before any request is sent.
            time_min, time_max = get_gcal_time_window()
            self.gcal_shift_data = self.get_gcal_shift_data(
                timeMin=time_min,
                timeMax=time_max
            )
            self.gcal_shifts = self.process_gcal_shift_data(
                gcal_shift_data=self.gcal_shift_data
            )
            self.filtered_gcal_shifts = self.filter_shifts(
                gcal_shifts=self.gcal_shifts
            )
            self.csv_data = self.generate_shift_csv(
                filtered_gcal_shifts=self.filtered_gcal_shifts
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

        # Extract the 'need_ids' key from the `gcal_shift` object
        gcal_shift.need_ids = gcal_shift.need_details['need_ids']

        return gcal_shift

    def _get_shift_time_data(
            self,
            need_id: Dict[str, int | str],
            end_time: str,
            start_time: str
    ) -> Tuple[str, str, int | str]:
        """ Calculate the date, time, and duration of a shift.

            Offset the start and end times if necessary.

            Args:
                need_id (Dict[str, int | str]):
                    Dictionary of data associated with a given need ID
                    including offset start and end times.

                end_time (str):
                    Google Shift end time in ISO format.

                start_time (str):
                    Google Shift start time in ISO format.

            Returns:
                shift_timing (Tuple[str, str, int | str]):
                    Tuple with formatted values for a shift's start
                    date, start time, and duration.
        """

        # Get the shift offset start and end values
        offset_start = timedelta(
            minutes=need_id.get('offset_start', 0)
        )
        offset_end = timedelta(
            minutes=need_id.get('offset_end', 0)
        )

        # Convert the shift start and end ISO strings to datetime objects
        shift_start_datetime = datetime.fromisoformat(start_time)
        shift_end_datetime = datetime.fromisoformat(end_time)

        # Adjust the shift start and end times based on the offset values
        shift_start_datetime = shift_start_datetime + offset_start
        shift_end_datetime = shift_end_datetime + offset_end

        # Calculate the time delta between the start and end of a shift
        start_end_delta = shift_end_datetime - shift_start_datetime

        # Convert the time delta to minutes
        shift_duration = floor(start_end_delta.seconds / 60)

        # Ensure `shift_duration` does note exceed the shift's `max_length`
        max_length = need_id.get('max_length', None)
        if max_length is not None:
            shift_duration = min(shift_duration, max_length)

        # Convert the shift start time to a formatted string
        shift_start_string = shift_start_datetime.strftime(
            format=AMPLIFY_DATE_TIME_FORMAT
        )

        # Split the `shift_start_string` values to separate variables
        shift_start_date, shift_start_time = shift_start_string.split(
            sep=' '
        )

        return shift_start_date, shift_start_time, shift_duration

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
            # Log an error message and exit
            message = f'Invalid Google Calendar data for "{self.gcal_name}"'
            logger.error(message)
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

            # Update the 'q' query string parameter and reset pagination
            # so a page token from a previous query does not carry over.
            params.update({'q': query_string})
            params.pop('pageToken', None)

            # Page through every result set for this query string. The
            # Google Calendar API returns a 'nextPageToken' whenever more
            # results are available (the default page size is 250).
            while True:

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
                response_json = self.helpers.response_json(response)

                # Add matching results to `gcal_shift_data`, defaulting
                # to an empty list when the 'items' key is absent.
                gcal_shift_data += response_json.get('items') or []

                # Stop unless the response supplies a next page token.
                next_page_token = response_json.get('nextPageToken')
                if not next_page_token:
                    break
                params.update({'pageToken': next_page_token})

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

            gcal_shifts.append(gcal_shift)

        # Display status message
        message = "done."
        self.helpers.printer(message=message)

        return gcal_shifts

    def filter_shifts(
            self,
            gcal_shifts: List[Dict[str, str]]
    ) -> List[GCALShift]:
        """ Remove unneeded shifts.

            Filter shifts the from processed Google Calendar Data.

            Args:
                gcal_shifts (List[GCALShift]:
                    List of GCALShift objects.

            Returns:
                filtered_gcal_shifts (List[GCALShift]:
                    Filtered List of GCALShift objects.
        """

        # Display preliminary status message
        message = 'Filtering event data...'
        self.helpers.printer(
            message=message,
            end=''
        )

        # Create a list of filtered Google Calendar Shifts
        filtered_gcal_shifts = []

        # Loop over the list of Google Calendar shifts
        for shift in gcal_shifts:

            # Search for shifts that don't match values in a tuple of prefixes
            if (
                any(
                    filter in shift.need_name.lower()
                    for filter in _defaults.GCAL_PREFIX_FILTERS
                )
                is False
            ):

                # Add non-matching shifts to filtered_gcal_shifts list
                filtered_gcal_shifts.append(shift)

        # Display status message
        message = "done."
        self.helpers.printer(message=message)

        return filtered_gcal_shifts

    def generate_shift_csv(
            self,
            filtered_gcal_shifts: List[GCALShift]
    ) -> str:
        """ Generate CSV file from shift data.

            Args:
                 filtered_gcal_shifts (List[GCALShift]:
                    List of GCALShift objects.

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

        # Look up details for shift object
        for gcal_shift in filtered_gcal_shifts:
            # Loop over each need ID in the 'need_details' dict of a shift
            for need_id in gcal_shift.need_ids:
                # Calculate shift start date, time, and duration
                start_date, start_time, duration = self._get_shift_time_data(
                    need_id=need_id,
                    end_time=gcal_shift.item_end,
                    start_time=gcal_shift.item_start
                )

                # Create an AmplifyShift object for each shift
                amplify_shift = AmplifyShift()
                amplify_shift.need_id = need_id['id']
                amplify_shift.need_name = gcal_shift.need_name
                amplify_shift.start_date = start_date
                amplify_shift.start_time = start_time
                amplify_shift.duration = duration
                amplify_shift.slots = need_id['slots']

                # Add the shift to the `amplify_shifts` list as a dictionary
                amplify_shifts.append(amplify_shift.args_to_dict())

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
