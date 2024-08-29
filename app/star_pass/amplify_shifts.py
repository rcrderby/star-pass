#!/usr/local/bin/python3
""" Amplify shift management classes and methods. """

# Imports - Python Standard Library
from copy import copy
from json import dumps, load
from os import getenv
from pathlib import Path
from typing import Any, Dict

# Imports - Third-Party
import pandas as pd
from dotenv import load_dotenv
from jsonschema import validate, ValidationError
from pandas.core import frame, series
from pandas.core.groupby.generic import DataFrameGroupBy

# Imports - Local
from . import _defaults
from ._helpers import Helpers

# Load environment variables
load_dotenv(
    dotenv_path='./.env',
    encoding='utf-8'
)

# Constants
# Authentication
AMPLIFY_TOKEN = getenv(
    key='AMPLIFY_TOKEN'
)

# HTTP request configuration
BASE_AMPLIFY_HEADERS = copy(_defaults.BASE_HEADERS)
BASE_AMPLIFY_HEADERS.update(
    {'Authorization': f'Bearer {AMPLIFY_TOKEN}'}
)
BASE_AMPLIFY_URL = _defaults.BASE_AMPLIFY_URL
HTTP_TIMEOUT = _defaults.HTTP_TIMEOUT

# Input and output data file paths
INPUT_DIR_PATH = _defaults.INPUT_DIR_PATH
INPUT_FILE_EXTENSION = _defaults.INPUT_FILE_EXTENSION
OUTPUT_DIR_PATH = _defaults.OUTPUT_DIR_PATH
OUTPUT_FILE_EXTENSION = _defaults.OUTPUT_FILE_EXTENSION

# JSON Schema file
JSON_SCHEMA_SHIFT_FILE = _defaults.JSON_SCHEMA_SHIFT_FILE

# CSV data file management
DROP_COLUMNS = _defaults.DROP_COLUMNS.split(sep=', ')
GROUP_BY_COLUMN = _defaults.GROUP_BY_COLUMN
SHIFTS_DICT_KEY_NAME = _defaults.SHIFTS_DICT_KEY_NAME
START_COLUMN = _defaults.START_COLUMN
START_DATE_COLUMN = _defaults.START_DATE_COLUMN
START_TIME_COLUMN = _defaults.START_TIME_COLUMN
KEEP_COLUMNS = _defaults.KEEP_COLUMNS.split(sep=', ')


# Class definitions
class CreateShifts:
    """ CreateShifts base class object. """

    def __init__(
            self,
            input_file: str,
            auto_prep_data: bool = True,
            check_mode: bool = True,
            **kwargs: Any
    ) -> None:
        """ CreateShifts initialization method.

            Args:
                input_file (str):
                    Name for an input data file. For
                    example:

                    shifts = CreateShifts(
                        input_file='data_file.csv'
                    )

                auto_prep_data (bool, optional):
                    Automatically run non-public methods that:

                    1. Imports shift data from a CSV file.
                    2. Removes any duplicate shifts.
                    3. Formats the shift start date and time to comply
                       with the Amplify API shift format.
                    4. Removes any CSV file columns not used by the
                       Amplify API.
                    5. Groups shift data by need ID.
                    6. Formats data to comply with the structure
                       requirements of the Amplify API.
                    7. Creates a JSON-formatted object of shift data
                       to send to the Amplify API.
                    8. Validates the JSON-formatted object using a JSON
                       Schema object.

                    When 'auto_prep_data' is True, creating
                    an instance of the 'CreateShifts' class will
                    automatically attempt to prepare data.  When
                    'auto_prep_data' is False, you may manually run the
                    non-public functions to prepare the data.

                    Non-public functions that prepare data include:

                        _read_shift_csv_data()
                        _remove_duplicate_shifts()
                        _format_shift_start()
                        _drop_unused_columns()
                        _group_shift_data()
                        _create_grouped_series()
                        _create_shift_json_data()
                        _validate_shift_json_data()

                    The default value is True.

                check_mode (bool, optional):
                    Prepare HTTP API requests without sending the
                    requests.  Default value is True.

                **kwargs (Any, optional):
                    Unspecified keyword arguments.

            Returns:
                None.
        """

        # Initialize helper methods
        self.helpers = Helpers()

        # Set Class initialization values
        self.auto_prep_data = auto_prep_data

        # Determine if the value of 'check_mode' is a boolean
        if isinstance(check_mode, bool) is True:
            self.check_mode = check_mode
        else:
            self.check_mode = self.helpers.convert_to_bool(check_mode)

        # Set the base file name
        self.base_file_name = input_file.rstrip(INPUT_FILE_EXTENSION)

        # Set the input file path
        self.input_file = Path.joinpath(
            INPUT_DIR_PATH,
            input_file
        )

        # Set the output file path
        output_file = f'{self.base_file_name}{OUTPUT_FILE_EXTENSION}'
        self.output_file = Path.joinpath(
            OUTPUT_DIR_PATH,
            output_file
        )

        # Placeholder variables for data transformation methods
        self._shift_data: frame.DataFrame | None = None
        self._grouped_shift_data: DataFrameGroupBy | None = None
        self._grouped_series: series.Series | None = None
        self._json_shift_data: Dict = {
            'data': None,
            'valid': None,
            'error': None
        }

        # Call non-public methods to initialize the workflow
        if self.auto_prep_data is True:
            self._read_shift_csv_data()
            self._remove_duplicate_shifts()
            self._combine_date_time_columns()
            self._format_shift_start()
            self._drop_unused_columns()
            self._group_shift_data()
            self._create_grouped_series()
            self._create_shift_json_data()
            self._validate_shift_json_data()

        return None

    def _read_shift_csv_data(
        self,
    ) -> None:
        """ Read shifts data from a CSV file.

            Convert fields to strings for Amplify API compatibility.

            Args:
                None.

            Modifies:
                self._shift_data (frame.DataFrame):
                    Pandas Data Frame of raw shift data.

            Example data structure:
                need_name need_id start_date start_time duration slots
            0   Need 1    000001  1/1/99     12:00      60       20
            1   Need 2    000002  1/1/99     12:00      90       20
            2   Need 3    000002  1/1/99     12:00      60       20
            3   Need 4    000003  1/1/99     12:00      120      20
            4   Need 5    000004  1/1/99     12:00      90       20

            Returns:
                None.
        """

        # Display preliminary status message
        message = f'\nReading shift data from "{self.input_file}"...'
        self.helpers.printer(
            message=message,
            end=''
        )

        # Read CSV file
        shift_data = pd.read_csv(
            filepath_or_buffer=f'{self.input_file}',
            dtype='string'
        )

        # Update self._shift_data
        self._shift_data = shift_data

        # Prepare status message
        if self._shift_data is not None:
            message = "done."
        else:
            message = f'\n\n** Error reading data in "{self.input_file}" **\n'

        # Display status message
        self.helpers.printer(message=message)

        return None

    def _remove_duplicate_shifts(self) -> None:
        """ Remove duplicate shift entries.

            Args:
                self._shift_data (frame.DataFrame):
                    Pandas Data Frame of raw shift data.

            Modifies:
                self._shift_data (frame.DataFrame):
                    Pandas Data Frame of shift data with duplicates
                    removed.

            Example data structure:
                need_name need_id start_date start_time duration slots
            0   Need 1    000001  1/1/99     12:00      60       20
            1   Need 2    000002  1/1/99     12:00      90       20
            2   Need 3    000002  1/1/99     12:00      60       20
            3   Need 4    000003  1/1/99     12:00      120      20
            4   Need 5    000004  1/1/99     12:00      90       20

            Returns:
                None.
        """

        # Display preliminary status message
        message = 'Removing duplicate shifts...'
        self.helpers.printer(
            message=message,
            end=''
        )

        # Drop duplicate rows in self._shift_data
        self._shift_data.drop_duplicates(
            inplace=True,
            keep='first'
        )

        # Display status message
        message = "done."
        self.helpers.printer(message=message)

        return None

    def _combine_date_time_columns(self) -> None:
        """ Combine the 'start_date' and 'start_time' columns to a
            'start_date' column.

            Args:
                self._shift_data (frame.DataFrame):
                    Pandas Data Frame of shift data with duplicates
                    removed.

            Modifies:
                self._shift_data (frame.DataFrame):
                    Pandas Data Frame with shift data in a new 'start'
                    column.

            Example data structure:
                need_name need_id start_date start_time ... start
            0   Need 1    000001  1/1/99     12:00      ... 1/1/99 12:00
            1   Need 2    000002  1/1/99     12:00      ... 1/1/99 12:00
            2   Need 3    000002  1/1/99     12:00      ... 1/1/99 12:00
            3   Need 4    000003  1/1/99     12:00      ... 1/1/99 12:00
            4   Need 5    000004  1/1/99     12:00      ... 1/1/99 12:00

            Returns:
                None.
        """

        # Display preliminary status message
        message = 'Combining shift start dates and times...'
        self.helpers.printer(
            message=message,
            end=''
        )

        # Add 'start' column with data from 'start_date' and 'start_time'
        self._shift_data[START_COLUMN] = self._shift_data[
            [
                START_DATE_COLUMN,
                START_TIME_COLUMN
            ]
        ].agg(
            # Join data with a blank space separator
            ' '.join,
            axis=1
        )

        # Display status message
        message = "done."
        self.helpers.printer(message=message)

        return None

    def _format_shift_start(self) -> None:
        """ Format the 'start' column for Amplify compatibility.

            Args:
                self._shift_data (frame.DataFrame):
                    Pandas Data Frame with shift data in a new 'start'
                    column.

            Modifies:
                self._shift_data (frame.DataFrame):
                    Pandas Data Frame of shift data with
                    Amplify-formatted dates in the 'start' column.

            Example data structure:
                need_name need_id start_date start_time ... start
            0   Need 1    000001  1/1/99     12:00      ... 2099-01-01 12:00
            1   Need 2    000002  1/1/99     12:00      ... 2099-01-01 12:00
            2   Need 3    000002  1/1/99     12:00      ... 2099-01-01 12:00
            3   Need 4    000003  1/1/99     12:00      ... 2099-01-01 12:00
            4   Need 5    000004  1/1/99     12:00      ... 2099-01-01 12:00

            Returns:
                None.
        """

        # Display preliminary status message
        message = 'Formatting shift start values for Amplify compatibility...'
        self.helpers.printer(
            message=message,
            end=''
        )

        # Format the 'start' column for Amplify compatibility
        self._shift_data[START_COLUMN] = self._shift_data[START_COLUMN].apply(
            lambda x: self.helpers.format_date_time(x)
        )

        # Display status message
        message = "done."
        self.helpers.printer(message=message)

        return None

    def _drop_unused_columns(self) -> None:
        """ Drop unused columns from the data frame.

            Args:
                self._shift_data (frame.DataFrame):
                    Pandas Data Frame of shift data with
                    Amplify-formatted dates in the 'start' column.

            Modifies:
                self._shift_data (frame.DataFrame):
                    Pandas Data Frame of shift data without
                    informational columns.

            Example data structure:
                need_id duration slots start
            0   000001  60       20    2099-01-01 12:00
            1   000002  90       20    2099-01-01 12:00
            2   000002  60       20    2099-01-01 12:00
            3   000003  120      20    2099-01-01 12:00
            4   000004  90       20    2099-01-01 12:00

            Returns:
                None.
        """

        # Display preliminary status message
        message = 'Removing unused column data...'
        self.helpers.printer(
            message=message,
            end=''
        )

        # Drop informational columns not required for an API POST request body
        self._shift_data.drop(
            columns=DROP_COLUMNS,
            inplace=True
        )

        # Display status message
        message = "done."
        self.helpers.printer(message=message)

        return None

    def _group_shift_data(self) -> None:
        """ Group rows by 'need_id' and keep only relevant columns.

            Args:
                self._shift_data (frame.DataFrame):
                    Pandas Data Frame of shift data without
                    informational columns.

            Modifies:
                self._grouped_shift_data (DataFrameGroupBy):
                    Pandas Grouped Data Frame of shift data, grouped by
                    each shift's 'need_id'.

            Example data structure:
            {
                '000001': [
                        need_id duration slots start
                    0   000001  60       20    2099-01-01 12:00
                ],
                '000002': [
                        need_id duration slots start
                    1   000002  60       20    2099-01-01 12:00,
                    2   000002  60       20    2099-01-01 12:00,
                ],
                '000003': [
                        need_id duration slots start
                    3   000003  60       20    2099-01-01 12:00
                ],
                '00004': [
                        need_id duration slots start
                    4   000003  60       20    2099-01-01 12:00
                ]
            }

            Returns:
                None.
        """

        # Display preliminary status message
        message = 'Grouping shift data by opportunity...'
        self.helpers.printer(
            message=message,
            end=''
        )

        # Group shifts by 'need_id' and remove other columns from the POST body
        self._grouped_shift_data = self._shift_data.groupby(
            # [KEEP_COLUMNS] excludes the 'need_id' column
            by=[GROUP_BY_COLUMN])[KEEP_COLUMNS]

        # Prepare status message
        if self._grouped_shift_data is not None:
            message = "done."
        else:
            message = '\n\n** Error grouping shift data **\n'

        # Display status message
        self.helpers.printer(message=message)

        return None

    def _create_grouped_series(self) -> None:
        """ Insert a 'shifts' dict under each 'need_id' dict group.

            Modifies the grouped shift data to comply with the required
            API POST body request format.  Automatically converts the
            grouped data frame to a Pandas Series

            Args:
                self._grouped_shift_data (DataFrameGroupBy):
                    Pandas Grouped Data Frame of shift data, grouped by
                    each shift's 'need_id'.

            Modifies:
                self._grouped_series (series.Series):
                    Pandas Series of shifts grouped by 'need_id' with
                    all shifts for each 'need_id' contained within in a
                    'shifts' dict key.

            Example data structure:
            need_id
            000001  {'shifts': [{'start': '2099-01-01 12:00', 'dur...']},
            000002  {'shifts': [{'start': '2099-01-01 12:00', 'dur...'},
                                {'start': '2099-01-01 12:00', 'dur...']},
            000003  {'shifts': [{'start': '2099-01-01 12:00', 'dur...']},
            000004  {'shifts': [{'start': '2099-01-01 12:00', 'dur...']}

            Returns:
                None.
        """

        # Display preliminary status message
        message = 'Organizing shift data for Amplify API compatibility...'
        self.helpers.printer(
            message=message,
            end=''
        )

        # Insert a 'shifts' dict between the 'need_id' and the shift data
        self._grouped_series = self._grouped_shift_data.apply(
            func=lambda x: {
                SHIFTS_DICT_KEY_NAME: x.to_dict(
                    orient='records'
                )
            }
        )

        # Prepare status message
        if self._grouped_series is not None:
            message = "done."

        else:
            message = '\n\n** Error organizing shift data **\n'

        # Display status message
        self.helpers.printer(message=message)

        return None

    def _create_shift_json_data(
            self,
            write_to_file: bool = False
    ) -> None:
        """ Create shift JSON data for the HTTP body.

            Args:
                self._grouped_series (series.Series):
                    Pandas Series of shifts grouped by 'need_id' with
                    all shifts for each 'need_id' contained within in a
                    'shifts' dict key.

                write_to_file (bool):
                    Write the resulting JSON data to a file in addition
                    to storing data in self._json_shift_data['data'].
                    Default value is False.

            Modifies:
                self._json_shift_data['data'] (Dict):
                    Dictionary of shifts grouped by 'need_id' with all
                    shifts for each 'need_id' contained within in a
                    'shifts' dict key.

            Example data structure:
            {'000001':  {'shifts': [{'start': '2099-01-01 12:00', 'dur...']},
            {'000002':  {'shifts': [{'start': '2099-01-01 12:00', 'dur...'},
                                    {'start': '2099-01-01 12:00', 'dur...']},
            {'000003':  {'shifts': [{'start': '2099-01-01 12:00', 'dur...']},
            {'000004':  {'shifts': [{'start': '2099-01-01 12:00', 'dur...']}

            Returns:
                None.
        """

        # Display preliminary status message
        message = 'Converting shift data to JSON...'
        self.helpers.printer(
            message=message,
            end=''
        )

        if write_to_file is True:
            # Save grouped series to JSON data to a file
            self._grouped_series.to_json(
                indent=2,
                mode='w',
                orient='index',
                path_or_buf=self.output_file
            )

        # Store grouped series data in a dictionary
        self._json_shift_data.update(
            {'data': self._grouped_series.to_dict()}
        )

        # Prepare status message
        if self._json_shift_data.get('data') is not None:
            message = "done."
        else:
            message = '\n\n** Error converting shift data to JSON **\n'

        # Display status message
        self.helpers.printer(message=message)

        return None

    def _validate_shift_json_data(self) -> bool:
        """ Validate shift JSON data against JSON Schema.

            Args:
                self._json_shift_data['data'] (Dict):
                    Dict of formatted shift data.

            Modifies:
                self._json_shift_data['valid'] (bool):
                    True if self._json_shift_data['data'] complies with
                    JSON Schema. False if self._json_shift_data['data']
                    does not comply with JSON Schema.

            Returns:
                None.
        """

        # Display preliminary status message
        message = 'Validating shift data compliance with JSON Schema...'
        self.helpers.printer(
            message=message,
            end=''
        )

        # Load JSON Schema file for shift data
        with open(
            file=JSON_SCHEMA_SHIFT_FILE,
            mode='rt',
            encoding='utf-8'
        ) as json_schema_shifts:
            json_schema_shifts = load(json_schema_shifts)

        # Validate shift data against JSON Schema
        try:
            # Attempt to validate shift data against JSON Schema
            validate(
                instance=self._json_shift_data.get('data'),
                schema=json_schema_shifts
            )

            # Set self._json_shift_data['valid'] to True
            self._json_shift_data.update(
                {'valid': True}
            )

        # Indicate invalidate JSON shift data
        except ValidationError as error:
            # Update self._json_shift_data['valid'] and ['error'] to False
            self._json_shift_data.update(
                {
                    'valid': False,
                    'error': error
                }
            )

        # Prepare status message
        if self._json_shift_data.get('valid') is True:
            message = "done."
        else:
            message = '\n\n** Error validating shift data **\n'

        # Display status message
        self.helpers.printer(message=message)

        return None

    def _lookup_opportunity_title(
            self,
            need_id: str | int,
            timeout: int = HTTP_TIMEOUT,
    ) -> str:
        """ Lookup an opportunity title with a need ID.

            Args:
                need_id (str|int):
                    Opportunity ID to look up.

                timeout (int):
                    HTTP timeout.  Default is HTTP_TIMEOUT.

            Returns:
                opp_title (str):
                    Opportunity title.
        """

        # Set HTTP request variables
        method = 'GET'
        headers = BASE_AMPLIFY_HEADERS

        # Construct URL and JSON payload
        url = f'{BASE_AMPLIFY_URL}/needs/{need_id}'

        # Construct API request data
        api_request_data = {
            'method': method,
            'url': url,
            'headers': headers,
            'json': None,
            'timeout': timeout
        }

        # Send API request
        response = self.helpers.send_api_request(
            api_request_data=api_request_data
        )

        # Parse opportunity title from response
        opp_title = response.json()['data'].get("need_title", "Unknown")

        return opp_title

    def create_new_shifts(
            self,
            json: Any = None,
            timeout: int = HTTP_TIMEOUT
    ) -> None:
        """ Upload shift data to create new Amplify shifts.

            Args:
                json (Any):
                    JSON body of shift data.  Default value is None in
                    order to allow sending a custom JSON body of shift
                    data, although the method will use the data in the
                    self._shift_data variable to construct a JSON body
                    by default.

                timeout (int):
                    HTTP timeout.  Default is HTTP_TIMEOUT.

            Returns:
                None.
        """

        # Only send the request if self._json_shift_data['valid'] is True
        if self._json_shift_data.get('valid') is True:

            # Set a default value for 'output_heading'
            output_heading = None

            # Set HTTP request variables
            method = 'POST'
            headers = BASE_AMPLIFY_HEADERS

            # Create and send request
            for need_id, shifts in self._json_shift_data.get('data').items():

                # Construct URL and JSON payload
                url = f'{BASE_AMPLIFY_URL}/needs/{need_id}/shifts'
                json = shifts

                # Construct API request data
                api_request_data = {
                    'method': method,
                    'url': url,
                    'headers': headers,
                    'json': json,
                    'timeout': timeout
                }

                # Determine the status of check_mode
                if self.check_mode is False:
                    # Send API request
                    self.helpers.send_api_request(
                        api_request_data=api_request_data
                    )

                else:
                    # Set check_mode output message
                    output_heading = (
                        '** HTTP API Check Mode Run **\n'
                    )

                # Lookup opportunity title
                opp_title = self._lookup_opportunity_title(
                    need_id=need_id
                )

                # Create output message
                output_message = (
                    f'URL: {url}\n'
                    f'Opportunity Title: {opp_title}\n'
                    f'Shift Count: {len(json.get("shifts"))}\n'
                    f'Payload:\n{dumps(json, indent=2)}'
                )

                # Add a heading if it exists
                if output_heading is not None:
                    output_message = f'{output_heading}{output_message}'

                # Display output message
                self.helpers.printer(
                    message=output_message
                )

        # Display a message if self._json_shift_data['valid'] is not True
        else:
            # Create output message
            output_message = (
                '** Unable to create shifts while shift data is invalid **\n'
            )
            if self._json_shift_data.get('error') is not None:
                # Update output message
                output_message += f'\n{self._json_shift_data.get("error")}\n'

                # Display output message
                self.helpers.printer(
                    message=output_message
                )

        return None
