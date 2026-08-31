#!/usr/local/bin/python3
""" Google Calendar shift management classes and methods. """

# Imports - Python Standard Library
from copy import copy
from dataclasses import dataclass
from os import getenv
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Imports - Local
from . import _defaults
from ._exceptions import ConfigurationError
from ._records import (
    UNCOLLECTED_ALL_DAY,
    UNCOLLECTED_EXCLUDED,
    UNCOLLECTED_UNTITLED
)
from ._reporting import (
    Reporter,
    STEP_FILTER_EVENTS,
    STEP_READ_CALENDAR
)
from ._helpers import Helpers, load_env_file
from ._logging import get_logger

# Load environment variables
load_env_file()

# Constants
# Authentication
GCAL_TOKEN = getenv(
    key='GCAL_TOKEN'
)

# HTTP request configuration
BASE_GCAL_HEADERS = copy(_defaults.BASE_HEADERS)
GCAL_CALENDARS = _defaults.GCAL_CALENDARS
BASE_GCAL_ENDPOINT = _defaults.BASE_GCAL_ENDPOINT
BASE_GCAL_PARAMS = _defaults.BASE_GCAL_PARAMS
BASE_GCAL_URL = _defaults.BASE_GCAL_URL
HTTP_TIMEOUT = _defaults.HTTP_TIMEOUT

# The query string that searches nothing and so returns the whole
# window.  A calendar configured with it is already read whole, which
# is why reading the window costs a second request on some calendars
# and none on others.
WHOLE_WINDOW_QUERY = ''

# Module logger
logger = get_logger(__name__)


@dataclass(frozen=True)
class WindowRead:
    """ One reading of a calendar window, searched and whole.

        Both halves, because what a run does not collect is the
        difference between them: an event the query strings never
        returned is one nobody looked for.

        Attributes:
            searched (List[Dict[str, Any]]):
                What the configured query strings returned, which is
                what the run is built from.

            everything (List[Dict[str, Any]]):
                Every event in the window, whatever it is called.
    """

    searched: List[Dict[str, Any]]
    everything: List[Dict[str, Any]]


def item_times(
        gcal_item: Dict[str, Any]
) -> Tuple[str, str] | None:
    """ Return a calendar item's start and end times.

        A timed event carries a 'dateTime'; an all-day event carries a
        'date' instead and so cannot become a shift.

        Args:
            gcal_item (Dict[str, Any]):
                Raw Google Calendar item.

        Returns:
            times (Tuple[str, str] | None):
                The ('start', 'end') ISO datetime strings, or None when
                either is absent.
    """

    start = (gcal_item.get('start') or {}).get('dateTime')
    end = (gcal_item.get('end') or {}).get('dateTime')

    if not start or not end:
        return None

    return start, end


def _is_excluded_title(
        need_name: str
) -> bool:
    """ Determine whether an event title excludes it from shifts.

        Args:
            need_name (str):
                Google Calendar event title.

        Returns:
            bool:
                True when the title contains any excluded term.
    """

    title = need_name.lower()

    return any(
        excluded_term in title
        for excluded_term in _defaults.GCAL_PREFIX_FILTERS
    )


def exclusion_reason(
        gcal_item: Dict[str, Any]
) -> Optional[str]:
    """ Return why an item must not become a shift, or None.

        One answer, read twice: the filter drops the items it names,
        and the collection records them against the run so a reviewer
        is told what the window held and why it is not there.

        Args:
            gcal_item (Dict[str, Any]):
                Raw Google Calendar item.

        Returns:
            reason (str | None):
                One of the reasons in '_records.UNCOLLECTED_REASONS',
                or None when the item can become a shift.
    """

    # An untitled event cannot be matched to a need
    if not gcal_item.get('summary'):
        return UNCOLLECTED_UNTITLED

    # Cancelled and non-officiated events never become shifts
    if _is_excluded_title(need_name=gcal_item['summary']) is True:
        return UNCOLLECTED_EXCLUDED

    # An all-day event has a 'date' instead of a 'dateTime', so it has
    # no start or end time to build a shift from
    if item_times(gcal_item=gcal_item) is None:
        return UNCOLLECTED_ALL_DAY

    return None


class GCALData:
    """ Collect and manage Google Calendar data. """
    def __init__(
            self,
            gcal_name: str,
            reporter: Reporter | None = None,
            **kwargs: Any
    ) -> None:
        """ Class initialization method.

            Construction reads nothing and sends no request.
            'get_gcal_shift_data' collects the items in a window,
            'filter_gcal_items' removes the ones that must not become
            shifts, and 'read_window' does the first while reading the
            whole window beside it.

            Args:
                gcal_name (str):
                    Name of the Google Calendar to request data from.
                    Example: 'Practices' or 'Events'

                reporter (Reporter, optional):
                    Receives progress and result events.  Defaults to
                    None, which discards them: how the run is displayed
                    is the caller's concern.

                **kwargs (Any, optional):
                    Unspecified keyword arguments.

            Return:
                None.
        """

        # Initialize helper methods
        self.helpers = Helpers()

        # Report progress nowhere unless the caller supplies a
        # destination
        self.reporter = reporter if reporter is not None else Reporter()

        # Validate the 'gcal_name' argument value
        self.gcal_name = gcal_name.lower()
        self.helpers.get_gcal_info(
            gcal_name=gcal_name.lower()
        )

        return None

    def _calendar_settings(self) -> Tuple[str, Sequence[str]]:
        """ Return the calendar's identifier and its query strings.

            Args:
                None.

            Raises:
                ConfigurationError:
                    If the deployment configured either as nothing.

            Returns:
                settings (Tuple[str, Sequence[str]]):
                    The calendar identifier and the strings it is
                    searched with.
        """

        gcal_id = GCAL_CALENDARS[self.gcal_name].get('gcal_id')
        query_strings = GCAL_CALENDARS[self.gcal_name].get('query_strings')

        # A missing identifier and an empty one are the same
        # deployment mistake: '.env.example' ships the key with no
        # value, so 'is None' would let an unfinished '.env' send
        # Google a request for no calendar.  The query strings keep
        # the identity test, because [''] is falsy and is a real
        # setting.
        if not gcal_id or query_strings is None:
            # Log an error message and exit
            message = f'Invalid Google Calendar data for "{self.gcal_name}"'
            logger.error(message)
            raise ConfigurationError(message)

        # The separator belongs to the URL, not to the value.  An
        # identifier carrying one would build a path with '//' in it,
        # which Google answers with a 404 that says nothing about the
        # cause.
        if gcal_id.startswith('/'):
            message = (
                f'The Google Calendar identifier for "{self.gcal_name}" '
                'starts with "/".  Set it to the calendar identifier '
                'alone, without a leading slash.'
            )
            logger.error(message)
            raise ConfigurationError(message)

        return gcal_id, query_strings

    def _read(  # pylint: disable=too-many-locals
            self,
            query_strings: Sequence[str],
            timeMin: str,  # pylint: disable=invalid-name
            timeMax: str,  # pylint: disable=invalid-name
            timeout: int = HTTP_TIMEOUT
    ) -> List[Dict[str, Any]]:
        """ Return every item a set of query strings finds in a window.

            Below both readings of a window - the configured strings
            build the run, the empty string reads it whole - so the two
            cannot page or de-duplicate differently.

            Args:
                query_strings (Sequence[str]):
                    What to search for, one search each.

                timeMin (str):
                    ISO-formatted string start date/time.

                timeMax (str):
                    ISO-formatted string end date/time.

                timeout (int, optional):
                    HTTP timeout.  Default is HTTP_TIMEOUT.

            Raises:
                ConfigurationError:
                    If the calendar is not configured.

                UpstreamError:
                    If the calendar cannot be read.

            Returns:
                items (List[Dict[str, Any]]):
                    Every item returned, in the order the searches ran.
        """

        # Create a list of shifts for Google Calendar data
        gcal_shift_data = []

        # Set HTTP request variables
        method = 'GET'
        headers = BASE_GCAL_HEADERS

        gcal_id, _ = self._calendar_settings()

        # Construct URL.  The separator is written here, so the
        # configured value is the calendar identifier Google shows and
        # nothing else.
        url = (
            f'{BASE_GCAL_URL}'
            f'/{gcal_id}'
            f'{BASE_GCAL_ENDPOINT}'
        )

        # Construct base URL parameters
        params = {}
        params.update(**BASE_GCAL_PARAMS)
        params.update({'timeMin': timeMin})
        params.update({'timeMax': timeMax})
        params.update({'key': GCAL_TOKEN})

        # Loop over keywords to construct consolidated results
        for query_string in query_strings:

            # Update the 'q' query string parameter and reset pagination
            # so a page token from a previous query does not carry over.
            params.update({'q': query_string})
            params.pop('pageToken', None)

            # Page through every result set for this query string. The
            # Google Calendar API returns a 'nextPageToken' whenever more
            # results are available (the default page size is 250).
            while True:

                # Construct API request data
                api_request_data = {
                    'method': method,
                    'url': url,
                    'headers': headers,
                    'params': params,
                    'timeout': timeout
                }

                # Send API request
                response = self.helpers.send_api_request(
                    api_request_data=api_request_data
                )
                response_json = self.helpers.response_json(response)

                # Add matching results to `gcal_shift_data`, defaulting
                # to an empty list when the 'items' key is absent.
                gcal_shift_data += response_json.get('items') or []

                # Stop unless the response supplies a next page token.
                next_page_token = response_json.get('nextPageToken')
                if not next_page_token:
                    break
                params.update({'pageToken': next_page_token})

        return gcal_shift_data

    def get_gcal_shift_data(
            self,
            timeMin: str,  # pylint: disable=invalid-name
            timeMax: str,  # pylint: disable=invalid-name
            timeout: int = HTTP_TIMEOUT
    ) -> List[Dict[str, Any]]:
        """ Get shift data from the Google Calendar.

            Args:
                timeMin (str):
                    ISO-formatted string start date/time for shifts in
                    calendar query

                    Example:
                        '2024-09-01T00:00:00-00:00'

                timeMax (str):
                    ISO-formatted string end date/time for shifts in
                    calendar query.

                    Example:
                        '2024-10-10T00:00:00-00:00'

                timeout (int, optional):
                    HTTP timeout.  Default is HTTP_TIMEOUT.

            Raises:
                ConfigurationError:
                    If the calendar is not configured.

                UpstreamError:
                    If the calendar cannot be read.

            Returns:
                gcal_shift_data (List[Dict[str, Any]]):
                    Data returned by the Google Calendar service.
        """

        _, query_strings = self._calendar_settings()

        return self._read(
            query_strings=query_strings,
            timeMin=timeMin,
            timeMax=timeMax,
            timeout=timeout
        )

    def read_window(
            self,
            timeMin: str,  # pylint: disable=invalid-name
            timeMax: str,  # pylint: disable=invalid-name
            timeout: int = HTTP_TIMEOUT
    ) -> WindowRead:
        """ Read a window as it is searched and as it stands.

            Two readings, because the events nobody looked for are
            the ones the query strings never returned.  A calendar
            searched with the empty string is already read whole, so
            its second reading is the first.

            Args:
                timeMin (str):
                    First moment the window covers.

                timeMax (str):
                    First moment after it.

                timeout (int, optional):
                    What each of the reads waits.  Default is
                    HTTP_TIMEOUT.

            Raises:
                ConfigurationError:
                    If the deployment has not configured the calendar.

                UpstreamError:
                    If either read fails.

            Returns:
                read (WindowRead):
                    What the searches found, and everything the window
                    holds.
        """

        # The step covers both readings rather than the searched one
        # alone.  Reported around 'get_gcal_shift_data' it would
        # finish while a second call to the calendar was still to be
        # made, which is a step saying it is done before it is.
        self.reporter.step_started(step=STEP_READ_CALENDAR)

        _, query_strings = self._calendar_settings()
        searched = self.get_gcal_shift_data(
            timeMin=timeMin,
            timeMax=timeMax,
            timeout=timeout
        )
        read = WindowRead(
            searched=searched,
            everything=(
                searched
                if WHOLE_WINDOW_QUERY in query_strings
                else self._read(
                    query_strings=(WHOLE_WINDOW_QUERY,),
                    timeMin=timeMin,
                    timeMax=timeMax,
                    timeout=timeout
                )
            )
        )

        self.reporter.step_finished()

        return read

    def filter_gcal_items(
            self,
            gcal_shift_data: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """ Remove calendar items that must not become shifts.

            Filtering runs before a title is matched to a category,
            for two reasons.  Matching looks the title up in the shift
            data model, so a cancelled event filtered afterwards logs a
            spurious "no confident match" warning.  And an item without
            a 'dateTime' or a 'summary' has nothing a shift can be
            built from.

            Which items those are is 'exclusion_reason's answer, which
            the collection records against the run.

            Args:
                gcal_shift_data (List[Dict[str, Any]]):
                    Raw Google Calendar items.

            Returns:
                filtered_gcal_items (List[Dict[str, Any]]):
                    The items that can and should become shifts.
        """

        # Display preliminary status message
        self.reporter.step_started(step=STEP_FILTER_EVENTS)

        filtered_gcal_items = []
        for gcal_item in gcal_shift_data:
            reason = exclusion_reason(gcal_item=gcal_item)

            if reason is None:
                filtered_gcal_items.append(gcal_item)
                continue

            # A title the deployment never collects is expected and
            # says nothing worth a line in the log; the other two are
            # events somebody put on the calendar meaning them to
            # become shifts.
            if reason == UNCOLLECTED_UNTITLED:
                message = (
                    'Skipping a Google Calendar event with no title '
                    f'(starting {self._item_start(gcal_item)})'
                )
                logger.warning(message)

            elif reason == UNCOLLECTED_ALL_DAY:
                message = (
                    f'Skipping "{gcal_item["summary"]}" because it has '
                    'no start and end time (an all-day event cannot '
                    'become a shift)'
                )
                logger.warning(message)

        # Display status message
        self.reporter.step_finished()

        return filtered_gcal_items

    @staticmethod
    def _item_start(
            gcal_item: Dict[str, Any]
    ) -> str:
        """ Return a calendar item's start for a log message.

            Args:
                gcal_item (Dict[str, Any]):
                    Raw Google Calendar item.

            Returns:
                str:
                    The item's start dateTime, its all-day date, or
                    'an unknown date' when it has neither.
        """

        start = gcal_item.get('start') or {}

        return (
            start.get('dateTime')
            or start.get('date')
            or 'an unknown date'
        )
