#!/usr/bin/env python3
""" Putting a revision's shifts into Amplify.

    The only thing star-pass does that cannot be undone.  Amplify has
    no way to take a shift back, so everything here is arranged around
    one question: does this row already exist?

    **One request per opportunity, not per shift.**  Amplify's create
    endpoint takes an array, and a month is on the order of a hundred
    shifts across a handful of opportunities.  Idempotency is
    unaffected: the record is per shift, keyed by the run and the four
    columns a row is identified by, and so is the decision to skip.

    **A batch cannot record a partial success.**  A request whose
    answer never arrives leaves the run not knowing whether those rows
    landed, so nothing is recorded, the run is left 'partly_sent', and
    the next attempt reads the opportunity and sends the difference.
    Duplicate safety rests on that live read.

    **Each opportunity is read in the step that sends to it**, not all
    at the start: minutes can pass between the first batch and the
    last, and a shift created in that time would otherwise be created
    twice.
"""

# Imports - Python Standard Library
import sqlite3
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Imports - Local
from . import _defaults
from ._database import transaction
from ._derived import minutes_between
from ._exceptions import ValidationError
from ._helpers import amplify_headers, Helpers
from ._logging import get_logger
from ._opportunities import read_need, shifts_in, UNKNOWN_TITLE
from ._preview import asked_for, PlannedShift, split_by_existing
from ._reading import read_run_for_send
from ._records import (
    IdempotencyRecord,
    Job,
    JOB_HOLDER_SERVICE,
    JOB_KIND_SEND,
    Opportunity,
    Run,
    RUN_STATUS_PARTLY_SENT,
    RUN_STATUS_SENT
)
from ._reporting import (
    Reporter,
    ShiftBatch,
    STEP_READ_OPPORTUNITY
)
from ._repository import (
    IdempotencyRepository,
    JobRepository,
    RunRepository,
    SentShiftRepository
)

# Constants
AMPLIFY_DATE_TIME_FORMAT = _defaults.AMPLIFY_DATE_TIME_FORMAT
BASE_AMPLIFY_URL = _defaults.BASE_AMPLIFY_URL
HTTP_TIMEOUT = _defaults.HTTP_TIMEOUT
SHIFTS_DICT_KEY_NAME = _defaults.SHIFTS_DICT_KEY_NAME

# Module logger
logger = get_logger(__name__)


def shifts_url(
        need_id: str
) -> str:
    """ Return where an opportunity's shifts are created.

        Args:
            need_id (str):
                Amplify need ID.

        Returns:
            url (str):
                The address a create request is sent to.
    """

    return f'{BASE_AMPLIFY_URL}/needs/{need_id}/shifts'


def _shift_body(
        shift: PlannedShift
) -> Dict[str, str]:
    """ Return one shift as Amplify is asked for it.

        Amplify takes a start and a length rather than a start and an
        end, so the length is worked out here from the two times the
        revision stores -- by the same function that tells a reader how
        long the shift is, so the number that arrives is the number
        they were shown.

        Every value is a string, which is what the published schema
        asks for.

        Args:
            shift (PlannedShift):
                The shift to create.

        Raises:
            ValueError:
                If the shift's times are not times.

        Returns:
            body (Dict[str, str]):
                The shift, as one item of a create request.
    """

    return {
        'start': f'{shift.date} {shift.shift_start}',
        'duration': str(
            minutes_between(
                start=shift.shift_start,
                end=shift.shift_end
            )
        ),
        'slots': str(shift.slots)
    }


def payload_for(
        shifts: Sequence[PlannedShift]
) -> Dict[str, Any]:
    """ Return the body one opportunity's create request carries.

        Args:
            shifts (Sequence[PlannedShift]):
                The shifts to create under it.

        Raises:
            ValueError:
                If a shift's times are not times.

        Returns:
            payload (Dict[str, Any]):
                The request body.
    """

    return {
        SHIFTS_DICT_KEY_NAME: [
            _shift_body(shift=shift) for shift in shifts
        ]
    }


def _titles(
        opportunities: Sequence[Opportunity]
) -> Dict[str, str]:
    """ Return what each opportunity is called, by need ID.

        Args:
            opportunities (Sequence[Opportunity]):
                The run's opportunities.

        Returns:
            titles (Dict[str, str]):
                Titles by need ID.
    """

    return {
        opportunity.need_id: opportunity.title
        for opportunity in opportunities
    }


def _create(
        helpers: Helpers,
        need_id: str,
        shifts: Sequence[PlannedShift],
        timeout: int = HTTP_TIMEOUT
) -> Dict[str, Any]:
    """ Ask Amplify to create one opportunity's shifts.

        Args:
            helpers (Helpers):
                What the request is sent through.

            need_id (str):
                Opportunity to create them under.

            shifts (Sequence[PlannedShift]):
                The shifts to create.

            timeout (int, optional):
                HTTP timeout.  Defaults to the configured value.

        Raises:
            UpstreamError:
                If Amplify cannot be reached or refuses the request.
                Nothing is recorded for a request that raised, because
                what it did is exactly what is unknown.

            ValueError:
                If a shift's times are not times.

        Returns:
            payload (Dict[str, Any]):
                What was sent, for the reporter to describe.
    """

    payload = payload_for(shifts=shifts)

    helpers.send_api_request(
        api_request_data={
            'method': 'POST',
            'url': shifts_url(need_id=need_id),
            'headers': amplify_headers(),
            'json': payload,
            'timeout': timeout
        },
        display_request_status=False
    )

    return payload


def _record(
        connection: sqlite3.Connection,
        run_id: str,
        shifts: Sequence[PlannedShift],
        principal_id: str,
        idempotency_key: str
) -> None:
    """ Write down what one batch created, and that the run has sent.

        Both in one transaction.  A run holding sent shifts and still
        calling itself unsent would be one a recollection was willing
        to replace, and Amplify cannot take those shifts back.

        Args:
            connection (sqlite3.Connection):
                The database to write to.

            run_id (str):
                Run whose send created them.

            shifts (Sequence[PlannedShift]):
                The shifts Amplify has just been given.

            principal_id (str):
                Who sent them (D13).

            idempotency_key (str):
                The key the send was made under (D13).

        Raises:
            ValidationError:
                If a shift is already recorded, which means the send
                lost track of what it did.

            UpstreamError:
                If the record cannot be written.

        Returns:
            None.
    """

    with transaction(connection=connection):
        SentShiftRepository(connection=connection).record(
            run_id=run_id,
            identities=[shift.identity for shift in shifts],
            principal_id=principal_id,
            idempotency_key=idempotency_key
        )
        RunRepository(connection=connection).mark_sent(
            run_id=run_id,
            status=RUN_STATUS_PARTLY_SENT
        )

    return None


def blocked_message(
        blocking: int
) -> str:
    """ Return what to say about a revision that cannot be sent at all.

        Args:
            blocking (int):
                How many of its events cannot become shifts.

        Returns:
            message (str):
                What to tell the caller.
    """

    return (
        f'{blocking} event(s) in this run cannot become a shift, so '
        'nothing is sent. A missing shift is invisible until '
        'volunteers cannot sign up, so the run stops rather than '
        'sending the rest. Read the preview, which names every one of '
        'them and why.'
    )


def claim(
        connection: sqlite3.Connection,
        run_id: str,
        key: str,
        fingerprint: str,
        principal_id: str,
        *,
        held_by: str = JOB_HOLDER_SERVICE
) -> Tuple[Optional[IdempotencyRecord], Optional[Job]]:
    """ Claim a key for a send and record the job, or say who was first.

        Both in one transaction.  A key reserved against a job that was
        never written would refuse every later attempt to send that run
        under it; a job written without the reservation would let a
        second request start a second one.

        Below both callers.  The service claims a key before queuing a
        job and the command line client claims one before running the
        work in the call (D2), and a half that reserved without
        recording, or recorded without reserving, would be a mode where
        a send could happen twice.

        Args:
            connection (sqlite3.Connection):
                The database to write to.

            run_id (str):
                Run to send.

            key (str):
                What the caller supplied.

            fingerprint (str):
                What the request asked for, as the caller summarized
                it, for comparing against a replay.

            principal_id (str):
                Who asked (D13).

            held_by (str, optional):
                Which of 'JOB_HOLDERS' will run the job.  Defaults to
                the service.

        Raises:
            ValidationError:
                If there is no such run, or neither can be written.

            UpstreamError:
                If the database refuses the write.

        Returns:
            claimed (Tuple[IdempotencyRecord | None, Job | None]):
                The reservation that was already there and no job, or
                no reservation and the job this call started.
    """

    with transaction(connection=connection):
        existing = IdempotencyRepository(connection=connection).reserve(
            operation=JOB_KIND_SEND,
            key=key,
            run_id=run_id,
            fingerprint=fingerprint,
            principal_id=principal_id
        )

        if existing is not None:
            return existing, None

        return None, JobRepository(connection=connection).create(
            run_id=run_id,
            kind=JOB_KIND_SEND,
            principal_id=principal_id,
            held_by=held_by
        )


def _refuse(
        message: str
) -> None:
    """ Log why the send will not happen, and stop it.

        Args:
            message (str):
                What to tell the caller, written for a person.

        Raises:
            ValidationError:
                Always.

        Returns:
            None.
    """

    logger.error(message)

    raise ValidationError(message)


@dataclass(frozen=True)
class _Sending:
    """ What every batch of one send works from.

        A record rather than five parameters repeated per batch: they
        describe one send and always travel together, and a batch that
        was given a different key or a different principal from the
        batch beside it would be a send whose record disagreed with
        itself.

        Attributes:
            connection (sqlite3.Connection):
                The database to write to.

            helpers (Helpers):
                What the Amplify requests are sent through.

            run_id (str):
                Run being sent.

            titles (Dict[str, str]):
                What each opportunity is called, by need ID.

            principal_id (str):
                Who asked (D13).

            idempotency_key (str):
                The key the send was made under (D13).
    """

    connection: sqlite3.Connection
    helpers: Helpers
    run_id: str
    titles: Dict[str, str]
    principal_id: str
    idempotency_key: str


def _send_to(
        sending: _Sending,
        need_id: str,
        wanted: Sequence[PlannedShift],
        index: int,
        reporter: Reporter
) -> Sequence[PlannedShift]:
    """ Read one opportunity, create what it is missing, record it.

        The read happens here rather than once for the whole run,
        immediately before the request that acts on it.  Minutes can
        pass between the first opportunity and the last, and a shift
        created in that time by anything else would otherwise be
        created twice.

        Args:
            sending (_Sending):
                What the send works from.

            need_id (str):
                Opportunity to send to.

            wanted (Sequence[PlannedShift]):
                The shifts the revision asks for under it.

            index (int):
                Position of this opportunity in the send, from one, for
                the report.

            reporter (Reporter):
                Where progress is described.

        Raises:
            UpstreamError:
                If the opportunity cannot be read, or Amplify refuses
                the create request.

            ValidationError:
                If a shift is already in this run's sent record.

        Returns:
            created (Sequence[PlannedShift]):
                The shifts this batch created, which is empty when
                Amplify already had all of them.
    """

    reporter.step_started(
        step=STEP_READ_OPPORTUNITY,
        subject=need_id
    )
    existing = shifts_in(
        need_id=need_id,
        need=read_need(helpers=sending.helpers, need_id=need_id)
    )
    reporter.step_finished()

    creating, already = split_by_existing(
        shifts=wanted,
        existing=existing
    )
    # An opportunity Amplify already holds every shift for is one this
    # send finished with, so nothing is created and nothing recorded,
    # and the report below is made all the same.
    payload = payload_for(shifts=())

    if creating:
        payload = _create(
            helpers=sending.helpers,
            need_id=need_id,
            shifts=creating
        )
        _record(
            connection=sending.connection,
            run_id=sending.run_id,
            shifts=creating,
            principal_id=sending.principal_id,
            idempotency_key=sending.idempotency_key
        )

    reporter.opportunity_sent(
        batch=ShiftBatch(
            index=index,
            need_id=need_id,
            title=sending.titles.get(need_id, UNKNOWN_TITLE),
            url=shifts_url(need_id=need_id),
            shifts=payload[SHIFTS_DICT_KEY_NAME],
            skipped=len(already),
            payload=payload
        )
    )

    return creating


def send(
        connection: sqlite3.Connection,
        run_id: str,
        reporter: Reporter,
        principal_id: str,
        idempotency_key: str
) -> Run:
    """ Create a run's outstanding shifts in Amplify.

        Args:
            connection (sqlite3.Connection):
                The database to read and write.

            run_id (str):
                Run to send.

            reporter (Reporter):
                Where progress is described.

            principal_id (str):
                Who asked (D13).

            idempotency_key (str):
                The key the send was made under (D13).

        Raises:
            ValidationError:
                If there is no such run, or an event in it cannot
                become a shift.

            UpstreamError:
                If an opportunity cannot be read, or Amplify refuses a
                create request.  The batches already created stay
                created and stay recorded: what raised is unfinished,
                not undone.

        Returns:
            run (Run):
                The run as it now stands.
    """

    gathered = read_run_for_send(connection=connection, run_id=run_id)

    if gathered is None:
        _refuse(
            message=f'There is no run with the identifier "{run_id}".'
        )

    events, opportunities = gathered
    asked = asked_for(events=events)

    if asked.blocking_events:
        _refuse(message=blocked_message(blocking=asked.blocking_events))

    sending = _Sending(
        connection=connection,
        helpers=Helpers(),
        run_id=run_id,
        titles=_titles(opportunities=opportunities),
        principal_id=principal_id,
        idempotency_key=idempotency_key
    )
    created = 0

    reporter.sending_started(opportunities=len(asked.by_opportunity))

    for index, (need_id, wanted) in enumerate(
        iterable=sorted(asked.by_opportunity.items()),
        start=1
    ):
        created += len(
            _send_to(
                sending=sending,
                need_id=need_id,
                wanted=wanted,
                index=index,
                reporter=reporter
            )
        )

    return _finished(
        connection=connection,
        run_id=run_id,
        created=created,
        asked_of=list(asked.by_opportunity)
    )


def _finished(
        connection: sqlite3.Connection,
        run_id: str,
        created: int,
        asked_of: List[str]
) -> Run:
    """ Record that the send reached the end, and report the run.

        Reaching here means every opportunity was read and every batch
        that had anything to create was answered, so everything the
        revision asks for is in Amplify.  That is true of a send that
        created nothing as well: it found each row already there.

        A run asking for nothing at all is left where it was.  It has
        not sent anything and saying it had would make a recollection
        refuse to replace it.

        A run that found every row already there is 'sent' as well.
            Nothing is left for it to do, which is what the status
            says; it did not put them there, which is what its empty
            sent record says.

        Args:
            connection (sqlite3.Connection):
                The database to write to.

            run_id (str):
                The run.

            created (int):
                How many shifts this send created.

            asked_of (List[str]):
                The opportunities it had shifts for.

        Raises:
            ValidationError:
                If the run cannot be updated.

        Returns:
            run (Run):
                The run as it now stands.
    """

    runs = RunRepository(connection=connection)

    if asked_of:
        runs.mark_sent(run_id=run_id, status=RUN_STATUS_SENT)

    message = (
        f'Sent {created} shift(s) for run {run_id} across '
        f'{len(asked_of)} opportunity(s)'
    )
    logger.info(message)

    return runs.get(run_id=run_id)
