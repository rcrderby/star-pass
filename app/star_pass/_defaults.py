#!/usr/bin/env python3
""" star_pass default values. """

# Imports - Python Standard Library
from os import getenv
from pathlib import Path
from typing import List
import sys

# Imports - Third-Party
from dotenv import load_dotenv
from yaml import safe_load

# Date and time formatting
AMPLIFY_DATE_TIME_FORMAT = '%Y-%m-%d %H:%M'
FILE_NAME_DATE_TIME_FORMAT = '%Y-%m-%dT%H_%M_%S_%f'
SIMPLE_DATE_FORMAT = '%A, %B %d %Y'
SIMPLE_TIME_FORMAT = '%H:%M'

# Data file management
FILE_ENCODING = sys.getfilesystemencoding()
# .env file path
ENV_FILE_PATH = './.env'
# Load environment variables so the deployment values defined below can
# be overridden via the environment (twelve-factor config).  Values
# already present in the environment are not overridden by the .env file.
load_dotenv(
    dotenv_path=ENV_FILE_PATH,
    encoding=FILE_ENCODING
)


def _get_env_list(
        var_name: str,
        default: List[str]
) -> List[str]:
    """ Read a comma-separated environment variable as a list.

        Args:
            var_name (str):
                Name of the environment variable to read.

            default (List[str]):
                Value to return when the variable is unset.

        Returns:
            List[str]:
                The comma-separated values as a list of stripped
                strings, or 'default' when the variable is unset.
    """

    raw_value = getenv(var_name)
    if raw_value is None:
        return default
    return [item.strip() for item in raw_value.split(',')]


# Path relative to this file
CURRENT_FILE_PATH = Path(__file__).parent
# 'app' directory path
APP_DIR_PATH = CURRENT_FILE_PATH.parent
# 'data' directory path
DATA_DIR_PATH = Path.joinpath(
    APP_DIR_PATH.parent,
    'data'
)
# 'input' directory path
INPUT_DIR_PATH = Path.joinpath(
    DATA_DIR_PATH,
    'csv'
)
# 'models' directory path
MODELS_DIR_PATH = Path.joinpath(
    APP_DIR_PATH.parent,
    'models'
)
# 'output' directory path
OUTPUT_DIR_PATH = Path.joinpath(
    DATA_DIR_PATH,
    'json'
)
# 'schema' directory path
SCHEMA_DIR_PATH = Path.joinpath(
    APP_DIR_PATH,
    'schema'
)
# JSON Schema file path
JSON_SCHEMA_DIR = SCHEMA_DIR_PATH
JSON_SCHEMA_SHIFT_FILE_NAME = 'amplify.shifts.schema.json'
JSON_SCHEMA_SHIFT_FILE = Path.joinpath(
    JSON_SCHEMA_DIR,
    JSON_SCHEMA_SHIFT_FILE_NAME
)

# Input and output data file extensions
INPUT_FILE_EXTENSION = '.csv'
OUTPUT_FILE_EXTENSION = '.json'

# HTTP request configuration
BASE_HEADERS = {
    'Accept': 'application/json',
    'Content-Type': 'application/json'
}
BASE_AMPLIFY_URL = getenv(
    'BASE_AMPLIFY_URL',
    'https://api.galaxydigital.com/api'
)
BASE_GCAL_URL = getenv(
    'BASE_GCAL_URL',
    'https://www.googleapis.com/calendar/v3/calendars'
)
HTTP_TIMEOUT = int(
    getenv(
        'HTTP_TIMEOUT',
        '10'
    )
)

# HTTP retry configuration
# Total retry attempts for transient failures.
HTTP_RETRY_TOTAL = int(
    getenv(
        'HTTP_RETRY_TOTAL',
        '3'
    )
)
# Exponential backoff factor between retries, in seconds.
HTTP_RETRY_BACKOFF_FACTOR = float(
    getenv(
        'HTTP_RETRY_BACKOFF_FACTOR',
        '0.5'
    )
)
# Response status codes that trigger a retry (idempotent methods only;
# see Helpers._build_session).  urllib3 never retries a POST body-write
# on these, so shift-creating POSTs are not automatically re-sent.
HTTP_RETRY_STATUS_FORCELIST = (429, 500, 502, 503, 504)

# Logging configuration
LOG_LEVEL = getenv(
    'LOG_LEVEL',
    'INFO'
)

# Fuzzy match confidence threshold (0-100).  When no alias appears
# literally in an event title, the fuzzy fallback must score at least
# this high to assign a category; otherwise the title is sent to review.
FUZZY_MATCH_THRESHOLD = int(
    getenv(
        'FUZZY_MATCH_THRESHOLD',
        '80'
    )
)

# Google Calendar values
BASE_GCAL_ENDPOINT = '/events'
GCAL_ORDER_BY = 'startTime'
GCAL_SHOW_DELETED = 'false'
GCAL_SINGLE_EVENTS = 'true'
GCAL_TIME_MIN = '2025-01-01T00:00:00-00:00'
GCAL_TIME_MAX = '2025-02-09T00:00:00-00:00'
GCAL_EVENTS_QUERY_STRINGS = _get_env_list(
    'GCAL_EVENTS_QUERY_STRINGS',
    ['']
)
GCAL_PRACTICES_QUERY_STRINGS = _get_env_list(
    'GCAL_PRACTICES_QUERY_STRINGS',
    ['officials', 'scrimmage']
)
BASE_GCAL_PARAMS = {
    'orderBy': GCAL_ORDER_BY,
    'q': '',
    'showDeleted': GCAL_SHOW_DELETED,
    'singleEvents': GCAL_SINGLE_EVENTS,
    'timeMin': '',
    'timeMax': '',
}
GCAL_ID_PREFIX = '/rosecityrollers.com_'
GCAL_EVENTS_CAL_ID = getenv(
    'GCAL_EVENTS_CAL_ID',
    (
        f'{GCAL_ID_PREFIX}'
        '2d35383436363030372d363035@resource.calendar.google.com'
    )
)
GCAL_PRACTICES_CAL_ID = getenv(
    'GCAL_PRACTICES_CAL_ID',
    (
        f'{GCAL_ID_PREFIX}'
        '313938323232323331%40resource.calendar.google.com'
    )
)
GCAL_CALENDARS = {
    'events': {
        'gcal_id': GCAL_EVENTS_CAL_ID,
        'query_strings': GCAL_EVENTS_QUERY_STRINGS
    },
    'practices': {
        'gcal_id': GCAL_PRACTICES_CAL_ID,
        'query_strings': GCAL_PRACTICES_QUERY_STRINGS
    }
}

GCAL_PREFIX_FILTERS = (
    'canceled',
    'cancelled',
    'derby daze',
    'summer camp'
)

# Amplify CSV input file management
DROP_COLUMNS = 'need_name, start_date, start_time'
GROUP_BY_COLUMN = 'need_id'
SHIFTS_DICT_KEY_NAME = 'shifts'
START_COLUMN = 'start'
START_DATE_COLUMN = 'start_date'
START_TIME_COLUMN = 'start_time'
KEEP_COLUMNS = f'{START_COLUMN}, duration, slots'

# Amplify shift output formatting
HTTP_CHECK_MODE_MESSAGE = '\n** HTTP API Check Mode Run **'
VERBOSITY_LEVELS = (
    'basic',    # Shift name and number of new shifts
    'simple',   # Basic data plus shift dates and times
    'detailed'  # JSON data with headings
)

# Amplify Shift lookup data model
SHIFTS_INFO_FILE_NAME = 'shift_info.yml'
SHIFTS_INFO_FILE = Path.joinpath(
    MODELS_DIR_PATH,
    SHIFTS_INFO_FILE_NAME
)

# Read the Amplify shift info model to set the SHIFTS_INFO constant
with open(
    file=SHIFTS_INFO_FILE,
    mode='rt',
    encoding=FILE_ENCODING
) as yaml_data:
    SHIFTS_INFO = safe_load(
        stream=yaml_data.read()
    )
