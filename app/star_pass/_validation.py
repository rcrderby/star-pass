#!/usr/bin/env python3
""" Shift input file validation.

    Checks a shift CSV file before the transformation pipeline runs, so
    that a problem in the file is reported against the file -- naming the
    column or the event and the line it came from -- rather than
    surfacing later as a KeyError from a transformation, or as data that
    silently never reaches Amplify.

    Each check logs the cause and exits non-zero, matching the failure
    style of the rest of the application.
"""

# Imports - Python Standard Library
import sys

# Imports - Third-Party
from pandas.core import frame

# Imports - Local
from . import _defaults
from ._logging import get_logger

# Constants
GROUP_BY_COLUMN = _defaults.GROUP_BY_COLUMN
NEED_NAME_COLUMN = _defaults.NEED_NAME_COLUMN
SHIFTS_INFO_FILE = _defaults.SHIFTS_INFO_FILE
START_COLUMN = _defaults.START_COLUMN

# Columns an input file must contain.  'START_COLUMN' is absent because
# '_combine_date_time_columns' derives it from the date and time columns.
REQUIRED_COLUMNS = [
    *_defaults.DROP_COLUMNS.split(sep=', '),
    GROUP_BY_COLUMN,
    *[
        column
        for column in _defaults.KEEP_COLUMNS.split(sep=', ')
        if column != START_COLUMN
    ]
]

# Module logger
logger = get_logger(__name__)


def validate_shift_columns(
        shift_data: frame.DataFrame,
        input_file: str
) -> None:
    """ Confirm a shift data file has every required column.

        A hand-edited file with a renamed or missing column otherwise
        surfaced as a bare KeyError from whichever transformation
        reached it first.

        Args:
            shift_data (frame.DataFrame):
                Pandas Data Frame of raw shift data.

            input_file (str):
                Path to the file, for the error message.

        Raises:
            SystemExit:
                When a required column is absent.

        Returns:
            None.
    """

    missing_columns = [
        column
        for column in REQUIRED_COLUMNS
        if column not in shift_data.columns
    ]

    if missing_columns:
        message = (
            f'The shift data file "{input_file}" is missing the '
            f'column(s): {", ".join(missing_columns)}.  A shift data '
            f'file requires: {", ".join(REQUIRED_COLUMNS)}.'
        )
        logger.error(message)
        sys.exit(1)

    return None


def validate_shift_need_ids(
        shift_data: frame.DataFrame,
        input_file: str
) -> None:
    """ Reject shift rows that have no need ID.

        'Helpers.search_shift_info' assigns the review fallback -- a
        category whose need IDs are empty -- to an event title it cannot
        match confidently, so an unmatched Google Calendar event reaches
        the CSV with a blank 'need_id'.  'DataFrame.groupby' drops null
        keys, which would silently discard those rows rather than
        create their shifts, so fail here and name every event that
        needs an alias in the shift data model.

        Args:
            shift_data (frame.DataFrame):
                Pandas Data Frame of shift data with duplicate rows
                removed, still carrying the 'need_name' column.

            input_file (str):
                Path to the file, for the error message.

        Raises:
            SystemExit:
                When any row has a missing, empty, or whitespace-only
                need ID.

        Returns:
            None.
    """

    # Treat a missing, empty, or whitespace-only value as blank
    need_ids = shift_data[GROUP_BY_COLUMN]
    blank_rows = shift_data[need_ids.fillna('').str.strip() == '']

    # Every row has a need ID
    if blank_rows.empty:
        return None

    # Name each unmatched event and the CSV line it came from.  The
    # 'need_name' column is still present at this point in the pipeline
    # (the unused columns are dropped later), and adding 2 to a
    # zero-based index yields the line number in the file.
    need_names = blank_rows.get(NEED_NAME_COLUMN)
    row_details = [
        f'line {index + 2}' if need_names is None
        else f'"{need_names.loc[index]}" (line {index + 2})'
        for index in blank_rows.index
    ]

    message = (
        f'{len(blank_rows)} shift row(s) in "{input_file}" have no need '
        f'ID: {", ".join(row_details)}.  These event titles did not '
        'match a category in the shift data model, so the review '
        'fallback assigned an empty need ID.  Add an alias for each '
        f'title to "{SHIFTS_INFO_FILE}" and collect the calendar data '
        'again, or remove the rows from the CSV file.  No shifts were '
        'created.'
    )
    logger.error(message)
    sys.exit(1)
