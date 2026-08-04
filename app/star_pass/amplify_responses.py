#!/usr/local/bin/python3
""" Amplify response (sign-up) reader classes and methods.

    Reads volunteer responses for an Amplify need and produces the
    sign-up summary structure consumed by
    star_pass.slack_notify.build_summary_blocks.

    The per-need endpoint (GET /needs/{id}/responses) cannot be paged or
    filtered -- it returns a need's entire response history in one slow
    response and times out (504) for large, long-lived needs.  Instead,
    this module reads the top-level GET /responses endpoint, which honors
    pagination, with a 'since_created' window to bound the volume, and
    filters the results to the target need client-side.  Only shifts that
    start in the future are summarized.
"""

# Imports - Python Standard Library
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set

# Imports - Local
from . import _defaults
from ._helpers import Helpers, load_env_file
from ._logging import get_logger
from .amplify_shifts import BASE_AMPLIFY_HEADERS, BASE_AMPLIFY_URL

# Load environment variables
load_env_file()

# Constants
HTTP_TIMEOUT = _defaults.HTTP_TIMEOUT
RESPONSES_HTTP_TIMEOUT = _defaults.AMPLIFY_RESPONSES_TIMEOUT
RESPONSES_SINCE_DAYS = _defaults.AMPLIFY_RESPONSES_SINCE_DAYS
RESPONSES_PER_PAGE = _defaults.AMPLIFY_RESPONSES_PER_PAGE
RESPONSES_MAX_PAGES = _defaults.AMPLIFY_RESPONSES_MAX_PAGES
RESPONSES_SINCE_FORMAT = _defaults.AMPLIFY_RESPONSES_SINCE_FORMAT
RESPONSES_MARGIN_WARN_DAYS = _defaults.AMPLIFY_RESPONSES_MARGIN_WARN_DAYS
AMPLIFY_NEED_DETAIL_URL = _defaults.AMPLIFY_NEED_DETAIL_URL
SUMMARY_DAYS = _defaults.SLACK_SUMMARY_DAYS
AMPLIFY_SHIFT_DATETIME_FORMAT = _defaults.AMPLIFY_SHIFT_DATETIME_FORMAT
SIMPLE_DATE_FORMAT = _defaults.SIMPLE_DATE_FORMAT
SIMPLE_TIME_FORMAT = _defaults.SIMPLE_TIME_FORMAT

# Only responses with this status count as a filled slot.
ACTIVE_RESPONSE_STATUS = 'active'

# Module logger
logger = get_logger(__name__)


def _parse_amplify_dt(
        value: Any
) -> Optional[datetime]:
    """ Parse an Amplify datetime string, tolerating absent seconds.

        Args:
            value (Any):
                A datetime string (a shift 'start'/'end' or a response
                'created_at'/'response_date_added'), or None.

        Returns:
            parsed (datetime | None):
                The parsed datetime, or None when 'value' is missing or
                cannot be parsed.
    """

    for date_format in (AMPLIFY_SHIFT_DATETIME_FORMAT, '%Y-%m-%d %H:%M'):
        try:
            return datetime.strptime(value, date_format)
        except (TypeError, ValueError):
            continue

    return None


def _shift_start_dt(
        shift: Dict[str, Any]
) -> Optional[datetime]:
    """ Return a shift's start as a datetime, or None when unparseable.

        Args:
            shift (Dict[str, Any]):
                Shift object with a 'start' datetime string.

        Returns:
            start (datetime | None):
                The parsed start datetime, or None.
    """

    return _parse_amplify_dt((shift or {}).get('start'))


def _response_created_dt(
        response: Dict[str, Any]
) -> Optional[datetime]:
    """ Return a response's creation datetime, or None.

        The live API returns 'created_at'; the documented schema names
        this field 'response_date_added'.  Either is accepted.

        Args:
            response (Dict[str, Any]):
                An Amplify response object.

        Returns:
            created (datetime | None):
                The parsed creation datetime, or None.
    """

    raw = response.get('created_at') or response.get('response_date_added')

    return _parse_amplify_dt(raw)


def _max_numeric_id(
        rows: List[Dict[str, Any]]
) -> Optional[int]:
    """ Return the largest numeric 'id' among rows, for the page cursor.

        Args:
            rows (List[Dict[str, Any]]):
                Response objects, each with an 'id'.

        Returns:
            max_id (int | None):
                The largest integer 'id', or None when none are numeric.
    """

    ids = [
        int(row['id'])
        for row in rows
        if str(row.get('id', '')).isdigit()
    ]

    return max(ids) if ids else None


def _window_end(
        now: datetime,
        days: int
) -> datetime:
    """ Return the last instant of a summary window.

        The window counts today as day one, so 'days=1' ends at the last
        instant of today and 'days=2' ends at the last instant of
        tomorrow.

        Args:
            now (datetime):
                Reference time; its calendar date is day one.

            days (int):
                Number of calendar days to cover, one or greater.

        Raises:
            ValueError:
                If 'days' is less than one.

        Returns:
            window_end (datetime):
                The last instant of the final day in the window.
    """

    if days < 1:
        raise ValueError(
            f'Summary window must cover at least one day, got {days}.'
        )

    last_day = now + timedelta(days=days - 1)

    return last_day.replace(
        hour=23,
        minute=59,
        second=59,
        microsecond=999999
    )


def _upcoming_shifts(
        shifts: List[Dict[str, Any]],
        now: datetime,
        window_end: datetime
) -> List[Dict[str, Any]]:
    """ Select the shifts starting inside the window, ordered by start.

        A long-lived need accumulates hundreds of past shifts that a
        sign-up summary should not repeat, and a summary is a call for
        volunteers over the next day or few, not a full backlog.  Shifts
        that already started are excluded, as are shifts with an
        unparseable start.

        Args:
            shifts (List[Dict[str, Any]]):
                Shift objects from a need.

            now (datetime):
                Start of the window; shifts before this are past.

            window_end (datetime):
                End of the window (see '_window_end').

        Returns:
            upcoming (List[Dict[str, Any]]):
                The shifts inside the window, earliest first.
    """

    dated = []
    for shift in shifts:
        start_dt = _shift_start_dt(shift=shift)
        if start_dt is not None and now <= start_dt <= window_end:
            dated.append((start_dt, shift))
    dated.sort(key=lambda pair: pair[0])

    return [shift for _start_dt, shift in dated]


def _window_title(
        now: datetime,
        window_end: datetime
) -> str:
    """ Build a default summary title describing the window.

        Args:
            now (datetime):
                Start of the window.

            window_end (datetime):
                End of the window (see '_window_end').

        Returns:
            title (str):
                A title naming the window's date, or its date range when
                the window covers more than one day.
    """

    start_label = now.strftime(SIMPLE_DATE_FORMAT)
    end_label = window_end.strftime(SIMPLE_DATE_FORMAT)

    if start_label == end_label:
        return f'Shift sign-ups for {start_label}'

    return f'Shift sign-ups for {start_label} - {end_label}'


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
    start_dt = _parse_amplify_dt(start_raw)
    end_dt = _parse_amplify_dt(end_raw)
    if start_dt is None or end_dt is None:
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


def _build_summary_shifts(
        shifts: List[Dict[str, Any]],
        counts: Dict[str, int],
        signup_url: str
) -> List[Dict[str, Any]]:
    """ Build the per-shift entries of a sign-up summary.

        Args:
            shifts (List[Dict[str, Any]]):
                The shifts to summarize, in display order.

            counts (Dict[str, int]):
                Active sign-up counts keyed by string shift ID.

            signup_url (str):
                Public sign-up link attached to every shift.

        Returns:
            summary_shifts (List[Dict[str, Any]]):
                One entry per shift, with 'name', 'start', 'end',
                'filled', 'slots', and 'signup_url'.  A shift with no
                sign-ups is reported as zero filled.
    """

    summary_shifts = []
    for shift in shifts:
        when = _format_shift_when(shift=shift)
        summary_shifts.append(
            {
                'name': when['name'],
                'start': when['start'],
                'end': when['end'],
                'filled': counts.get(str(shift.get('id')), 0),
                'slots': shift.get('slots'),
                'signup_url': signup_url
            }
        )

    return summary_shifts


def count_signups_by_shift(
        responses: List[Dict[str, Any]]
) -> Dict[str, int]:
    """ Count active sign-ups per shift ID.

        Args:
            responses (List[Dict[str, Any]]):
                Amplify response objects, each with a nested 'shift' and
                a 'response_status'.

        Returns:
            counts (Dict[str, int]):
                Mapping of shift ID (as a string) to the number of active
                responses.  Inactive responses and responses without a
                shift ID are ignored.
    """

    counts: Dict[str, int] = {}

    for response in responses:
        # Only active responses fill a slot
        if response.get('response_status') != ACTIVE_RESPONSE_STATUS:
            continue

        shift = response.get('shift') or {}
        shift_id = shift.get('id')
        if shift_id is None:
            continue

        # Key on a string so lookups match the summary's shift IDs
        # regardless of whether the API returns numbers or strings.
        key = str(shift_id)
        counts[key] = counts.get(key, 0) + 1

    return counts


class AmplifyResponses:
    """ Read Amplify response (sign-up) data for a need. """

    def __init__(
            self,
            timeout: int = HTTP_TIMEOUT,
            since_days: int = RESPONSES_SINCE_DAYS
    ) -> None:
        """ Class initialization method.

            Args:
                timeout (int, optional):
                    HTTP timeout for the need read.  Default is
                    'HTTP_TIMEOUT'.

                since_days (int, optional):
                    The 'since_created' look-back window, in days, for
                    the responses read.  Default is
                    'AMPLIFY_RESPONSES_SINCE_DAYS'.

            Returns:
                None.
        """

        # Initialize helper methods
        self.helpers = Helpers()
        self.timeout = timeout
        self.since_days = since_days

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

        return self.helpers.response_json(response).get('data', {})

    def get_recent_responses(
            self,
            since_created: str,
            need_id: Optional[str | int] = None
    ) -> List[Dict[str, Any]]:
        """ Read recent responses through the paged top-level endpoint.

            Pages 'GET /responses' with a 'since_created' lower bound and
            'show_inactive=No', walking pages with the 'since_id' cursor,
            and (when 'need_id' is given) keeps only that need's rows.

            The endpoint has no server-side need or shift-date filter, so
            the domain's recent responses are paged and filtered
            client-side; 'since_created' bounds that volume.  The
            alternative -- 'GET /needs/{id}/responses' -- ignores
            pagination entirely and times out for large needs.

            Args:
                since_created (str):
                    Lower bound for a response's creation datetime, in
                    'AMPLIFY_RESPONSES_SINCE_FORMAT'.

                need_id (str | int, optional):
                    When given, keep only responses for this need.

            Returns:
                responses (List[Dict[str, Any]]):
                    Response objects, limited to 'need_id' when given.
        """

        url = f'{BASE_AMPLIFY_URL}/responses'
        collected: List[Dict[str, Any]] = []
        since_id: Optional[int] = None
        pages = 0

        while pages < RESPONSES_MAX_PAGES:
            # Server-side filters: recent, active, one page at a time
            params: Dict[str, Any] = {
                'show_inactive': 'No',
                'per_page': RESPONSES_PER_PAGE,
                'since_created': since_created
            }
            if since_id is not None:
                params['since_id'] = since_id

            api_request_data = {
                'method': 'GET',
                'url': url,
                'headers': BASE_AMPLIFY_HEADERS,
                'json': None,
                'timeout': RESPONSES_HTTP_TIMEOUT,
                'params': params
            }
            response = self.helpers.send_api_request(
                api_request_data=api_request_data,
                display_request_status=False
            )
            page = self.helpers.response_json(response).get('data') or []
            pages += 1

            # Client-side filter: keep only the target need's rows
            for row in page:
                if (
                    need_id is None
                    or str((row.get('need') or {}).get('id')) == str(need_id)
                ):
                    collected.append(row)

            # A short page is the last page
            if len(page) < RESPONSES_PER_PAGE:
                break

            # Advance the cursor, stopping if it cannot move forward
            next_id = _max_numeric_id(rows=page)
            if next_id is None or next_id == since_id:
                message = (
                    f'Could not advance the responses cursor after {pages} '
                    'page(s); returning the responses collected so far.'
                )
                logger.warning(message)
                break

            since_id = next_id

        else:
            message = (
                f'Reached the responses page limit ({RESPONSES_MAX_PAGES}); '
                'results may be incomplete.  Narrow the window with '
                'AMPLIFY_RESPONSES_SINCE_DAYS.'
            )
            logger.warning(message)

        return collected

    def _log_window_margin(
            self,
            responses: List[Dict[str, Any]],
            upcoming_ids: Set[str],
            cutoff: datetime
    ) -> None:
        """ Log how close the counted sign-ups sit to the window edge.

            The 'since_created' window filters on when a sign-up record
            was created, not on when its shift occurs, so a sign-up made
            before the cutoff would be missed.  When the oldest counted
            sign-up was created only just after the cutoff, that margin is
            thin and the window should widen; otherwise the margin is
            logged for reassurance.

            Args:
                responses (List[Dict[str, Any]]):
                    The fetched (need-filtered) responses.

                upcoming_ids (Set[str]):
                    String shift IDs of the summarized upcoming shifts.

                cutoff (datetime):
                    The 'since_created' lower bound.

            Returns:
                None.
        """

        # Creation times of the sign-ups that produced the shown counts
        created_times = []
        for response in responses:
            if response.get('response_status') != ACTIVE_RESPONSE_STATUS:
                continue
            shift_id = str((response.get('shift') or {}).get('id'))
            if shift_id not in upcoming_ids:
                continue
            created = _response_created_dt(response=response)
            if created is not None:
                created_times.append(created)

        if not created_times:
            return None

        oldest = min(created_times)
        margin_days = (oldest - cutoff).total_seconds() / 86400
        oldest_display = oldest.strftime(AMPLIFY_SHIFT_DATETIME_FORMAT)

        if margin_days < RESPONSES_MARGIN_WARN_DAYS:
            message = (
                f'The oldest counted sign-up ({oldest_display}) was created '
                f'{margin_days:.1f} day(s) after the since_created cutoff '
                f'({cutoff.strftime(AMPLIFY_SHIFT_DATETIME_FORMAT)}).  '
                'Increase AMPLIFY_RESPONSES_SINCE_DAYS (currently '
                f'{self.since_days}) if sign-ups may predate this window.'
            )
            logger.warning(message)
        else:
            message = (
                f'Sign-up window margin is healthy: the oldest counted '
                f'sign-up ({oldest_display}) is {margin_days:.1f} day(s) '
                f'inside the {self.since_days}-day window.'
            )
            logger.info(message)

        return None

    def build_need_summary(
            self,
            need_id: str | int,
            title: Optional[str] = None,
            now: Optional[datetime] = None,
            days: Optional[int] = None
    ) -> Dict[str, Any]:
        """ Build a sign-up summary for a need's upcoming shifts.

            Combines the need's upcoming shifts (for capacity and timing)
            with its recent responses (for live filled counts) into the
            structure consumed by 'slack_notify.build_summary_blocks'.
            Only shifts starting between 'now' and the end of the day
            window are included: a long-lived need accumulates hundreds
            of past shifts that a sign-up summary should not repeat, and
            the summary is a call for volunteers over the next day or
            few rather than a full backlog.

            Args:
                need_id (str | int):
                    Amplify need ID.

                title (str, optional):
                    Summary heading.  Defaults to a heading naming the
                    window's date or date range.

                now (datetime, optional):
                    Reference time for the shift window, the
                    'since_created' window, and the 'as_of' stamp.
                    Defaults to the current local time.

                days (int, optional):
                    Number of calendar days the summary covers, counting
                    today as day one.  Defaults to
                    'SLACK_SUMMARY_DAYS'.

            Raises:
                ValueError:
                    If 'days' is less than one.

            Returns:
                summary (Dict[str, Any]):
                    A summary with 'title', 'as_of', and 'shifts' (each
                    with 'name', 'start', 'end', 'filled', 'slots', and
                    'signup_url'), ordered by start time.  The 'shifts'
                    list is empty when nothing falls inside the window.
        """

        if now is None:
            now = datetime.now()

        if days is None:
            days = SUMMARY_DAYS

        # The shift window: from now through the end of its final day
        window_end = _window_end(
            now=now,
            days=days
        )

        # The server-side window bounding the responses read
        cutoff = now - timedelta(days=self.since_days)
        since_created = cutoff.strftime(RESPONSES_SINCE_FORMAT)

        # Read the need (shifts) and its recent responses (sign-ups)
        need = self.get_need(need_id=need_id)
        responses = self.get_recent_responses(
            since_created=since_created,
            need_id=need_id
        )
        counts = count_signups_by_shift(responses=responses)

        # Keep only shifts starting inside the window, ordered by start
        upcoming = _upcoming_shifts(
            shifts=need.get('shifts', []),
            now=now,
            window_end=window_end
        )

        # Warn when the counts sit close to the window edge
        self._log_window_margin(
            responses=responses,
            upcoming_ids={str(shift.get('id')) for shift in upcoming},
            cutoff=cutoff
        )

        as_of_format = f'{SIMPLE_DATE_FORMAT} {SIMPLE_TIME_FORMAT}'

        return {
            'title': title or _window_title(
                now=now,
                window_end=window_end
            ),
            'as_of': now.strftime(as_of_format),
            'shifts': _build_summary_shifts(
                shifts=upcoming,
                counts=counts,
                signup_url=f'{AMPLIFY_NEED_DETAIL_URL}?need_id={need_id}'
            )
        }
