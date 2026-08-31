#!/usr/bin/env python3
""" Reading an Amplify opportunity, where it is published, and what it holds.

    Below every caller.  Collection resolves an opportunity's title
    once and stores it on the run, because every review row is
    labelled with one; the shift preview reads the same title while
    reporting what it would create.

    The shifts an opportunity already holds are read here too.  The
    preview says which of a revision's shifts Amplify already has, and
    the send re-asks inside its own transaction so that nothing
    created between the two is sent twice.  Both are the same
    question, asked one way.

    The address is built rather than read: it is the public page a
    volunteer signs up on, which the API's own response does not
    carry, and it is one configured base plus the need ID.
"""

# Imports - Python Standard Library
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, Optional, Sequence, Set

# Imports - Local
from . import _defaults
from ._helpers import amplify_headers, Helpers, parse_amplify_datetime
from ._logging import get_logger
from ._records import Event, ShiftIdentity

# Constants
AMPLIFY_NEED_DETAIL_URL = _defaults.AMPLIFY_NEED_DETAIL_URL
BASE_AMPLIFY_URL = _defaults.BASE_AMPLIFY_URL
HTTP_TIMEOUT = _defaults.HTTP_TIMEOUT
ISO_DATE_FORMAT = _defaults.ISO_DATE_FORMAT
SIMPLE_TIME_FORMAT = _defaults.SIMPLE_TIME_FORMAT

# What an opportunity is called when Amplify answers without a title.
# Named rather than left empty: a row labelled with nothing reads as a
# rendering fault, and this reads as what it is.
UNKNOWN_TITLE = 'Unknown'

# Where a need's own shifts are in what Amplify answers with.
SHIFTS_KEY = 'shifts'

# Module logger
logger = get_logger(__name__)


def read_need(
        helpers: Helpers,
        need_id: str | int,
        timeout: int = HTTP_TIMEOUT
) -> Dict[str, Any]:
    """ Return what Amplify holds about one opportunity.

        One request, whether the caller wants the title or the shifts.
        Two functions each making their own would read the opportunity
        twice while collecting and previewing the same run, and could
        be answered at two different moments.

        Args:
            helpers (Helpers):
                What the request is sent through.

            need_id (str | int):
                Amplify need ID to look up.

            timeout (int, optional):
                HTTP timeout.  Defaults to the configured value.

        Raises:
            UpstreamError:
                If Amplify cannot be reached or refuses the request.

        Returns:
            need (Dict[str, Any]):
                The opportunity, as Amplify describes it, or an empty
                mapping when the answer carries no description of one.
    """

    response = helpers.send_api_request(
        api_request_data={
            'method': 'GET',
            'url': f'{BASE_AMPLIFY_URL}/needs/{need_id}',
            'headers': amplify_headers(),
            'json': None,
            'timeout': timeout
        },
        display_request_status=False
    )

    # Guarding a body that is not JSON and an answer with no 'data'.
    return helpers.response_json(response).get('data', {})


def title_of(
        need: Dict[str, Any]
) -> str:
    """ Return what Amplify calls an opportunity it has described.

        Args:
            need (Dict[str, Any]):
                An opportunity, as 'read_need' returns one.

        Returns:
            title (str):
                The opportunity's title, or 'UNKNOWN_TITLE' when the
                answer carries none.
    """

    return need.get('need_title', UNKNOWN_TITLE)


def _ends_at(
        shift: Dict[str, Any],
        started: datetime
) -> Optional[datetime]:
    """ Return when one of Amplify's shifts ends.

        Amplify answers with both an end and the duration the shift was
        created with, and the duration is the field star-pass sends, so
        it is the one that is certainly there.  The end is preferred
        anyway, because it is what Amplify itself says; the duration is
        what the answer is worked out from when the end cannot be read.

        Args:
            shift (Dict[str, Any]):
                One of an opportunity's shifts.

            started (datetime):
                When it starts, already read.

        Returns:
            ends (datetime | None):
                When it ends, or None when neither field says.
    """

    ends = parse_amplify_datetime(shift.get('end'))

    if ends is not None:
        return ends

    try:
        return started + timedelta(minutes=int(shift.get('duration')))

    except (TypeError, ValueError):
        return None


def _identity(
        need_id: str,
        shift: Dict[str, Any]
) -> Optional[ShiftIdentity]:
    """ Return one of Amplify's shifts as a row identity, if it is one.

        Two shifts are reported as absent rather than matched.  One
        that runs past midnight cannot be a shift this tool created:
        collection refuses to store one, because an event holds times
        of day and a shift crossing midnight cannot be read back as the
        one that was stored.  One whose times cannot be read at all is
        the other, and it is logged, because it is the only case where
        a row that does exist could be counted as absent.

        Args:
            need_id (str):
                Opportunity the shift belongs to.

            shift (Dict[str, Any]):
                One of its shifts, as Amplify describes it.

        Returns:
            identity (ShiftIdentity | None):
                Need ID, date, start and end, or None when the shift is
                not one this tool could have created.
    """

    starts = parse_amplify_datetime(shift.get('start'))
    ends = (
        _ends_at(shift=shift, started=starts)
        if starts is not None
        else None
    )

    if ends is None:
        message = (
            f'Opportunity {need_id} holds a shift whose times cannot '
            f'be read: {shift.get("start")!r} to {shift.get("end")!r}. '
            'It is not counted as one this run already sent.'
        )
        logger.warning(message)

        return None

    if starts.date() != ends.date():
        return None

    return (
        str(need_id),
        starts.strftime(ISO_DATE_FORMAT),
        starts.strftime(SIMPLE_TIME_FORMAT),
        ends.strftime(SIMPLE_TIME_FORMAT)
    )


def shifts_in(
        need_id: str | int,
        need: Dict[str, Any]
) -> Set[ShiftIdentity]:
    """ Return the shifts an opportunity already holds.

        Amplify is the authority on this, and no local record can
        replace it: a shift created by an earlier run, by another
        deployment or by hand appears in no run's sent record, and
        creating it again is a duplicate a volunteer sees.

        Args:
            need_id (str | int):
                Amplify need ID the shifts belong to.

            need (Dict[str, Any]):
                The opportunity, as 'read_need' returns one.

        Returns:
            identities (Set[ShiftIdentity]):
                Every shift the opportunity holds that this tool could
                have created, by need ID, date, start and end.
    """

    found = {
        _identity(need_id=str(need_id), shift=shift)
        for shift in need.get(SHIFTS_KEY) or ()
    }

    return {identity for identity in found if identity is not None}


def need_ids_in(
        events: Iterable[Event]
) -> Sequence[str]:
    """ Return the opportunities a revision's events would send to.

        The events rather than the run's stored opportunities: an
        opportunity nothing is sent to is one nobody has to be asked
        about, and asking would be a request per opportunity a reviewer
        removed the last event from.

        Args:
            events (Iterable[Event]):
                The revision's events.

        Returns:
            need_ids (Sequence[str]):
                The need IDs the events name, in order, without
                repeats.
    """

    ordered: Dict[str, None] = {}

    for event in events:
        for role in event.roles:
            ordered.setdefault(role.need_id, None)

    return tuple(ordered)


def shifts_in_amplify(
        events: Iterable[Event],
        helpers: Optional[Helpers] = None,
        timeout: int = HTTP_TIMEOUT
) -> Set[ShiftIdentity]:
    """ Return which of a revision's shifts Amplify already holds.

        What the preview reports and what the send skips, asked the one
        way.

        Args:
            events (Iterable[Event]):
                The revision's events, which name the opportunities to
                ask about.

            helpers (Helpers, optional):
                What the requests are sent through.  Defaults to None,
                which builds one.

            timeout (int, optional):
                HTTP timeout per request.  Defaults to the configured
                value.

        Raises:
            UpstreamError:
                If an opportunity cannot be read.  Reported rather than
                treated as an empty answer: a read that failed says
                nothing about what Amplify holds, and sending on that
                basis would create every shift again.

        Returns:
            identities (Set[ShiftIdentity]):
                Every shift those opportunities already hold.
    """

    reading = helpers if helpers is not None else Helpers()
    found: Set[ShiftIdentity] = set()

    for need_id in need_ids_in(events=events):
        found |= shifts_in(
            need_id=need_id,
            need=read_need(
                helpers=reading,
                need_id=need_id,
                timeout=timeout
            )
        )

    return found


def public_url(
        need_id: str | int
) -> str:
    """ Return where an opportunity is published.

        Args:
            need_id (str | int):
                Amplify need ID.

        Returns:
            url (str):
                The page a volunteer signs up on.
    """

    return f'{AMPLIFY_NEED_DETAIL_URL}{need_id}'
