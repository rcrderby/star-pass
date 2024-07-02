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
from requests import request

# Load environment variables
load_dotenv(
    dotenv_path='./.env',
    encoding='utf-8'
)

# Constants
GC_TOKEN = getenv(key='GC_TOKEN')
BASE_HEADERS = {
    'Accept': 'application/json',
    'Authorization': f'Bearer {GC_TOKEN}',
    'Content-Type': 'application/json'
}
BASE_URL = getenv(key='BASE_URL')
DROP_COLUMNS = getenv('DROP_COLUMNS').split(
    sep=', '
)
GROUP_BY_COLUMN = getenv('GROUP_BY_COLUMN')
HTTP_TIMEOUT = 3
INPUT_FILE_EXTENSION = getenv('INPUT_FILE_EXTENSION')
INPUT_FILE_PATH = path.join(
    getenv('BASE_FILE_PATH'),
    getenv('INPUT_FILE_DIR'),
    getenv('BASE_FILE_NAME')
)
INPUT_FILE = f'{INPUT_FILE_PATH}{INPUT_FILE_EXTENSION}'
JSON_SCHEMA_DIR = getenv('JSON_SCHEMA_DIR')
JSON_SCHEMA_SHIFT_FILE = path.join(
    JSON_SCHEMA_DIR,
    getenv('JSON_SCHEMA_SHIFT_FILE')
)
KEEP_COLUMNS = getenv('KEEP_COLUMNS').split(
    sep=', '
)
OUTPUT_FILE_EXTENSION = getenv('OUTPUT_FILE_EXTENSION')
OUTPUT_FILE_PATH = path.join(
    getenv('BASE_FILE_PATH'),
    getenv('OUTPUT_FILE_DIR'),
    getenv('BASE_FILE_NAME')
)
OUTPUT_FILE = f'{OUTPUT_FILE_PATH}{OUTPUT_FILE_EXTENSION}'
SHIFTS_DICT_KEY_NAME = getenv('SHIFTS_DICT_KEY_NAME')
START_COLUMN = getenv('START_COLUMN')
START_DATE_COLUMN = getenv('START_DATE_COLUMN')
START_TIME_COLUMN = getenv('START_TIME_COLUMN')


# Class definitions
class AmplifyShifts():
    """ AmplifyShifts base class object. """

    def __init__(
            self,
            dry_run: bool = False
    ) -> None:
        """ AmplifyShifts initialization method.

            Args:
                dry_run (bool):
                    Prepare HTTP API requests without sending the
                    requests.  Default value is False.

            Returns:
                None.
        """

        # Set the value of self._dry_run
        self._dry_run = dry_run

        # Placeholder variables for data transformation methods
        self._shift_data: frame.DataFrame = None
        self._grouped_shift_data: DataFrameGroupBy = None
        self._grouped_series: series.Series = None
        self._shift_data: Dict = None
        self._shift_data_valid: bool = None

        # Call non-public functions to initialize workflow
        self._read_shift_csv_data()
        self._remove_duplicate_shifts()
        self._format_shift_start()
        self._drop_unused_columns()
        self._group_shift_data()
        self._create_grouped_series()
        self._create_shift_json_data()
        self._validate_shift_json_data()

    def _send_api_request(
            self,
            method: str,
            url: str,
            headers: Dict[str, str],
            json: Any,
            timeout: int
    ) -> None:
        """ Create base API request.

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
                None.
        """

        # Check for a dry run
        if self._dry_run is False:
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

            # Set HTTP response output message
            output_msg = (
                '** HTTP API Response **\n'
                f'Response: HTTP {response.status_code} {response.reason}'
            )

        else:
            # Set dry run output message
            output_msg = (
                '** HTTP API Dry Run **'
            )

        # Display output message
        print(
            f'\n{output_msg}\n'
            f'URL: {url}\n'
            f'Shift Count: {len(json.get("shifts"))}\n'
            f'Payload:\n{dumps(json, indent=2)}'
        )

        return None

    def _read_shift_csv_data(
        self,
        input_file: str = INPUT_FILE
    ) -> None:
        """ Read shifts data from a CSV file and convert fields to
            strings for Amplify API compatibility.

            Args:
                input_file (str):
                    CSV file or path to CSV file.

            Modifies:
                self._shift_data (frame.DataFrame):
                    Pandas Data Frame of raw shift data.

            Returns:
                None.
        """
        # Read CSV file
        shift_data = pd.read_csv(
            filepath_or_buffer=input_file,
            dtype='string'
        )

        # Update self._shift_data
        self._shift_data = shift_data

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
        # Drop duplicate rows in self._shift_data
        self._shift_data.drop_duplicates(
            inplace=True,
            keep='first'
        )

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
        # Drop informational columns not required for an API POST request body
        self._shift_data.drop(
            columns=DROP_COLUMNS,
            inplace=True
        )

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
        # Group shifts by 'need_id' and remove other columns from the POST body
        self._grouped_shift_data = self._shift_data.groupby(
            # [KEEP_COLUMNS] excludes the 'need_id' column
            by=[GROUP_BY_COLUMN])[KEEP_COLUMNS]

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
        # Insert a 'shifts' dict between the 'need_id' and the shift data
        self._grouped_series = self._grouped_shift_data.apply(
            func=lambda x: {
                SHIFTS_DICT_KEY_NAME: x.to_dict(
                    orient='records'
                )
            }
        )

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

        return None

    def create_new_shifts(
            self,
            json: Any = None,
            timeout: int = HTTP_TIMEOUT,
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

            # Send request
            self._send_api_request(
                method=method,
                url=url,
                headers=headers,
                json=json,
                timeout=timeout
            )

        return None
