#!/usr/bin/env python3
""" star_pass default values.

    Default constant values. Override these values by
    setting environment variables either in the host OS or in a .env
    file at the root folder of the application.  For example, to
    override the value for HTTP_TIMEOUT, add the following line to a
    .env file located in the root directory of the application:

        # .env file contents
        HTTP_TIMEOUT=3

    The application will attempt to load environment
    variable values as constants before importing the default values
    in this file by using the 'default' parameter of the os.getenv
    method:

        # star_pass.py contents
        from os import getenv
        import ._defaults

        HTTP_TIMEOUT = getenv(
            key='HTTP_TIMEOUT',
            default=_defaults.HTTP_TIMEOUT
        )
"""

# Imports - Python Standard Library
from pathlib import Path

# Imports - Third-Party
from yaml import safe_load

# Application run modes
RUN_MODES = (
    'create_amplify_shifts',
    'c',  # Alias for 'create_amplify_shifts
    'get_gcal_events',
    'g'  # Alias for 'get_gcal_events'
)

# Data file management
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
BASE_AMPLIFY_URL = 'https://api.galaxydigital.com/api'
BASE_GCAL_URL = 'https://www.googleapis.com/calendar/v3/calendars'
HTTP_TIMEOUT = 3

# Google Calendar values
BASE_GCAL_ENDPOINT = '/events'
BASE_GCAL_PARAMS = {
    'orderBy': 'startTime',
    'q': '',
    'showDeleted': 'false',
    'singleEvents': 'true',
    'timeMin': '',
    'timeMax': '',
}
GCAL_PRACTICE_CAL_ID = (
    '/rosecityrollers.com_313938323232323331%40resource.calendar.google.com'
)
GCAL_ORDER_BY = 'startTime'
GCAL_SHOW_DELETED = False
GCAL_SINGLE_EVENTS = True
GCAL_TIME_MIN = '2024-09-08T00:00:00-00:00'
GCAL_TIME_MAX = '2024-10-10T00:00:00-00:00'
GCAL_DEFAULT_QUERY_STRINGS = (
    'officials',
    'scrimmage'
)

# Amplify CSV input file management
DROP_COLUMNS = 'need_name, start_date, start_time'
GROUP_BY_COLUMN = 'need_id'
SHIFTS_DICT_KEY_NAME = 'shifts'
START_COLUMN = 'start'
START_DATE_COLUMN = 'start_date'
START_TIME_COLUMN = 'start_time'
KEEP_COLUMNS = f'{START_COLUMN}, duration, slots'

# Shift lookup data model
SHIFT_INFO_FILE_NAME = 'shift_info.yml'
SHIFT_INFO_FILE = Path.joinpath(
    MODELS_DIR_PATH,
    SHIFT_INFO_FILE_NAME
)

# Read the shift info model to set SHIFT_INFO
with open(
    file=SHIFT_INFO_FILE,
    mode='rt',
    encoding='utf-8'
) as yaml_data:
    SHIFT_INFO = safe_load(
        stream=yaml_data.read()
    )

# Miscellaneous
DEFAULT_SLOTS = 20
DATE_TIME_FORMAT = '%Y-%m-%d %H:%M'
FILE_NAME_DATE_TIME_FORMAT = '%Y-%m-%dT%H_%M_%S_%f'
