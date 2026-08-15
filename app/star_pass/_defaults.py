#!/usr/bin/env python3
""" star_pass default values. """

# Imports - Python Standard Library
from os import getenv
from pathlib import Path
from typing import List

# Imports - Third-Party
from dotenv import load_dotenv


# Environment
# Encoding for file *content* (CSV, JSON, YAML, .env).  Not the
# filesystem encoding, which describes path names and is not
# guaranteed to be UTF-8; a non-ASCII event title needs this one.
FILE_ENCODING = 'utf-8'
# .env file path
ENV_FILE_PATH = './.env'
# Load environment variables before any setting is read, so every value
# in this module can be supplied by the .env file as well as by the
# process environment (twelve-factor config).  Values already present in
# the environment win over the file.
#
# Nothing may call 'getenv' above this line.  A setting read before the
# load binds to its default and the .env file has no effect on it, with
# no error to say so.
load_dotenv(
    dotenv_path=ENV_FILE_PATH,
    encoding=FILE_ENCODING
)

# The league's local time zone, as an IANA name.  Everything that has
# to agree with a wall clock reads this: which calendar day a summary
# covers, the 'as of' stamp on a summary, and the calendar search
# window.  The host clock cannot be trusted for it -- a container or a
# CI runner usually runs in UTC, where the local evening is already
# tomorrow.
LOCAL_TIMEZONE = getenv(
    'LOCAL_TIMEZONE',
    'America/Los_Angeles'
)

# Date and time formatting
AMPLIFY_DATE_TIME_FORMAT = '%Y-%m-%d %H:%M'
# Amplify returns shift/response datetimes with seconds.
AMPLIFY_SHIFT_DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'
FILE_NAME_DATE_TIME_FORMAT = '%Y-%m-%dT%H_%M_%S_%f'
SIMPLE_DATE_FORMAT = '%A, %B %d %Y'
SIMPLE_TIME_FORMAT = '%H:%M'

# Data file management
# 'FILE_ENCODING' and 'ENV_FILE_PATH' are defined with the .env load
# above, which is the first thing this module does.


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

# SQLite database file path.  Holds the state the repository layer
# owns: runs, the revisions of each one, their events and the change
# log.  Named by an environment variable because it is an attached
# resource (twelve-factor), so a deployment points it at a mounted
# volume without a code change.
DATABASE_FILE = Path(
    getenv(
        'STAR_PASS_DATABASE_PATH',
        str(
            Path.joinpath(
                DATA_DIR_PATH,
                'star_pass.db'
            )
        )
    )
)
# Seconds a statement waits for another connection to release its lock
# before giving up.  SQLite takes one writer at a time, so a wait is
# ordinary rather than a fault; failing immediately would turn two
# overlapping requests into an error the caller has to retry.
DATABASE_BUSY_TIMEOUT = float(
    getenv(
        'STAR_PASS_DATABASE_BUSY_TIMEOUT',
        '5'
    )
)

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
# 'GCAL_WINDOW_START' and 'GCAL_WINDOW_END' have no default here.  They
# bound the calendar search window, which moves with every run, so no
# default stays correct, and a stale one collects zero events and
# writes an empty CSV.  'gcal_data' requires them from the environment
# and reports a clear error when they are missing.
# Time zone applied to a search window value written without a UTC
# offset, so a plain local date means the same thing year round and
# Daylight Saving is applied automatically.  A value that carries its
# own offset is used as written.
GCAL_TIMEZONE = getenv(
    'GCAL_TIMEZONE',
    LOCAL_TIMEZONE
)
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
GROUP_BY_COLUMN = 'need_id'
NEED_NAME_COLUMN = 'need_name'
SHIFTS_DICT_KEY_NAME = 'shifts'
START_COLUMN = 'start'
START_DATE_COLUMN = 'start_date'
START_TIME_COLUMN = 'start_time'
DROP_COLUMNS = f'{NEED_NAME_COLUMN}, {START_DATE_COLUMN}, {START_TIME_COLUMN}'
KEEP_COLUMNS = f'{START_COLUMN}, duration, slots'

# Amplify shift output formatting
HTTP_CHECK_MODE_MESSAGE = '\n** HTTP API Check Mode Run **'
VERBOSITY_LEVELS = (
    'basic',    # Shift name and number of new shifts
    'simple',   # Basic data plus shift dates and times
    'detailed'  # JSON data with headings
)

# Slack configuration
# Destination channel IDs (non-secret deployment config).  The bot
# token itself is a secret and is read in slack_notify.py, not here.
SLACK_CHANNEL_ID = getenv('SLACK_CHANNEL_ID')
SLACK_DEV_CHANNEL_ID = getenv('SLACK_DEV_CHANNEL_ID')
# Displayed when a Slack post is skipped in check mode (dry run).
SLACK_CHECK_MODE_MESSAGE = '\n** Slack Check Mode Run (no message sent) **'
# Text appended to a sign-up button's label, marking that it opens a
# browser rather than acting inside Slack.  A plain arrow rather than
# ':arrow_upper_right:', which Slack renders as a full emoji tile with
# a hover card and which crowds out the label on a narrow button.  Set
# it empty for no suffix.
#
# U+2197 carries an emoji presentation by default and would render as
# that same tile, so U+FE0E follows it to ask for the text glyph.  The
# selector is invisible, which is why both are written as escapes: a
# literal arrow pasted here looks identical with the selector dropped,
# and the tile would return with nothing in the diff to explain it.
SLACK_SIGN_UP_BUTTON_SUFFIX = getenv(
    'SLACK_SIGN_UP_BUTTON_SUFFIX',
    ' \u2197\ufe0e'
)
# Slack button style for the sign-up buttons: 'primary' fills them,
# which reads as a control rather than a label on a phone.  Slack
# also accepts 'danger'; an empty value leaves them outlined.
SLACK_SIGN_UP_BUTTON_STYLE = getenv(
    'SLACK_SIGN_UP_BUTTON_STYLE',
    'primary'
)
# Call to action shown above the sign-up buttons.
SLACK_SIGN_UP_PROMPT = getenv(
    'SLACK_SIGN_UP_PROMPT',
    "Sign up if you plan to attend and haven't already. Thanks!"
)
# Optional emoji flanking the summary heading, as Slack shortcodes
# (for example ':flamingo::zebra:').  Empty by default.
SLACK_SUMMARY_EMOJI = getenv(
    'SLACK_SUMMARY_EMOJI',
    ''
)
# Separator between an event name and a role in an opportunity title,
# used to group opportunities and shorten their labels.  A title
# without it forms a group of its own.
SLACK_TITLE_SEPARATOR = getenv(
    'SLACK_TITLE_SEPARATOR',
    ': '
)
# Comma-separated Amplify need IDs summarized when -N is not supplied.
SLACK_SUMMARY_NEED_IDS = _get_env_list(
    'SLACK_SUMMARY_NEED_IDS',
    []
)
# Number of calendar days a sign-up summary covers, counting today as
# day one: 1 is today only, 2 adds tomorrow, and so on.  The summary
# replaces a same-day call for volunteers, so the default is today.
SLACK_SUMMARY_DAYS = int(
    getenv(
        'SLACK_SUMMARY_DAYS',
        '1'
    )
)
# Days between today and the first day a sign-up summary covers: 0
# starts today, 1 starts tomorrow.  A post made ahead of the shifts it
# covers uses this to leave out the day it is sent, so a Friday notice
# about the weekend lists Saturday and Sunday only.
SLACK_SUMMARY_START_IN_DAYS = int(
    getenv(
        'SLACK_SUMMARY_START_IN_DAYS',
        '0'
    )
)

# Amplify responses (sign-ups)
# Public need-detail URL used for shift sign-up link buttons.
AMPLIFY_NEED_DETAIL_URL = getenv(
    'AMPLIFY_NEED_DETAIL_URL',
    'https://rosecityrollers.galaxydigital.com/need/detail/'
)
# Extended timeout (seconds) for a responses page.  Response reads are
# slower than a need read, so the default HTTP_TIMEOUT is too short.
AMPLIFY_RESPONSES_TIMEOUT = int(
    getenv(
        'AMPLIFY_RESPONSES_TIMEOUT',
        '90'
    )
)
# Look-back window (days) for the 'since_created' filter on the responses
# read.  The Amplify API has no server-side filter for a need or for a
# shift's date; 'since_created' (when the sign-up record was created) is
# the only lever that bounds the volume, so the whole domain's recent
# responses are paged and filtered to the target need client-side.
#
# The window is safe because a sign-up cannot predate the shift it is
# for, and shifts are created at most a month or two ahead, so a sign-up
# for an upcoming shift is always recent.  Widen this value if sign-ups
# might be created further ahead than the window; 'AmplifyResponses'
# logs the observed margin on every run and warns when it gets thin.
AMPLIFY_RESPONSES_SINCE_DAYS = int(
    getenv(
        'AMPLIFY_RESPONSES_SINCE_DAYS',
        '90'
    )
)
# Results per page for the responses read (the API maximum is 150).
AMPLIFY_RESPONSES_PER_PAGE = int(
    getenv(
        'AMPLIFY_RESPONSES_PER_PAGE',
        '150'
    )
)
# Safety cap on the number of response pages read in one run.
AMPLIFY_RESPONSES_MAX_PAGES = int(
    getenv(
        'AMPLIFY_RESPONSES_MAX_PAGES',
        '80'
    )
)
# Datetime format the API expects for the 'since_created' parameter.
AMPLIFY_RESPONSES_SINCE_FORMAT = '%Y-%m-%d %H:%M'
# Warn when the oldest counted sign-up was created fewer than this many
# days after the 'since_created' cutoff (a thin margin risks undercount).
AMPLIFY_RESPONSES_MARGIN_WARN_DAYS = int(
    getenv(
        'AMPLIFY_RESPONSES_MARGIN_WARN_DAYS',
        '7'
    )
)

# Amplify Shift lookup data model
SLACK_ROLE_LABELS_FILE_NAME = 'slack_role_labels.yml'
SLACK_ROLE_LABELS_FILE = Path.joinpath(
    MODELS_DIR_PATH,
    SLACK_ROLE_LABELS_FILE_NAME
)

SHIFTS_INFO_FILE_NAME = 'shift_info.yml'
SHIFTS_INFO_FILE = Path.joinpath(
    MODELS_DIR_PATH,
    SHIFTS_INFO_FILE_NAME
)
