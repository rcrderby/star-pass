#!/usr/bin/env python3
""" Star Pass Classes and Methods """

# Imports - Python Standard Library
from json import dumps, load
from os import getenv
from os import path
from typing import Any, Dict

# Imports - Third-Party
import pandas as pd
from dotenv import load_dotenv
from jsonschema import validate, ValidationError
from pandas.core import frame, series
from pandas.core.groupby.generic import DataFrameGroupBy

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
GC_TOKEN = getenv(
    key='GC_TOKEN'
)

# HTTP request configuration
BASE_HEADERS = _defaults.BASE_HEADERS
BASE_HEADERS.update(
    {'Authorization': f'Bearer {GC_TOKEN}'}
)
BASE_URL = getenv(
    key='BASE_URL',
    default=_defaults.BASE_URL
)
HTTP_TIMEOUT = int(
    getenv(
        key='HTTP_TIMEOUT',
        default=_defaults.HTTP_TIMEOUT
    )
)

# Data file name and location
BASE_FILE_NAME = getenv(
    key='BASE_FILE_NAME',
    default=_defaults.BASE_FILE_NAME
)
BASE_FILE_PATH = getenv(
    key='BASE_FILE_PATH',
    default=_defaults.BASE_FILE_PATH
)

# Input data file
INPUT_FILE_DIR = getenv(
    key='INPUT_FILE_DIR',
    default=_defaults.INPUT_FILE_DIR
)
INPUT_FILE_EXTENSION = getenv(
    key='INPUT_FILE_EXTENSION',
    default=_defaults.INPUT_FILE_EXTENSION
)
INPUT_FILE_PATH = path.join(
    BASE_FILE_PATH,
    INPUT_FILE_DIR,
    BASE_FILE_NAME
)
INPUT_FILE = f'{INPUT_FILE_PATH}{INPUT_FILE_EXTENSION}'

# Data file management
DROP_COLUMNS = getenv(
    key='DROP_COLUMNS',
    default=_defaults.DROP_COLUMNS
).split(sep=', ')
GROUP_BY_COLUMN = getenv(
    key='GROUP_BY_COLUMN',
    default=_defaults.GROUP_BY_COLUMN
)
SHIFTS_DICT_KEY_NAME = getenv(
    key='SHIFTS_DICT_KEY_NAME',
    default=_defaults.SHIFTS_DICT_KEY_NAME
)
START_COLUMN = getenv(
    key='START_COLUMN',
    default=_defaults.START_COLUMN
)
START_DATE_COLUMN = getenv(
    key='START_DATE_COLUMN',
    default=_defaults.START_DATE_COLUMN
)
START_TIME_COLUMN = getenv(
    key='START_TIME_COLUMN',
    default=_defaults.START_TIME_COLUMN
)
KEEP_COLUMNS = getenv(
    key='KEEP_COLUMNS',
    default=_defaults.KEEP_COLUMNS
).split(sep=', ')

# JSON Schema
JSON_SCHEMA_DIR = getenv(
    key='JSON_SCHEMA_DIR',
    default=_defaults.JSON_SCHEMA_DIR
)
JSON_SCHEMA_SHIFT_FILE = getenv(
    key='JSON_SCHEMA_SHIFT_FILE',
    default=_defaults.JSON_SCHEMA_SHIFT_FILE
)
JSON_SCHEMA_SHIFT_FILE = path.join(
    JSON_SCHEMA_DIR,
    getenv(
        key='JSON_SCHEMA_SHIFT_FILE',
        default=_defaults.JSON_SCHEMA_SHIFT_FILE
    )
)

# Output data file
OUTPUT_FILE_DIR = getenv(
    key='OUTPUT_FILE_DIR',
    default=_defaults.OUTPUT_FILE_DIR
)
OUTPUT_FILE_EXTENSION = getenv(
    key='OUTPUT_FILE_EXTENSION',
    default=_defaults.OUTPUT_FILE_EXTENSION
)
OUTPUT_FILE_PATH = path.join(
    BASE_FILE_PATH,
    OUTPUT_FILE_DIR,
    BASE_FILE_NAME
)
OUTPUT_FILE = f'{OUTPUT_FILE_PATH}{OUTPUT_FILE_EXTENSION}'


# Class definitions
class CreateShifts:
    """ CreateShifts base class object. """

    def __init__(
            self,
            auto_prep_data: bool = True,
            check_mode: bool = True,
            input_file: str = INPUT_FILE,
            input_file_override: str = None
    ) -> None:
        """ CreateShifts initialization method.

            Args:
                auto_prep_data (bool):
                    Automatically run non-public methods that import,
                    validate, and prepare CSV data for upload via the
                    Amplify API. When auto_prep_data is True, creating
                    an instance of the CreateShifts Class will
                    automatically attempt to prepare data.  When
                    auto_prep_data is False, you may manually run the
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

                    Default value is True.

                check_mode (bool):
                    Prepare HTTP API requests without sending the
                    requests.  Default value is True.

                input_file (str):
                    Absolute path to non-default input data file. For
                    example:

                        shifts = CreateShifts(
                            input_file='data/csv/data_file.csv'
                        )

                    Default value is INPUT_FILE

            Returns:
                None.
        """

        # Initialize helper methods
        self.helpers = Helpers()

        # Set Class initialization values
        self.auto_prep_data = auto_prep_data
        # Determine if the value of 'check_mode' is a boolean
        if isinstance(check_mode, bool):
            self.check_mode = check_mode
        else:
            self.check_mode = self.helpers.convert_to_bool(check_mode)
        self.input_file = input_file
        # Override input file if input_file_override argument is not None
        if input_file_override is not None:
            self.input_file = input_file_override

        # Placeholder variables for data transformation methods
        self._shift_data: frame.DataFrame = None
        self._grouped_shift_data: DataFrameGroupBy = None
        self._grouped_series: series.Series = None
        self._shift_data: Dict = None
        self._shift_data_valid: bool = None

        # Call non-public methods to initialize workflow
        if self.auto_prep_data is True:
            self._read_shift_csv_data()
            self._remove_duplicate_shifts()
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

            Modifies:
                self._shift_data (frame.DataFrame):
                    Pandas Data Frame of raw shift data.

            Returns:
                None.
        """
        # Print preliminary status message
        message = f'\nReading shift data from "{self.input_file}"...'
        self.helpers.printer(
            message=message,
            end=''
        )

        # Read CSV file
        shift_data = pd.read_csv(
            filepath_or_buffer=self.input_file,
            dtype='string'
        )

        # Update self._shift_data
        self._shift_data = shift_data

        # Print final status message
        if self._shift_data is not None:
            message = "done."
            self.helpers.printer(message=message)

        else:
            message = f'\n\n** Error reading data in "{self.input_file}" **\n'

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

            Returns:
                None.
        """
        # Print preliminary status message
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

        # Print final status message
        message = "done."
        self.helpers.printer(message=message)

        return None

    def _format_shift_start(self) -> None:
        """ Merge the 'start_date' and 'start_time' columns to a
            'start_date' column.

            Args:
                self._shift_data (frame.DataFrame):
                    Pandas Data Frame of shift data with duplicates
                    removed.

            Modifies:
                self._shift_data (frame.DataFrame):
                    Pandas Data Frame with shift data in a new 'start' column.

            Returns:
                None.
        """
        # Print preliminary status message
        message = 'Merging shift dates and times to combined values...'
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

        # Print final status message
        message = "done."
        self.helpers.printer(message=message)

        return None

    def _format_shift_dates(self) -> None:
        """ Format START_COLUMN dates/times for Amplify compatibility. """

        # Print preliminary status message
        message = 'Formatting shift start values for Amplify compatibility...'
        self.helpers.printer(
            message=message,
            end=''
        )

        # Print final status message
        message = "done."
        self.helpers.printer(message=message)

        return None

    def _drop_unused_columns(self) -> None:
        """ Drop unused columns from the data frame.

            Args:
                self._shift_data (frame.DataFrame):
                    Pandas Data Frame with shift data in a new 'start' column.

            Modifies:
                self._shift_data (frame.DataFrame):
                    Pandas Data Frame of shift data without informational
                    columns.

            Returns:
                None.
        """
        # Print preliminary status message
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

        # Print final status message
        message = "done."
        self.helpers.printer(message=message)

        return None

    def _group_shift_data(self) -> None:
        """ Group rows by 'need_id' and keep only relevant columns.

            Args:
                self._shift_data (frame.DataFrame):
                    Pandas Data Frame of shift data without extra columns.

            Modifies:
                self._grouped_shift_data (DataFrameGroupBy):
                    Pandas Grouped Data Frame of shift data, grouped by each
                    shift's 'need_id'.

            Returns:
                None.
        """
        # Print preliminary status message
        message = 'Grouping shift data by opportunity...'
        self.helpers.printer(
            message=message,
            end=''
        )

        # Group shifts by 'need_id' and remove other columns from the POST body
        self._grouped_shift_data = self._shift_data.groupby(
            # [KEEP_COLUMNS] excludes the 'need_id' column
            by=[GROUP_BY_COLUMN])[KEEP_COLUMNS]

        # Print final status message
        if self._grouped_shift_data is not None:
            message = "done."
            self.helpers.printer(message=message)

        else:
            message = '\n\n** Error grouping shift data **\n'

        return None

    def _create_grouped_series(self) -> None:
        """ Insert a 'shifts' dict under each 'need_id' dict to comply with the
            required API POST body request format.  Automatically converts the
            grouped data frame to a Pandas Series

            Args:
                self._grouped_shift_data (DataFrameGroupBy):
                    Pandas Grouped Data Frame of shift data, grouped by each
                    shift's 'need_id'.

            Modifies:
                self._grouped_series (series.Series):
                    Pandas Series of shifts grouped by 'need_id' with all
                    shifts contained in a 'shifts' dict key.

            Returns:
                None.
        """
        # Print preliminary status message
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

        # Print final status message
        if self._grouped_series is not None:
            message = "done."
            self.helpers.printer(message=message)

        else:
            message = '\n\n** Error organizing shift data **\n'

        return None

    def _create_shift_json_data(
            self,
            write_to_file: bool = False
    ) -> None:
        """ Create shift JSON data for the HTTP body.

            Args:
                self._grouped_series (series.Series):
                    Pandas Series of shifts grouped by 'need_id' with all
                    shifts contained in a 'shifts' dict key.

                write_to_file (bool):
                    Write the resulting JSON data to a file in addition to
                    storing the data in self._shift_data. Default value
                    is False.

            Modifies:
                self._shift_data (Dict):
                    Dictionary of shifts grouped by 'need_id' with all
                    shifts for each 'need_id' contained in a 'shifts'
                    dict key.

            Returns:
                None.
        """
        # Print preliminary status message
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
                path_or_buf=OUTPUT_FILE
            )

        # Store grouped series data in a dictionary
        self._shift_data = self._grouped_series.to_dict()

        # Print final status message
        if self._shift_data is not None:
            message = "done."
            self.helpers.printer(message=message)

        else:
            message = '\n\n** Error converting shift data to JSON **\n'

        return None

    def _validate_shift_json_data(self) -> bool:
        """ Validate shift JSON data against JSON Schema.

            Args:
                self._shift_data (Dict):
                    Dict of formatted shift data.

            Modifies:
                self._shift_data_valid (bool):
                    True if self._shift_data complies with JSON Schema.
                    False if self._shift_data does not comply with JSON Schema.

            Returns:
                None.
        """
        # Print preliminary status message
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
                instance=self._shift_data,
                schema=json_schema_shifts
            )

            # Set self._shift_data_valid to True
            self._shift_data_valid = True

        # Indicate invalidate JSON shift data
        except ValidationError:
            # Set self._shift_data_valid to False
            self._shift_data_valid = False

        # Print final status message
        if self._shift_data_valid is True:
            message = "done."
            self.helpers.printer(message=message)

        else:
            message = '\n\n** Error validating shift data **\n'

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
        headers = BASE_HEADERS

        # Construct URL and JSON payload
        url = f'{BASE_URL}/needs/{need_id}'

        # Construct API request data
        api_request_data = {
            "method": method,
            "url": url,
            "headers": headers,
            "json": None,
            "timeout": timeout
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

        # Set HTTP request variables
        method = 'POST'
        headers = BASE_HEADERS

        # Create and send request
        for need_id, shifts in self._shift_data.items():

            # Construct URL and JSON payload
            url = f'{BASE_URL}/needs/{need_id}/shifts'
            json = shifts

            # Construct API request data
            api_request_data = {
                "method": method,
                "url": url,
                "headers": headers,
                "json": json,
                "timeout": timeout
            }

            # Determine the status of check_mode
            if self.check_mode is False:
                # Send API request
                response = self.helpers.send_api_request(
                    api_request_data=api_request_data
                )

                # Set HTTP response output message
                output_heading = (
                    '** HTTP API Response **\n'
                    f'Response: HTTP {response.status_code} {response.reason}'
                )

            else:
                # Set check_mode output message
                output_heading = (
                    '** HTTP API Check Mode Run **'
                )

            # Lookup opportunity title
            opp_title = self._lookup_opportunity_title(
                need_id=need_id
            )

            # Create output message
            output_message = (
                f'\n{output_heading}\n'
                f'URL: {url}\n'
                f'Opportunity Title: {opp_title}\n'
                f'Shift Count: {len(json.get("shifts"))}\n'
                f'Payload:\n{dumps(json, indent=2)}'
            )

            # Display output message
            self.helpers.printer(
                message=output_message
            )

        return None
