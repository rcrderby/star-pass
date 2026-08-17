#!/usr/local/bin/python3
""" Google Calendar shift management classes and methods. """

# Imports - Python Standard Library
from copy import copy
from os import getenv
from typing import Any, Dict, List, Tuple

# Imports - Local
from . import _defaults
from ._exceptions import ConfigurationError
from ._reporting import Reporter
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

# Module logger
logger = get_logger(__name__)


def _item_times(
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


class GCALData:
    """ Collect and manage Google Calendar data. """
    def __init__(
            self,
            gcal_name: str,
            reporter: Reporter | None = None,
            **kwargs: Any
    ) -> None:
        """ Class initialization method.

            Construction reads nothing and sends no request.  The
            caller chooses the window and asks for the calendar it
            wants: 'get_gcal_shift_data' collects the items in a window
            and 'filter_gcal_items' removes the ones that must not
            become shifts.

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

    def get_gcal_shift_data(  # pylint: disable=too-many-locals
            self,
            timeMin: str,  # pylint: disable=invalid-name
            timeMax: str,  # pylint: disable=invalid-name
            timeout: int = HTTP_TIMEOUT
    ) -> Dict[Any, Any]:
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

            Returns:
                gcal_shift_data (Dict[Any, Any]):
                    Data returned by the Google Calendar service.
        """

        self.reporter.calendar_read_started()

        # Create a list of shifts for Google Calendar data
        gcal_shift_data = []

        # Set HTTP request variables
        method = 'GET'
        headers = BASE_GCAL_HEADERS

        # Set Google Calendar variables
        gcal_id = GCAL_CALENDARS[self.gcal_name].get('gcal_id')
        query_strings = GCAL_CALENDARS[self.gcal_name].get('query_strings')

        # Confirm the Google calendar variables are not None
        if gcal_id is None or query_strings is None:
            # Log an error message and exit
            message = f'Invalid Google Calendar data for "{self.gcal_name}"'
            logger.error(message)
            raise ConfigurationError(message)

        # Construct URL
        url = (
            f'{BASE_GCAL_URL}'
            f'{gcal_id}'
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

    @staticmethod
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

    def filter_gcal_items(
            self,
            gcal_shift_data: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """ Remove calendar items that must not become shifts.

            Filtering runs before the caller matches a title to a
            category, for two reasons:

            1. Matching looks the event title up in the shift data
               model, so a cancelled event filtered afterwards is
               matched first and logs a spurious "no confident match"
               warning on every run.
            2. An item without a 'dateTime' (an all-day event) or
               without a 'summary' (an untitled event) has nothing a
               shift can be built from, and is named here rather than
               failing partway through a collection.

            Args:
                gcal_shift_data (List[Dict[str, Any]]):
                    Raw Google Calendar items.

            Returns:
                filtered_gcal_items (List[Dict[str, Any]]):
                    The items that can and should become shifts.
        """

        # Display preliminary status message
        self.reporter.step_started(
            label='Filtering event data'
        )

        filtered_gcal_items = []
        for gcal_item in gcal_shift_data:

            # An untitled event cannot be matched to a need
            need_name = gcal_item.get('summary')
            if not need_name:
                message = (
                    'Skipping a Google Calendar event with no title '
                    f'(starting {self._item_start(gcal_item)})'
                )
                logger.warning(message)
                continue

            # Cancelled and non-officiated events never become shifts
            if self._is_excluded_title(need_name=need_name) is True:
                continue

            # An all-day event has a 'date' instead of a 'dateTime', so
            # it has no start or end time to build a shift from
            if _item_times(gcal_item=gcal_item) is None:
                message = (
                    f'Skipping "{need_name}" because it has no start and '
                    'end time (an all-day event cannot become a shift)'
                )
                logger.warning(message)
                continue

            filtered_gcal_items.append(gcal_item)

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
