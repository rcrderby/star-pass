#!/usr/local/bin/python3
""" Amplify shift management classes and methods. """

# Imports - Python Standard Library
from json import load
from pathlib import Path
from typing import Any, Dict

# Imports - Third-Party
import pandas as pd
# Aliased so the name is free for the core's own ValidationError,
# which is what this module raises; jsonschema's is only caught.
from jsonschema import validate, ValidationError as SchemaValidationError
from pandas.core import frame, series
from pandas.core.groupby.generic import DataFrameGroupBy

# Imports - Local
from . import _defaults
from ._exceptions import ValidationError
from ._helpers import amplify_headers, Helpers, load_env_file
from ._reporting import Reporter, ShiftBatch
from ._logging import get_logger
from ._opportunities import read_title
from ._validation import validate_shift_columns, validate_shift_need_ids

# Load environment variables
load_env_file()

# Constants
# HTTP request configuration
BASE_AMPLIFY_HEADERS = amplify_headers()
BASE_AMPLIFY_URL = _defaults.BASE_AMPLIFY_URL
HTTP_TIMEOUT = _defaults.HTTP_TIMEOUT

# Input and output data file paths
FILE_ENCODING = _defaults.FILE_ENCODING
INPUT_DIR_PATH = _defaults.INPUT_DIR_PATH
INPUT_FILE_EXTENSION = _defaults.INPUT_FILE_EXTENSION
OUTPUT_DIR_PATH = _defaults.OUTPUT_DIR_PATH
OUTPUT_FILE_EXTENSION = _defaults.OUTPUT_FILE_EXTENSION

# JSON Schema file
JSON_SCHEMA_SHIFT_FILE = _defaults.JSON_SCHEMA_SHIFT_FILE

# CSV data file management
DROP_COLUMNS = _defaults.DROP_COLUMNS.split(sep=', ')
GROUP_BY_COLUMN = _defaults.GROUP_BY_COLUMN
NEED_NAME_COLUMN = _defaults.NEED_NAME_COLUMN
SHIFTS_DICT_KEY_NAME = _defaults.SHIFTS_DICT_KEY_NAME
START_COLUMN = _defaults.START_COLUMN
START_DATE_COLUMN = _defaults.START_DATE_COLUMN
START_TIME_COLUMN = _defaults.START_TIME_COLUMN
KEEP_COLUMNS = _defaults.KEEP_COLUMNS.split(sep=', ')

# Default output format verbosity

# Module logger
logger = get_logger(__name__)


# Class definitions
class CreateShifts:  # pylint: disable=too-many-instance-attributes
    """ CreateShifts base class object. """

    def __init__(
            self,
            input_file: str,
            auto_prep_data: bool = True,
            check_mode: bool = True,
            reporter: Reporter | None = None,
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
                    3. Rejects any shift row without a need ID.
                    4. Formats the shift start date and time to comply
                       with the Amplify API shift format.
                    5. Removes any CSV file columns not used by the
                       Amplify API.
                    6. Groups shift data by need ID.
                    7. Formats data to comply with the structure
                       requirements of the Amplify API.
                    8. Creates a JSON-formatted object of shift data
                       to send to the Amplify API.
                    9. Validates the JSON-formatted object using a JSON
                       Schema object.

                    When 'auto_prep_data' is True, creating
                    an instance of the 'CreateShifts' class will
                    automatically attempt to prepare data.  When
                    'auto_prep_data' is False, you may manually run the
                    non-public functions to prepare the data.

                    Non-public functions that prepare data include:

                        _read_shift_csv_data()
                        _remove_duplicate_shifts()
                        _validate_shift_rows()
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

                reporter (Reporter, optional):
                    Receives progress and result events.  Defaults to
                    None, which discards them: how the run is displayed
                    is the caller's concern, and a caller that only
                    wants the outcome passes nothing.

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

        # Report progress nowhere unless the caller supplies a
        # destination
        self.reporter = reporter if reporter is not None else Reporter()

        # Set the base file name.
        # Use removesuffix (not rstrip, which strips a *character set*
        # and would corrupt names ending in '.', 'c', 's', or 'v').
        self.base_file_name = input_file.removesuffix(INPUT_FILE_EXTENSION)

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
            self._validate_shift_need_ids()
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
        self.reporter.step_started(
            label=f'Reading shift data from "{self.input_file}"'
        )

        # Read CSV file.  A missing or unreadable file is an operator
        # error (a mistyped -i value), not a bug, so report the path
        # rather than raising a traceback from deep inside pandas.
        try:
            shift_data = pd.read_csv(
                filepath_or_buffer=f'{self.input_file}',
                dtype='string'
            )
        except FileNotFoundError as error:
            self.reporter.step_failed()
            message = (
                f'No shift data file at "{self.input_file}".  Pass the '
                'file name of a CSV file in the input directory with '
                '-i/--input-file.'
            )
            logger.error(message)
            raise ValidationError(message) from error
        except pd.errors.EmptyDataError as error:
            self.reporter.step_failed()
            message = (
                f'The shift data file "{self.input_file}" is empty.'
            )
            logger.error(message)
            raise ValidationError(message) from error

        # Update self._shift_data
        self._shift_data = shift_data

        # Display status message
        self.reporter.step_finished()

        # Confirm the file has the columns the pipeline transforms
        validate_shift_columns(
            shift_data=self._shift_data,
            input_file=self.input_file
        )

        return None

    def _remove_duplicate_shifts(self) -> None:
        """ Remove duplicate shift entries.

            Args:
                self._shift_data (frame.DataFrame):
                    Pandas Data Frame of raw shift data.

            Modifies:
                self._shift_data (frame.DataFrame):
                    Pandas Data Frame of shift data with fully-duplicate
                    rows removed (index 2 dropped in the example below).

            Example data structure:
                need_name need_id start_date start_time duration slots
            0   Alpha     000001  1/1/99     12:00      60       20
            1   Bravo     000002  1/1/99     12:00      90       20
            3   Charlie   000003  1/1/99     12:00      120      20

            Returns:
                None.
        """

        # Display preliminary status message
        self.reporter.step_started(label='Removing duplicate shifts')

        # Drop duplicate rows in self._shift_data
        self._shift_data.drop_duplicates(
            inplace=True,
            keep='first'
        )

        # Display status message
        self.reporter.step_finished()

        return None

    def _validate_shift_need_ids(self) -> None:
        """ Reject shift rows that have no need ID.

            Args:
                self._shift_data (frame.DataFrame):
                    Pandas Data Frame of shift data with duplicate rows
                    removed.

            Raises:
                ValidationError:
                    Through 'validate_shift_need_ids', when any row has
                    a missing, empty, or whitespace-only need ID.

            Returns:
                None.
        """

        # Display preliminary status message
        self.reporter.step_started(label='Validating shift need IDs')

        # Close the step first: the check writes its report to the log,
        # which goes to stderr, when it finds a blank need ID.
        self.reporter.step_failed()
        validate_shift_need_ids(
            shift_data=self._shift_data,
            input_file=self.input_file
        )

        # Display status message
        self.reporter.step_finished()

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
        self.reporter.step_started(
            label='Combining shift start dates and times'
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
        self.reporter.step_finished()

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
        self.reporter.step_started(
            label='Formatting shift start values for Amplify '
                  'compatibility'
        )

        # Format the 'start' column for Amplify compatibility.  A value
        # the date parser cannot read is an error in a hand-edited file,
        # so name it instead of raising a traceback.
        try:
            self._shift_data[START_COLUMN] = self._shift_data[
                START_COLUMN
            ].apply(
                lambda x: self.helpers.format_date_time_amplify(x)
            )
        except ValueError as error:
            self.reporter.step_failed()
            message = (
                f'{error}  Check the {START_DATE_COLUMN} and '
                f'{START_TIME_COLUMN} columns in '
                f'"{self.input_file}".'
            )
            logger.error(message)
            raise ValidationError(message) from error

        # Display status message
        self.reporter.step_finished()

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
        self.reporter.step_started(label='Removing unused column data')

        # Drop informational columns not required for an API POST request body
        self._shift_data.drop(
            columns=DROP_COLUMNS,
            inplace=True
        )

        # Display status message
        self.reporter.step_finished()

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
        self.reporter.step_started(label='Grouping shift data by opportunity')

        # Group shifts by 'need_id' and remove other columns from the POST body
        self._grouped_shift_data = self._shift_data.groupby(
            # [KEEP_COLUMNS] excludes the 'need_id' column
            by=[GROUP_BY_COLUMN])[KEEP_COLUMNS]

        # Display status message ('groupby' raises rather than returning
        # None, so a failure never reaches this line)
        self.reporter.step_finished()

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
        self.reporter.step_started(
            label='Organizing shift data for Amplify API compatibility'
        )

        # Insert a 'shifts' dict between the 'need_id' and the shift data
        self._grouped_series = self._grouped_shift_data.apply(
            func=lambda x: {
                SHIFTS_DICT_KEY_NAME: x.to_dict(
                    orient='records'
                )
            }
        )

        # Display status message ('apply' raises rather than returning
        # None, so a failure never reaches this line)
        self.reporter.step_finished()

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
        self.reporter.step_started(label='Converting shift data to JSON')

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

        # Display status message ('to_dict' raises rather than returning
        # None, so a failure never reaches this line)
        self.reporter.step_finished()

        return None

    def _validate_shift_json_data(self) -> None:
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
        self.reporter.step_started(
            label='Validating shift data compliance with JSON Schema'
        )

        # Load JSON Schema file for shift data
        with open(
            file=JSON_SCHEMA_SHIFT_FILE,
            mode='rt',
            encoding=FILE_ENCODING
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
        except SchemaValidationError as error:
            # Update self._json_shift_data['valid'] and ['error'] to False
            self._json_shift_data.update(
                {
                    'valid': False,
                    'error': error
                }
            )

        # Report the outcome
        if self._json_shift_data.get('valid') is True:
            self.reporter.step_finished()
        else:
            self.reporter.schema_validation_failed()

        return None

    def _lookup_opportunity_title(
            self,
            need_id: str | int,
            timeout: int = HTTP_TIMEOUT,
    ) -> str:
        """ Lookup an opportunity title with a need ID.

            Args:
                need_id (str | int):
                    Opportunity ID to look up.

                timeout (int):
                    HTTP timeout.  Default is HTTP_TIMEOUT.

            Returns:
                opp_title (str):
                    Opportunity title.
        """

        return read_title(
            helpers=self.helpers,
            need_id=need_id,
            timeout=timeout
        )

    def create_new_shifts(
            self,
            timeout: int = HTTP_TIMEOUT
    ) -> None:
        """ Upload shift data to create new Amplify shifts.

            The body of each request is built from the prepared data in
            'self._json_shift_data'.

            Args:
                timeout (int):
                    HTTP timeout.  Default is HTTP_TIMEOUT.

            Returns:
                None.
        """

        # Only send the request if self._json_shift_data['valid'] is True
        if self._json_shift_data.get('valid') is True:

            self.reporter.sending_started()

            # A dry run reports what it would have created
            if self.check_mode is True:
                self.reporter.check_mode()

            # Set HTTP request variables
            method = 'POST'
            headers = BASE_AMPLIFY_HEADERS

            # Create and send request
            for index, (need_id, shifts) in enumerate(
                iterable=self._json_shift_data.get('data').items(),
                start=1
            ):

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

                # Report the batch; the renderer decides how much of
                # it to show
                self.reporter.shifts_sent(
                    batch=ShiftBatch(
                        index=index,
                        need_id=need_id,
                        title=self._lookup_opportunity_title(
                            need_id=need_id
                        ),
                        url=url,
                        shifts=json.get('shifts'),
                        payload=json
                    )
                )

        # Display a message if self._json_shift_data['valid'] is not True
        else:
            # Create output message.  The validation error is appended
            # when there is one, but the message is reported either way:
            # nesting the report inside the error check meant that
            # unvalidated data (['valid'] is None) returned in silence,
            # as though the shifts had been created.
            output_message = (
                '** Unable to create shifts while shift data is invalid **'
            )
            validation_error = self._json_shift_data.get('error')
            if validation_error is not None:
                output_message += f'\n\n{validation_error}'

            # Report to the log and to the caller's renderer
            logger.error(output_message)
            self.reporter.shift_data_invalid(
                detail=(
                    None if validation_error is None
                    else str(validation_error)
                )
            )

        return None
