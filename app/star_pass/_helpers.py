#!/usr/bin/env python3
""" Helper methods for star_pass.py """

# Imports - Python Standard Library
from dataclasses import dataclass
from datetime import datetime, timedelta
from os import getenv
from typing import Any, Dict, Optional
import re

# Imports - Third-Party
from dateparser import parse
from dotenv import load_dotenv
from thefuzz import fuzz, process
from requests import exceptions, Response, Session
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Imports - Local
from . import _defaults
from ._exceptions import ConfigurationError, UpstreamError, ValidationError
from ._logging import get_logger
from . import _models
from ._records import Match, MATCH_KIND_FUZZY, MATCH_KIND_KEYWORD

# Constants
AMPLIFY_DATE_TIME_FORMAT = _defaults.AMPLIFY_DATE_TIME_FORMAT
AMPLIFY_SHIFT_DATETIME_FORMAT = _defaults.AMPLIFY_SHIFT_DATETIME_FORMAT
ENV_FILE_PATH = _defaults.ENV_FILE_PATH
FILE_ENCODING = _defaults.FILE_ENCODING
FUZZY_MATCH_THRESHOLD = _defaults.FUZZY_MATCH_THRESHOLD
GCAL_CALENDARS = _defaults.GCAL_CALENDARS
HTTP_RETRY_BACKOFF_FACTOR = _defaults.HTTP_RETRY_BACKOFF_FACTOR
HTTP_RETRY_STATUS_FORCELIST = _defaults.HTTP_RETRY_STATUS_FORCELIST
HTTP_RETRY_TOTAL = _defaults.HTTP_RETRY_TOTAL
SIMPLE_DATE_FORMAT = _defaults.SIMPLE_DATE_FORMAT
SIMPLE_TIME_FORMAT = _defaults.SIMPLE_TIME_FORMAT

# Module logger
logger = get_logger(__name__)


def amplify_headers() -> Dict[str, str]:
    """ Return the headers an Amplify request carries.

        Here rather than beside any one caller: attaching the
        credential is the same rule for every request, and a second
        copy of it is a second place to forget.

        Read when a request is about to be made rather than held from
        import time, so a deployment that rotates the credential and
        restarts nothing still sends the current one.

        Args:
            None.

        Returns:
            headers (Dict[str, str]):
                The base headers plus the bearer credential.
    """

    headers = dict(_defaults.BASE_HEADERS)
    headers.update(
        {'Authorization': f'Bearer {getenv("AMPLIFY_TOKEN")}'}
    )

    return headers


def parse_amplify_datetime(
        value: Any
) -> Optional[datetime]:
    """ Return an Amplify datetime as a datetime, or None.

        Here rather than beside either caller.  The sign-up summary
        reads a shift's start to decide whether it falls in its window,
        and the shift preview reads the same field to decide whether
        Amplify already has a row (D16).  Two readings of one format
        could disagree about a value with no seconds in it, and the
        disagreement would show up as a shift sent twice.

        Amplify writes datetimes as naive local values, so what comes
        back carries no zone and is directly comparable with another
        one from the same source.

        Args:
            value (Any):
                A datetime string, as Amplify writes one, or None.

        Returns:
            parsed (datetime | None):
                The datetime, or None when the value is missing or is
                not one.
    """

    for date_time_format in (
        AMPLIFY_SHIFT_DATETIME_FORMAT,
        AMPLIFY_DATE_TIME_FORMAT
    ):
        try:
            return datetime.strptime(value, date_time_format)

        except (TypeError, ValueError):
            continue

    return None


@dataclass(frozen=True)
class CategoryMatch:
    """ Which category a title matched, and how it got there.

        The answer to one lookup, kept whole.  A caller that only
        wants the shift configuration reads 'need_details'; a caller
        storing the event needs the other two as well, because a run
        records the match it actually made rather than the one the
        data model would make today.

        Attributes:
            need_details (Dict[str, Any]):
                The category's configuration -- its need IDs, their
                slots and their offsets -- without the alias list a
                reader has no use for.

            category (str, optional):
                Which category matched, or None when nothing did and
                the calendar's review fallback was assigned instead.

            match (Match, optional):
                How it matched, or None when nothing did.
    """

    need_details: Dict[str, Any]
    category: Optional[str] = None
    match: Optional[Match] = None


# Class definitions
class Helpers:
    """ star_pass helper methods. """

    def __init__(self) -> None:
        """ Helpers initialization method.

            Args:
                None.

            Object Attributes:
                _session (requests.Session | None):
                    HTTP session, built on first use by
                    '_build_session' and reused for every request.

            Returns:
                None.
        """

        self._session: Session | None = None

        return None

    # Accepted string representations for each boolean value.
    _TRUE_STRINGS = frozenset({'true', 't', 'yes', 'y', '1'})
    _FALSE_STRINGS = frozenset({'false', 'f', 'no', 'n', '0'})

    def convert_to_bool(
            self,
            arg_value: str
    ) -> bool:
        """ Convert a string representation of a boolean to a bool.

            Comparison is case-insensitive and ignores surrounding
            whitespace. Unrecognized values raise a ValueError rather
            than defaulting, so that a typo (e.g. 'flase') can never
            silently send live API requests.

            Args:
                arg_value (str):
                    String representation of a boolean. Accepted
                    (case-insensitive) values are:
                        True:  'true', 't', 'yes', 'y', '1'
                        False: 'false', 'f', 'no', 'n', '0'

            Raises:
                ValueError:
                    If 'arg_value' is not a recognized boolean string.

            Returns:
                arg_bool (bool):
                    bool object converted from a string.
        """

        # Normalize the string for comparison
        normalized = arg_value.strip().lower()

        # Map the normalized value to a boolean
        if normalized in self._TRUE_STRINGS:
            return True
        if normalized in self._FALSE_STRINGS:
            return False

        # Fail fast on unrecognized input
        accepted = sorted(self._TRUE_STRINGS | self._FALSE_STRINGS)
        raise ValueError(
            f'Cannot convert {arg_value!r} to a boolean. '
            f'Accepted values (case-insensitive): {accepted}.'
        )

    def format_date_time_amplify(
            self,
            date_time_string: str
    ) -> str:
        """ Format a date and time for Amplify compatibility.

            Examples:
                '5/6/24 11:30' --------------> '2024-05-06 11:30'
                '6 may 2024 11:30 am' -------> '2024-05-06 11:30'
                'may 6th, 2024 11:30 a.m.' --> '2024-05-06 11:30'

                See https://dateparser.readthedocs.io/en/latest
                for more information.

            Args:
                date_time_string (str):
                    Space-separated concatenation of a common date
                    format and a common time format.

            Returns:
                formatted_date_time_string (str):
                    Date/time string in the Amplify-specified format.

                    Example:
                        '2024-05-06 11:30'

                    See https://api.galaxydigital.com/docs/#/Need/needAddShifts
        """

        # Parse date/time string into datetime.datetime object
        dt_object = parse(
            date_string=date_time_string
        )

        # 'dateparser.parse' returns None rather than raising when it
        # cannot make sense of the input.  The shift CSV file is
        # reviewed and edited by hand, so a typo here is expected input.
        if dt_object is None:
            raise ValueError(
                f'Cannot read {date_time_string!r} as a date and time.'
            )

        # Convert 'dt_object' to a formatted string
        formatted_date_time_string = dt_object.strftime(
            format=AMPLIFY_DATE_TIME_FORMAT
        )

        return formatted_date_time_string

    def format_shift_date_simple(
            self,
            date_time_string: str
    ) -> str:
        """ Format an Amplify date and time to a simple date format.

            Example:
                '2025-04-09 11:30' ------> 'Wednesday, April 09 2025'

            Args:
                date_time_string (str):
                    Date and time string in the format YYYY-MM-DD HH:MM.

            Returns:
                simple_date_string (str):
                    Date string in the format Wednesday, April 9 2025
        """

        # Convert an Amplify time string to a datetime.datetime object.
        dt_object = datetime.strptime(
            date_time_string,
            "%Y-%m-%d %H:%M"
        )

        # Convert 'dt_object' to a formatted string
        simple_date_string = dt_object.strftime(
            format=SIMPLE_DATE_FORMAT
        )

        return simple_date_string

    def format_shift_time_simple(
            self,
            date_time_string: str,
            shift_duration: str
    ) -> str:
        """ Format an Amplify date and time to a simple shift time.

            Also add an end time based on the duration.

            Example:
                '2025-04-09 11:30' -------> '11:30'

            Args:
                date_time_string (str):
                    Date and time string in the format YYYY-MM-DD HH:MM.

                shift_duration (str):
                    Number of minutes in a shift duration.

            Returns:
                simple_shift_time_string (str):
                    Time string in the format 11:30-12:30.
        """

        # Convert an Amplify time string to a datetime.datetime object.
        dt_object = datetime.strptime(
            date_time_string,
            "%Y-%m-%d %H:%M"
        )

        # Convert 'dt_object' to a formatted start time string
        start_time = dt_object.strftime(
            format=SIMPLE_TIME_FORMAT
        )

        # Convert the shift duration to a timedelta object
        shift_duration_object = timedelta(
            minutes=int(shift_duration)
        )

        # Calculate the shift end time
        end_time_object = dt_object + shift_duration_object

        # Convert 'end_time_object' to a formatted start time string
        end_time = end_time_object.strftime(
            format=SIMPLE_TIME_FORMAT
        )

        # Create a simple shift time string
        simple_shift_time_string = (
            f'{start_time}-{end_time}'
        )

        return simple_shift_time_string

    def get_gcal_info(
            self,
            gcal_name: Dict[str, str]
    ) -> str:
        """ Check the validity of a Google Calendar name.

        Display a message and exit if the calendar is not in the list
        of valid Google Calendars.

            Args:
                gcal_name (str):
                    Google Calendar name to check.

            Returns:
                Dict[str: str]:
                    Dictionary with the ID of the named Google Calendar
                    plus the corresponding URL query string(s).
        """

        # Check for a matching calendar ID.  Returning inside the 'try'
        # keeps the name bound on the only path that reaches the return;
        # the previous trailing return read as though 'gcal_id' were
        # available after the lookup had failed.
        try:
            return GCAL_CALENDARS[gcal_name]

        # Report a 'gcal_name' the configuration does not name
        except KeyError as error:
            message = f'"{gcal_name}" is not a valid calendar name'
            logger.error(message)
            raise ConfigurationError(message) from error

    def search_shift_info(
            self,
            gcal_name: str,
            need_name: str
    ) -> Dict:
        """ Search the shift info data model.

            Args:
                gcal_name (str);
                    Google Calendar name to search.  For example:
                    'Events' or 'Practices'.

                need_name (str);
                    Google Calendar event name to search for.  For
                    example: 'Adult Scrimmage' or 'Juniors Game'.

            Returns:
                need_details (Dict):
                    Dictionary object with need details for the matched
                    category, or the calendar 'default' when no category
                    matches with enough confidence.
        """

        return self.match_shift_info(
            gcal_name=gcal_name,
            need_name=need_name
        ).need_details

    def category_named(
            self,
            gcal_name: str,
            category: str
    ) -> CategoryMatch:
        """ Return a category by name, for a person who chose it.

            Beside 'match_shift_info' because both answer "what does
            this category ask for", and they differ only in how the
            category was reached.  A chosen category carries no 'Match':
            nothing was matched, somebody decided, and a run that
            recorded a match here would claim the model did work it did
            not do.

            Args:
                gcal_name (str):
                    Google Calendar the category belongs to.  For
                    example: 'events' or 'practices'.

                category (str):
                    The category's name in the shift data model.

            Raises:
                ValidationError:
                    If the calendar defines no category by that name.
                    Refused rather than fallen back on: a person naming
                    a category that is not there has made a mistake
                    they would not see in a silent default.

            Returns:
                matched (CategoryMatch):
                    The category and its configuration, with no match.
        """

        calendar = _models.get_shifts_info()['calendar'][gcal_name.lower()]
        categories = calendar['categories']

        if category not in categories:
            known = ', '.join(sorted(categories))
            message = (
                f'The "{gcal_name}" calendar has no "{category}" '
                f'category. It defines: {known}.'
            )
            logger.error(message)
            raise ValidationError(message)

        return CategoryMatch(
            need_details=self._category_need_details(categories[category]),
            category=category
        )

    def match_shift_info(
            self,
            gcal_name: str,
            need_name: str
    ) -> CategoryMatch:
        """ Match a title to a category, and say which one and how.

            The whole answer to the lookup 'search_shift_info' takes
            one field of.  A run stores which category a title matched
            and how it matched, because the data model can change
            between the day a run is collected and the day it is
            reviewed: recomputed later, the match would describe the
            model as it is now instead of what the run actually did.

            Args:
                gcal_name (str):
                    Google Calendar name to search.  For example:
                    'events' or 'practices'.

                need_name (str):
                    Google Calendar event name to search for.

            Returns:
                matched (CategoryMatch):
                    The category, how the title reached it, and its
                    shift configuration.
        """

        calendar = _models.get_shifts_info()['calendar'][gcal_name]
        categories = calendar['categories']

        # Map each alias to the name of the category it belongs to.
        # The name rather than the configuration, because a caller
        # storing the event records which category matched and the
        # configuration does not carry its own name.
        alias_categories = {
            alias: name
            for name, category in categories.items()
            for alias in category['aliases']
        }

        # Deterministic pass: prefer an alias whose words all appear in
        # the title (the longest such alias wins).
        best_alias = self._best_literal_alias(
            need_name,
            list(alias_categories)
        )
        if best_alias is not None:
            return self._matched(
                categories=categories,
                name=alias_categories[best_alias],
                match=Match(
                    kind=MATCH_KIND_KEYWORD,
                    keyword=best_alias
                )
            )

        # Fuzzy fallback: accept the best token-set match only if it
        # clears the confidence threshold.
        match = process.extractOne(
            query=need_name,
            choices=list(alias_categories),
            scorer=fuzz.token_set_ratio
        )
        if match is not None and match[1] >= FUZZY_MATCH_THRESHOLD:
            return self._matched(
                categories=categories,
                name=alias_categories[match[0]],
                # Stored as the scorer gave it.  It answers in whole
                # numbers out of a hundred, which is what a score is
                # shown as, and 'test_helpers' holds it to that: a
                # library that started answering in fractions would
                # otherwise put one in a field typed for a whole
                # number, and nothing would say so.
                match=Match(
                    kind=MATCH_KIND_FUZZY,
                    score=match[1]
                )
            )

        # Unmatched: log for review and fall back to the default
        # category, which names no category and no match, because
        # neither is what happened.
        message = (
            f'No confident shift-info match for "{need_name}" in the '
            f'"{gcal_name}" calendar; assigning the review fallback'
        )
        logger.warning(message)

        return CategoryMatch(
            need_details=self._category_need_details(calendar['default'])
        )

    @classmethod
    def _matched(
            cls,
            categories: Dict,
            name: str,
            match: Match
    ) -> CategoryMatch:
        """ Return the answer for a title that reached a category.

            Args:
                categories (Dict):
                    Every category the calendar defines, by name.

                name (str):
                    The category that matched.

                match (Match):
                    How the title reached it.

            Returns:
                matched (CategoryMatch):
                    The category, the match and the configuration.
        """

        return CategoryMatch(
            need_details=cls._category_need_details(categories[name]),
            category=name,
            match=match
        )

    @classmethod
    def _best_literal_alias(
            cls,
            need_name: str,
            aliases: list
    ):
        """ Return the best alias that appears literally in a title.

            An alias matches when all of its words appear as tokens in
            the title.  Among matches, the longest alias wins (by word
            count, then character length), with ties broken by the
            earliest position of the alias in the title.

            Args:
                need_name (str):
                    Event title to search.

                aliases (list):
                    Candidate alias strings.

            Returns:
                str | None:
                    The best matching alias, or None if none match.
        """

        title_tokens = cls._tokenize(need_name)
        title_token_set = set(title_tokens)
        best_alias = None
        best_key = None
        for alias in aliases:
            alias_tokens = cls._tokenize(alias)
            if all(token in title_token_set for token in alias_tokens):
                position = min(
                    title_tokens.index(token) for token in alias_tokens
                )
                key = (len(alias_tokens), len(alias), -position)
                if best_key is None or key > best_key:
                    best_key = key
                    best_alias = alias

        return best_alias

    @staticmethod
    def _tokenize(
            text: str
    ) -> list:
        """ Split text into lowercase alphanumeric word tokens.

            Args:
                text (str):
                    Text to tokenize.

            Returns:
                list:
                    Lowercase alphanumeric tokens, in order.
        """

        return re.findall(r'[a-z0-9]+', text.lower())

    @staticmethod
    def _category_need_details(
            category: Dict
    ) -> Dict:
        """ Return a category's need details without the alias list.

            Args:
                category (Dict):
                    A category (or 'default') config from the shift-info
                    model.

            Returns:
                Dict:
                    The category config minus the internal 'aliases'
                    key.
        """

        return {
            key: value
            for key, value in category.items()
            if key != 'aliases'
        }

    # Regex patterns matching secret-bearing substrings that must never
    # be printed or logged.  Each pattern keeps the label in group 1 so
    # the substitution shows what was redacted.
    _SECRET_PATTERNS = (
        # Query parameters: '?key=', '&api_key=', 'access_token=', ...
        re.compile(r'(?i)((?:api_|access_|auth_)?(?:key|token)=)[^&\s\'"]+'),
        # Authorization header values
        re.compile(r'(?i)(bearer\s+)[^\s\'"]+'),
        # Slack tokens, which carry their own recognizable prefix and so
        # can leak without an adjacent label
        re.compile(r'(xox[abprs]-)[A-Za-z0-9-]+'),
    )

    def redact_secrets(
            self,
            text: Any
    ) -> str:
        """ Redact API keys and bearer tokens from a string.

            Replaces the value portion of 'key=<value>' query parameters
            and 'Bearer <token>' header values with 'REDACTED', so that
            secrets cannot leak into stdout, stderr, or logs (for
            example, via an exception repr that includes a request URL).

            Args:
                text (Any):
                    Value to scrub.  Converted to a string before
                    redaction.

            Returns:
                redacted (str):
                    The input with any secret values replaced by
                    'REDACTED'.
        """

        # Substitute each secret pattern, preserving the label prefix
        redacted = str(text)
        for pattern in self._SECRET_PATTERNS:
            redacted = pattern.sub(r'\1REDACTED', redacted)

        return redacted

    def _build_session(self) -> Session:
        """ Return a requests Session with retry and backoff configured.

            Transient failures are retried with exponential backoff.
            The urllib3 default set of allowed methods is used, so only
            idempotent methods (GET, HEAD, PUT, DELETE, OPTIONS, TRACE)
            are retried on read errors or the status forcelist.  A POST
            (used to create Amplify shifts) is retried only on a
            connection error that occurred before the request reached
            the server, which cannot create a duplicate shift.

            The session is built once and reused.  A session per request
            left its pooled connections unreleased and defeated the
            connection reuse a Session exists to provide, which matters
            most to the responses reader: it can send up to
            'AMPLIFY_RESPONSES_MAX_PAGES' requests in one run.

            Args:
                None.

            Returns:
                session (requests.Session):
                    A session whose HTTP and HTTPS adapters retry
                    transient failures.
        """

        if self._session is not None:
            return self._session

        retry = Retry(
            total=HTTP_RETRY_TOTAL,
            backoff_factor=HTTP_RETRY_BACKOFF_FACTOR,
            status_forcelist=HTTP_RETRY_STATUS_FORCELIST,
            raise_on_status=False
        )
        adapter = HTTPAdapter(max_retries=retry)

        session = Session()
        session.mount('https://', adapter)
        session.mount('http://', adapter)
        self._session = session

        return session

    def send_api_request(
            self,
            api_request_data: Dict,
            display_request_status: bool = True
    ) -> Response:
        """ Send API request.

            Args:
                api_request_data (Dict):
                    Dictionary of key, value pairs for API request.
                    Common values include:

                    method (str):
                        HTTP method (GET, POST, PUT, PATCH, DELETE).

                    url (str):
                        Fully-qualified API endpoint URI.

                    headers (Dict[str, str]):
                        HTTP headers.

                    json (Any | None):
                        JSON body, or None.

                    timeout (int):
                        HTTP timeout.

                display_request_status (bool, optional):
                    Print a message to display the result of the HTTP
                    request.  Default is 'True'.

            Returns:
                response (requests.Response):
                    HTTP server response object.
        """

        # Send the API request through a retry-enabled session
        session = self._build_session()
        try:
            response = session.request(**api_request_data)
        # Handle TCP Connection Errors
        except (
            exceptions.ConnectionError,
            exceptions.ConnectTimeout,
            exceptions.HTTPError,
            exceptions.ReadTimeout,
            exceptions.Timeout,
            exceptions.TooManyRedirects,
            exceptions.RequestException
        ) as error:
            # Redact any secrets before logging.  'repr' captures the
            # error type and message without the fragile assumptions of
            # digging into nested exception args -- the previous approach
            # assumed a '>: ' delimiter and raised IndexError on read
            # timeouts.  The repr may include the request URL with its
            # 'key' query parameter, hence the redaction.
            detail = self.redact_secrets(repr(error))
            message = f'An HTTP error occurred: {detail}'
            logger.error(message)
            raise UpstreamError(message) from error

        # Check for HTTP errors
        try:
            if response.ok is not True:
                response.raise_for_status()

        # Handle non-ok HTTP responses
        except exceptions.HTTPError as error:
            # Redact any secrets before logging
            detail = self.redact_secrets(repr(error))
            message = (
                'The request returned a bad status code '
                f'({response.status_code}): {detail}'
            )
            logger.error(message)
            raise UpstreamError(message) from error

        # Log the HTTP request status
        if display_request_status is True:
            # Create display URL that does not expose any paths or parameters
            display_url = response.request.url.replace(
                response.request.path_url,
                ''
            )

            message = (
                f'HTTP API response: {display_url} -> '
                f'HTTP {response.status_code} {response.reason}'
            )
            logger.info(message)

        return response

    def response_json(
            self,
            response: Response
    ) -> Any:
        """ Parse an HTTP response body as JSON.

            Guards against a non-JSON body -- for example, an HTML
            gateway error page returned with a 2xx status.  The error is
            logged with secrets redacted.

            Args:
                response (requests.Response):
                    HTTP response whose body should be JSON.

            Raises:
                UpstreamError:
                    If the body is not valid JSON.

            Returns:
                data (Any):
                    The parsed JSON body.
        """

        # 'requests' raises a ValueError subclass when the body is not
        # valid JSON.
        try:
            return response.json()
        except ValueError as error:
            detail = self.redact_secrets(repr(error))
            message = f'The response body was not valid JSON: {detail}'
            logger.error(message)
            raise UpstreamError(message) from error


# Standalone functions
def require_env_vars(
        *var_names: str
) -> None:
    """ Confirm required environment variables have a value.

        Without this check a missing credential is only discovered when
        the API rejects the request: the run sends 'Bearer None' (or
        'key=None'), gets a 401 or 403, and reports the status code,
        which says nothing about the actual cause.

        Args:
            *var_names (str):
                Names of the environment variables to require.

        Raises:
            ConfigurationError:
                When any named variable is unset or empty.

        Returns:
            None.
    """

    missing = [name for name in var_names if not getenv(name)]

    if missing:
        message = (
            f'{", ".join(missing)} must be set to run this command.  '
            'Add the value(s) to the .env file at the repository root '
            '(see .env.example).'
        )
        logger.error(message)
        raise ConfigurationError(message)

    return None


def load_env_file() -> bool:
    """ Load environment variables from an .env file.

        Args:
            None.

        Returns:
            load_env_status (bool):
                Boolean value indicating whether or not the
                'load_dotenv' function reads environment variables
                from the specified file.
    """

    # Load environment variables
    load_env_status = load_dotenv(
        dotenv_path=ENV_FILE_PATH,
        encoding=FILE_ENCODING
    )

    return load_env_status
