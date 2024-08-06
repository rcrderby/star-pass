#!/usr/bin/env python3
""" star_pass default values.

    Default constant values for star_pass.py. Override these values by
    setting environment variables either in the host OS or in a .env
    file at the root folder of the application.  For example, to
    override the value for HTTP_TIMEOUT, add the following line to a
    .env file located in the root directory of the application:

        # .env file contents
        HTTP_TIMEOUT=5

    The application (star_pass.py) will attempt to load environment
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

# Constants
# HTTP request configuration
BASE_HEADERS = {
    'Accept': 'application/json',
    'Content-Type': 'application/json'
}
BASE_AMPLIFY_URL = 'https://api.galaxydigital.com/api'
BASE_GCAL_URL = 'https://www.googleapis.com/calendar/v3/calendars/'
HTTP_TIMEOUT = '3'

# Google Calendar...
GCAL_PRACTICE_CAL_ID = (
    'rosecityrollers.com_313938323232323331%40resource.calendar.google.com'
)
GCAL_ORDER_BY = 'startTime'
GCAL_SHOW_DELETED = False
GCAL_SINGLE_EVENTS = True
GCAL_TIME_MIN = '2024-09-01T00:00:00-00:00'
GCAL_TIME_MAX = '2024-10-10T00:00:00-00:00'
GCAL_TEXT_QUERY = 'scrimmage'

# Data file name and location
BASE_FILE_NAME = 'amplify_shifts'
BASE_FILE_PATH = 'data'

# Input data file
INPUT_FILE_DIR = 'csv'
INPUT_FILE_EXTENSION = '.csv'

# Data file management
DROP_COLUMNS = 'need_name, start_date, start_time'
GROUP_BY_COLUMN = 'need_id'
SHIFTS_DICT_KEY_NAME = 'shifts'
START_COLUMN = 'start'
START_DATE_COLUMN = 'start_date'
START_TIME_COLUMN = 'start_time'
KEEP_COLUMNS = f'{START_COLUMN}, duration, slots'

# JSON Schema
JSON_SCHEMA_DIR = 'app/schema'
JSON_SCHEMA_SHIFT_FILE = 'amplify.shifts.schema.json'

# Output data file
OUTPUT_FILE_DIR = 'json'
OUTPUT_FILE_EXTENSION = '.json'
