#!/usr/local/bin/python3
""" Amplify response (sign-up) reader classes and methods.

    Reads volunteer responses for an Amplify need and produces the
    sign-up summary structure consumed by
    star_pass.slack_notify.build_summary_blocks.
"""

# Imports - Python Standard Library
from datetime import datetime
from typing import Any, Dict, List, Optional

# Imports - Local
from . import _defaults
from ._helpers import Helpers, load_env_file
from ._logging import get_logger
from .amplify_shifts import BASE_AMPLIFY_HEADERS, BASE_AMPLIFY_URL

# Load environment variables
load_env_file()

# Constants
HTTP_TIMEOUT = _defaults.HTTP_TIMEOUT
AMPLIFY_NEED_DETAIL_URL = _defaults.AMPLIFY_NEED_DETAIL_URL
AMPLIFY_RESPONSES_PER_PAGE = _defaults.AMPLIFY_RESPONSES_PER_PAGE
AMPLIFY_SHIFT_DATETIME_FORMAT = _defaults.AMPLIFY_SHIFT_DATETIME_FORMAT
SIMPLE_DATE_FORMAT = _defaults.SIMPLE_DATE_FORMAT
SIMPLE_TIME_FORMAT = _defaults.SIMPLE_TIME_FORMAT

# Only responses with this status count as a filled slot.
ACTIVE_RESPONSE_STATUS = 'active'
# Safety cap so an endpoint that ignores pagination cannot loop forever.
MAX_RESPONSE_PAGES = 100

# Module logger
logger = get_logger(__name__)


def _format_shift_when(
        shift: Dict[str, Any]
) -> Dict[str, Any]:
    """ Format a shift's date and time window for display.

        Args:
            shift (Dict[str, Any]):
                Shift object with 'start' and 'end' datetime strings in
                'AMPLIFY_SHIFT_DATETIME_FORMAT'.

        Returns:
            when (Dict[str, Any]):
                A dictionary with 'name' (formatted date), 'start', and
                'end' (formatted times).  When parsing fails the raw
                values are returned unchanged.
    """

    start_raw = shift.get('start')
    end_raw = shift.get('end')

    # Fall back to the raw values when either datetime cannot be parsed
    try:
        start_dt = datetime.strptime(
            start_raw, AMPLIFY_SHIFT_DATETIME_FORMAT
        )
        end_dt = datetime.strptime(
            end_raw, AMPLIFY_SHIFT_DATETIME_FORMAT
        )
    except (TypeError, ValueError):
        return {
            'name': start_raw or 'Shift',
            'start': start_raw,
            'end': end_raw
        }

    return {
        'name': start_dt.strftime(SIMPLE_DATE_FORMAT),
        'start': start_dt.strftime(SIMPLE_TIME_FORMAT),
        'end': end_dt.strftime(SIMPLE_TIME_FORMAT)
    }


def count_signups_by_shift(
        responses: List[Dict[str, Any]]
) -> Dict[Any, int]:
    """ Count active sign-ups per shift ID.

        Args:
            responses (List[Dict[str, Any]]):
                Amplify response objects, each with a nested 'shift' and
                a 'response_status'.

        Returns:
            counts (Dict[Any, int]):
                Mapping of shift ID to the number of active responses.
                Inactive responses and responses without a shift ID are
                ignored.
    """

    counts: Dict[Any, int] = {}

    for response in responses:
        # Only active responses fill a slot
        if response.get('response_status') != ACTIVE_RESPONSE_STATUS:
            continue

        shift = response.get('shift') or {}
        shift_id = shift.get('id')
        if shift_id is None:
            continue

        counts[shift_id] = counts.get(shift_id, 0) + 1

    return counts


class AmplifyResponses:
    """ Read Amplify response (sign-up) data for a need. """

    def __init__(
            self,
            timeout: int = HTTP_TIMEOUT
    ) -> None:
        """ Class initialization method.

            Args:
                timeout (int, optional):
                    HTTP timeout.  Default is HTTP_TIMEOUT.

            Returns:
                None.
        """

        # Initialize helper methods
        self.helpers = Helpers()
        self.timeout = timeout

        return None

    def get_need(
            self,
            need_id: str | int
    ) -> Dict[str, Any]:
        """ Read a single Amplify need.

            Args:
                need_id (str | int):
                    Amplify need ID.

            Returns:
                need (Dict[str, Any]):
                    The need object ('data'), including its 'shifts'.
        """

        # Construct and send the request
        url = f'{BASE_AMPLIFY_URL}/needs/{need_id}'
        api_request_data = {
            'method': 'GET',
            'url': url,
            'headers': BASE_AMPLIFY_HEADERS,
            'json': None,
            'timeout': self.timeout
        }
        response = self.helpers.send_api_request(
            api_request_data=api_request_data,
            display_request_status=False
        )

        return response.json().get('data', {})

    def get_need_responses(
            self,
            need_id: str | int
    ) -> List[Dict[str, Any]]:
        """ Read every response (sign-up) for a need.

            Follows pagination: authoritative 'meta.last_page' when the
            API provides it, otherwise stops once a short page arrives.
            A hard page cap ('MAX_RESPONSE_PAGES') guards against an
            endpoint that ignores the pagination parameters.

            Args:
                need_id (str | int):
                    Amplify need ID.

            Returns:
                responses (List[Dict[str, Any]]):
                    All response objects for the need.
        """

        url = f'{BASE_AMPLIFY_URL}/needs/{need_id}/responses'
        responses: List[Dict[str, Any]] = []
        page = 1

        while page <= MAX_RESPONSE_PAGES:

            # Construct and send the request for the current page
            api_request_data = {
                'method': 'GET',
                'url': url,
                'headers': BASE_AMPLIFY_HEADERS,
                'params': {
                    'per_page': AMPLIFY_RESPONSES_PER_PAGE,
                    'page': page
                },
                'timeout': self.timeout
            }
            response = self.helpers.send_api_request(
                api_request_data=api_request_data,
                display_request_status=False
            )
            response_json = response.json()

            # Accumulate this page's results
            data = response_json.get('data') or []
            responses += data

            # Prefer authoritative pagination metadata when present;
            # otherwise stop once a short (or empty) page arrives.
            meta = response_json.get('meta') or {}
            last_page = meta.get('last_page')
            if last_page is not None:
                if page >= int(last_page):
                    break
            elif len(data) < AMPLIFY_RESPONSES_PER_PAGE:
                break

            page += 1

        return responses

    def build_need_summary(
            self,
            need_id: str | int,
            title: Optional[str] = None
    ) -> Dict[str, Any]:
        """ Build a sign-up summary for a need.

            Combines the need's shifts (for capacity and timing) with
            its responses (for live filled counts) into the structure
            consumed by 'slack_notify.build_summary_blocks'.

            Args:
                need_id (str | int):
                    Amplify need ID.

                title (str, optional):
                    Summary heading.  Defaults to the need title.

            Returns:
                summary (Dict[str, Any]):
                    A summary with 'title', 'as_of', and 'shifts' (each
                    with 'name', 'start', 'end', 'filled', 'slots', and
                    'signup_url').
        """

        # Read the need (shifts) and its responses (sign-ups)
        need = self.get_need(need_id=need_id)
        responses = self.get_need_responses(need_id=need_id)
        counts = count_signups_by_shift(responses=responses)

        # Public sign-up link for this need
        signup_url = f'{AMPLIFY_NEED_DETAIL_URL}?need_id={need_id}'
        summary_title = title or need.get('need_title', 'Sign-Ups')

        # One summary entry per shift, defaulting empty shifts to zero
        summary_shifts = []
        for shift in need.get('shifts', []):
            when = _format_shift_when(shift=shift)
            summary_shifts.append(
                {
                    'name': when['name'],
                    'start': when['start'],
                    'end': when['end'],
                    'filled': counts.get(shift.get('id'), 0),
                    'slots': shift.get('slots'),
                    'signup_url': signup_url
                }
            )

        # Timestamp the summary was generated
        as_of_format = f'{SIMPLE_DATE_FORMAT} {SIMPLE_TIME_FORMAT}'
        as_of = datetime.now().strftime(as_of_format)

        return {
            'title': summary_title,
            'as_of': as_of,
            'shifts': summary_shifts
        }
