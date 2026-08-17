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
from typing import (
    Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple
)

# Imports - Local
from . import _defaults
from ._helpers import amplify_headers, Helpers, load_env_file
from ._logging import get_logger
from ._progress import Spinner
from ._summary_window import (
    local_now,
    _format_clock,
    _format_day_heading,
    _format_long_date,
    _format_slot_when,
    _response_created_dt,
    _upcoming_shifts,
    _window_end,
    _window_start,
    _window_title
)

# Load environment variables
load_env_file()

# Constants
BASE_AMPLIFY_URL = _defaults.BASE_AMPLIFY_URL
HTTP_TIMEOUT = _defaults.HTTP_TIMEOUT
RESPONSES_HTTP_TIMEOUT = _defaults.AMPLIFY_RESPONSES_TIMEOUT
RESPONSES_SINCE_DAYS = _defaults.AMPLIFY_RESPONSES_SINCE_DAYS
RESPONSES_PER_PAGE = _defaults.AMPLIFY_RESPONSES_PER_PAGE
RESPONSES_MAX_PAGES = _defaults.AMPLIFY_RESPONSES_MAX_PAGES
RESPONSES_SINCE_FORMAT = _defaults.AMPLIFY_RESPONSES_SINCE_FORMAT
RESPONSES_MARGIN_WARN_DAYS = _defaults.AMPLIFY_RESPONSES_MARGIN_WARN_DAYS
AMPLIFY_NEED_DETAIL_URL = _defaults.AMPLIFY_NEED_DETAIL_URL
SUMMARY_DAYS = _defaults.SLACK_SUMMARY_DAYS
SUMMARY_START_IN_DAYS = _defaults.SLACK_SUMMARY_START_IN_DAYS
AMPLIFY_SHIFT_DATETIME_FORMAT = _defaults.AMPLIFY_SHIFT_DATETIME_FORMAT
LOCAL_TIMEZONE = _defaults.LOCAL_TIMEZONE

# Only responses with this status count as a filled slot.
ACTIVE_RESPONSE_STATUS = 'active'

# Module logger
logger = get_logger(__name__)


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


def _build_need_shifts(
        shifts: List[Dict[str, Any]],
        counts: Dict[str, int]
) -> List[Dict[str, Any]]:
    """ Build the per-shift entries for one need in a summary.

        Args:
            shifts (List[Dict[str, Any]]):
                The need's shifts to summarize, in display order.

            counts (Dict[str, int]):
                Active sign-up counts keyed by string shift ID.

        Returns:
            need_shifts (List[Dict[str, Any]]):
                One entry per shift, with 'when' (the time label), 'day'
                (the date heading it belongs under), 'sort_key' (the raw
                start, for ordering across needs), and 'filled'.  A
                shift with no sign-ups reports zero.
    """

    need_shifts = []
    for shift in shifts:
        need_shifts.append(
            {
                'when': _format_slot_when(shift=shift),
                'day': _format_day_heading(shift=shift),
                'sort_key': shift.get('start') or '',
                'filled': counts.get(str(shift.get('id')), 0)
            }
        )

    return need_shifts


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
            'headers': amplify_headers(),
            'json': None,
            'timeout': self.timeout
        }
        response = self.helpers.send_api_request(
            api_request_data=api_request_data,
            display_request_status=False
        )

        return self.helpers.response_json(response).get('data', {})

    def _read_responses_page(
            self,
            since_created: str,
            since_id: Optional[int]
    ) -> List[Dict[str, Any]]:
        """ Read one page of the top-level responses endpoint.

            Args:
                since_created (str):
                    Lower bound for a response's creation datetime.

                since_id (int | None):
                    Page cursor, or None for the first page.

            Returns:
                page (List[Dict[str, Any]]):
                    The page's response objects.
        """

        # Server-side filters: recent, active, one page at a time
        params: Dict[str, Any] = {
            'show_inactive': 'No',
            'per_page': RESPONSES_PER_PAGE,
            'since_created': since_created
        }
        if since_id is not None:
            params['since_id'] = since_id

        response = self.helpers.send_api_request(
            api_request_data={
                'method': 'GET',
                'url': f'{BASE_AMPLIFY_URL}/responses',
                'headers': amplify_headers(),
                'json': None,
                'timeout': RESPONSES_HTTP_TIMEOUT,
                'params': params
            },
            display_request_status=False
        )

        return self.helpers.response_json(response).get('data') or []

    def get_recent_responses(
            self,
            since_created: str,
            need_ids: Optional[Iterable[str | int]] = None,
            progress: Optional[Callable[[str], None]] = None
    ) -> List[Dict[str, Any]]:
        """ Read recent responses through the paged top-level endpoint.

            Pages 'GET /responses' with a 'since_created' lower bound and
            'show_inactive=No', walking pages with the 'since_id' cursor,
            and (when 'need_ids' is given) keeps only those needs' rows.

            The endpoint has no server-side need or shift-date filter, so
            the domain's recent responses are paged and filtered
            client-side; 'since_created' bounds that volume.  The
            alternative -- 'GET /needs/{id}/responses' -- ignores
            pagination entirely and times out for large needs.

            Because the read covers the whole domain, several needs are
            filtered out of one pass rather than one pass per need: the
            paging cost is the same for one need or a dozen.

            Args:
                since_created (str):
                    Lower bound for a response's creation datetime, in
                    'AMPLIFY_RESPONSES_SINCE_FORMAT'.

                need_ids (Iterable[str | int], optional):
                    When given, keep only responses for these needs.

                progress (Callable[[str], None], optional):
                    Called with a status line as each page is read.  The
                    read takes tens of seconds, so a caller attached to
                    a terminal can report where it has got to.

            Returns:
                responses (List[Dict[str, Any]]):
                    Response objects, limited to 'need_ids' when given.
        """

        # Compare as strings: the API returns numeric IDs in some
        # payloads and string IDs in others.
        wanted = (
            {str(need_id) for need_id in need_ids}
            if need_ids is not None
            else None
        )

        collected: List[Dict[str, Any]] = []
        since_id: Optional[int] = None
        pages = 0

        while pages < RESPONSES_MAX_PAGES:
            if progress is not None:
                progress(f'Reading recent sign-ups (page {pages + 1})')

            page = self._read_responses_page(
                since_created=since_created,
                since_id=since_id
            )
            pages += 1

            # Client-side filter: keep only the target needs' rows
            for row in page:
                if (
                    wanted is None
                    or str((row.get('need') or {}).get('id')) in wanted
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

    def _summarize_needs(
            self,
            need_ids: Sequence[str | int],
            counts: Dict[str, int],
            now: datetime,
            window_end: datetime,
            progress: Optional[Callable[[str], None]] = None
    ) -> Tuple[List[Dict[str, Any]], Set[str]]:
        """ Build the per-need entries of a summary.

            Args:
                need_ids (Sequence[str | int]):
                    Amplify need IDs, in display order.

                counts (Dict[str, int]):
                    Active sign-up counts keyed by string shift ID.

                now (datetime):
                    Start of the shift window.

                window_end (datetime):
                    End of the shift window (see '_window_end').

                progress (Callable[[str], None], optional):
                    Called with a status line as each need is read.

            Returns:
                result (Tuple[List[Dict[str, Any]], Set[str]]):
                    The needs that have shifts inside the window, and the
                    string shift IDs those needs contributed.
        """

        summary_needs = []
        upcoming_ids: Set[str] = set()
        total = len(need_ids)

        for number, need_id in enumerate(need_ids, start=1):
            if progress is not None:
                progress(f'Reading opportunity {number} of {total}')

            need = self.get_need(need_id=need_id)
            upcoming = _upcoming_shifts(
                shifts=need.get('shifts', []),
                now=now,
                window_end=window_end
            )

            # A need with nothing in the window contributes no lines and
            # no sign-up button
            if not upcoming:
                continue

            upcoming_ids.update(
                str(shift.get('id')) for shift in upcoming
            )
            summary_needs.append(
                {
                    # Titles are entered by hand in Amplify and carry
                    # stray whitespace; an untrimmed one would split a
                    # group in two and ride into the button text.
                    'title': need.get(
                        'need_title', f'Need {need_id}'
                    ).strip(),
                    'signup_url': (
                        f'{AMPLIFY_NEED_DETAIL_URL}?need_id={need_id}'
                    ),
                    'shifts': _build_need_shifts(
                        shifts=upcoming,
                        counts=counts
                    )
                }
            )

        return (summary_needs, upcoming_ids)

    def build_summary(
            self,
            need_ids: Sequence[str | int],
            title: Optional[str] = None,
            now: Optional[datetime] = None,
            days: Optional[int] = None,
            start_in_days: Optional[int] = None
    ) -> Dict[str, Any]:
        """ Build a sign-up summary covering one or more needs.

            Combines each need's shifts (for timing) with the domain's
            recent responses (for live filled counts) into the structure
            consumed by 'slack_notify.build_summary_blocks'.  Only shifts
            starting between 'now' and the end of the day window are
            included: a long-lived need accumulates hundreds of past
            shifts that a sign-up summary should not repeat, and the
            summary is a call for volunteers over the next day or few
            rather than a full backlog.

            The responses read covers the whole domain and is filtered
            client-side, so it runs ONCE for every need together; only
            the cheap per-need shift read repeats.

            Args:
                need_ids (Sequence[str | int]):
                    Amplify need IDs, in display order.

                title (str, optional):
                    Summary heading.  Defaults to a heading naming the
                    window's date or date range.

                now (datetime, optional):
                    Reference time for the shift window, the
                    'since_created' window, and the 'as_of' stamp.
                    Defaults to the current local time.

                start_in_days (int, optional):
                    Days between 'now' and the window's first day.  Zero
                    starts today; one starts tomorrow, which leaves out
                    the day a notice is posted.  Defaults to
                    'SLACK_SUMMARY_START_IN_DAYS'.

                days (int, optional):
                    Number of calendar days the summary covers, counting
                    today as day one.  Defaults to
                    'SLACK_SUMMARY_DAYS'.

            Raises:
                ValueError:
                    If 'days' is less than one, or 'need_ids' is empty.

            Returns:
                summary (Dict[str, Any]):
                    A summary with 'title', 'as_of', and 'needs' (each
                    with 'title', 'signup_url', and 'shifts').  Needs
                    with no shifts inside the window are omitted, so an
                    empty 'needs' list means nothing is scheduled.
        """

        if not need_ids:
            raise ValueError('At least one need ID is required.')

        if now is None:
            now = local_now()

        if days is None:
            days = SUMMARY_DAYS

        if start_in_days is None:
            start_in_days = SUMMARY_START_IN_DAYS

        # The shift window: from its first instant through the end of
        # its final day
        window_start = _window_start(
            now=now,
            start_in_days=start_in_days
        )
        window_end = _window_end(
            now=window_start,
            days=days
        )

        # The server-side window bounding the responses read
        cutoff = now - timedelta(days=self.since_days)
        since_created = cutoff.strftime(RESPONSES_SINCE_FORMAT)

        # Most of a run is spent waiting on these reads, so report
        # progress while they happen.  The spinner is a no-op unless
        # stderr is a terminal.
        with Spinner(message='Reading recent sign-ups') as spinner:
            # One responses read serves every need: the endpoint has no
            # server-side need filter, so paging per need would refetch
            # the same domain-wide rows once per need.
            responses = self.get_recent_responses(
                since_created=since_created,
                need_ids=need_ids,
                progress=spinner.update
            )
            counts = count_signups_by_shift(responses=responses)

            summary_needs, upcoming_ids = self._summarize_needs(
                need_ids=need_ids,
                counts=counts,
                now=window_start,
                window_end=window_end,
                progress=spinner.update
            )

        # Warn when the counts sit close to the window edge
        self._log_window_margin(
            responses=responses,
            upcoming_ids=upcoming_ids,
            cutoff=cutoff
        )

        return {
            'title': title or _window_title(
                now=window_start,
                window_end=window_end
            ),
            'as_of': (
                f'{_format_clock(value=now)} on '
                f'{_format_long_date(value=now)}'
            ),
            # A single-day summary needs no date headings: the title
            # already names the day they would repeat.
            'multi_day': days > 1,
            'needs': summary_needs
        }
