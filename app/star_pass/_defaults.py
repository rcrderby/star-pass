#!/usr/bin/env python3
""" star_pass default values. """

# Imports - Python Standard Library
from os import path

# Constants
# HTTP request configuration
BASE_HEADERS = {
    'Accept': 'application/json',
    'Content-Type': 'application/json'
}
BASE_URL = 'https://api.galaxydigital.com/api'
HTTP_TIMEOUT = 3

# Data file name and location
BASE_FILE_NAME = 'amplify_shifts'
BASE_FILE_PATH = 'data'

# Input data file
INPUT_FILE_DIR = 'csv'
INPUT_FILE_EXTENSION = '.csv'
INPUT_FILE_PATH = path.join(
    'BASE_FILE_PATH',
    'INPUT_FILE_DIR',
    'BASE_FILE_NAME'
)
INPUT_FILE = f'{INPUT_FILE_PATH}{INPUT_FILE_EXTENSION}'

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
OUTPUT_FILE_PATH = path.join(
    'BASE_FILE_PATH',
    'OUTPUT_FILE_DIR',
    'BASE_FILE_NAME'
)
OUTPUT_FILE = f'{OUTPUT_FILE_PATH}{OUTPUT_FILE_EXTENSION}'
