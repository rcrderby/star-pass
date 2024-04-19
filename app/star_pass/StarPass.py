#!/usr/bin/env python3
""" Star Pass Classes and Methods """

# Imports - Python Standard Library
from os import getenv
from os import path

# Imports - Third-Party
import pandas as pd
from dotenv import load_dotenv
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
    'Authorization': f'Bearer {GC_TOKEN}',
    'Accept': 'application/json'
}
BASE_FILE_PATH = path.join(
    getenv('BASE_FILE_RELATIVE_PATH'),
    getenv('BASE_FILE_NAME')
)
BASE_URL = getenv(key='BASE_URL')
GROUP_BY_COLUMN = getenv('GROUP_BY_COLUMN')
INPUT_FILE_EXTENSION = getenv('INPUT_FILE_EXTENSION')
INPUT_FILE = f'{BASE_FILE_PATH}{INPUT_FILE_EXTENSION}'
DROP_COLUMNS = getenv('DROP_COLUMNS').split(
    sep=', '
)
KEEP_COLUMNS = getenv('KEEP_COLUMNS').split(
    sep=', '
)
OUTPUT_FILE_EXTENSION = getenv('OUTPUT_FILE_EXTENSION')
OUTPUT_FILE = f'{BASE_FILE_PATH}{OUTPUT_FILE_EXTENSION}'
SHIFTS_DICT_KEY_NAME = getenv('SHIFTS_DICT_KEY_NAME')
START_COLUMN = getenv('START_COLUMN')
START_DATE_COLUMN = getenv('START_DATE_COLUMN')
START_TIME_COLUMN = getenv('START_TIME_COLUMN')


# Class definitions
class AmplifyShifts():
    """ AmplifyShifts base class object. """

    def __init__(self) -> None:
        """ AmplifyShifts initialization method.

            Args:
                None.

            Returns:
                None.
        """
        # Placeholder variables for data transformation methods
        self._shift_data: frame.DataFrame = None
        self._grouped_shift_data = None
        self._grouped_series = None

    def _send_api_request(self) -> None:
        """ Create base API request.

            Args:
                None.

            Returns:
                None.
        """

        # Construct URL
        # url = f'{BASE_URL}{endpoint}'

        # Send API request
        response_data = request(
            # Type
            # url=url,
            headers=BASE_HEADERS,
            timeout=3
        )

        # Create response data object
        response = response_data.json()['data']

        return response

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
            by=[GROUP_BY_COLUMN]
        # Excludes the 'need_id' from what will be the API request POST body
        )[KEEP_COLUMNS]

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
                    Pandas Series of shifts grouped by 'need_id' with all shifts
                    contained in a 'shifts' dict key.

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

    def _create_shift_json_data(self) -> None:
        """ Create shift JSON data for the HTTP body.

            Args:
                self._grouped_series (series.Series):
                    Pandas Series of shifts grouped by 'need_id' with all shifts
                    contained in a 'shifts' dict key.

            Returns:
                None.
        """
        # Convert grouped series to JSON data for HTTP API requests
        self._grouped_series.to_json(
            indent=2,
            mode='w',
            orient='index',
            path_or_buf=OUTPUT_FILE
        )

        return None

    def create_new_shifts_(self) -> None:
        """ Upload shift data to create new shifts.

            Args:
                None.

            Returns:
                None.
        """
        pass
