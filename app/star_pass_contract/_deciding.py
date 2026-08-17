#!/usr/bin/env python3
""" What both halves have to decide the same way, read from what is stored.

    A refusal is not only a message.  Deciding whether a run may be
    sent means reading the run, reading the revision a send would work
    from, asking Amplify what it already holds, and working out what
    would be created -- and a half that read one fewer of those, or
    read them in a different order, would refuse a different thing
    while saying the same words.

    So the reading and the deciding live together, below both halves,
    for the reason '_messages' says of the words alone: the service
    answers over HTTP and the command line client answers from the same
    database in the same process (D2), and D2 only holds while the two
    reach the same answer.

    Nothing here decides what a refusal *is* to a caller.  A status
    code is a property of the transport, and each half raises its own
    kind of failure carrying the reason this module chose.
"""

# Imports - Python Standard Library
import sqlite3
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple

# Imports - Local
from star_pass._editing import edit
from star_pass._exceptions import ValidationError
from star_pass._opportunities import shifts_in_amplify
from star_pass._reading import read_run_for_send
from star_pass._revising import seal
from star_pass._records import (
    IdempotencyRecord,
    Job,
    OPERATION_EDIT,
    OPERATION_SEAL,
    Run
)
from star_pass._repository import (
    IdempotencyRepository,
    JobRepository,
    RunRepository
)
from ._requests import EditRequest
from ._messages import (
    replay,
    REPLAY_DIFFERENT,
    REPLAY_RUNNING,
    why_not_resume,
    why_not_send
)
from ._views import (
    previewed,
    to_edit_view,
    to_operations,
    to_revision_views
)

# Constants
# What an edit answers with.  It is carried out in the request that
# asked for it, so there is nothing to watch and nothing to accept.
EDIT_STATUS_CODE = 200

# What sealing a revision answers with.  A revision that was not there
# before is a thing created, and the answer names it.
SEAL_STATUS_CODE = 201


@dataclass(frozen=True)
class WriteRefusals:
    """ How one half says no to a keyed write.

        A record rather than three parameters: a status code belongs to
        the transport, so each half supplies its own way of refusing,
        and three callables in a signature is a signature nobody reads.

        Attributes:
            missing (Callable):
                Called with 'run_id' when there is no such run.

            conflict (Callable):
                Called with 'detail' when an operation cannot be
                applied.

            refuse (Callable):
                Called with 'detail' when a key carries a different
                request.
    """

    missing: Callable[..., Exception]
    conflict: Callable[..., Exception]
    refuse: Callable[..., Exception]


def sendable(
        connection: sqlite3.Connection,
        run_id: str,
        expected: int
) -> Optional[Tuple[Run, Optional[str]]]:
    """ Read a run and decide whether a send may go ahead.

        The check the plan calls "when the run is opened", made before
        anything is written, so a caller who cannot send is told why in
        the answer to their own request rather than by reading a job
        that failed.  The core makes the other one, against each
        opportunity immediately before the request that writes to it.

        Args:
            connection (sqlite3.Connection):
                The database to read.

            run_id (str):
                Run to send.

            expected (int):
                How many shifts the caller was shown.

        Raises:
            UpstreamError:
                If an opportunity cannot be read.  A send decided
                without that answer would create every shift again.

        Returns:
            found (Tuple[Run, str | None] | None):
                The run and why it may not be sent, or None when there
                is no such run.
    """

    run = RunRepository(connection=connection).get(run_id=run_id)
    gathered = read_run_for_send(connection=connection, run_id=run_id)

    if run is None or gathered is None:
        return None

    events, opportunities = gathered
    result = previewed(
        events=events,
        opportunities=opportunities,
        existing=shifts_in_amplify(events=events)
    )

    return run, why_not_send(
        run=run,
        blocking=result.blocking_events,
        will_create=result.will_create,
        expected=expected
    )


def resumable(
        connection: sqlite3.Connection,
        job_id: str
) -> Optional[Tuple[Job, Optional[str]]]:
    """ Read a job and decide whether it may be resumed (D10).

        The run is read as well as the job, and not only to know it
        exists: whether something else is already working on it is
        half of the answer, and a job read without it would be
        resumable on paper while a send was in hand.

        Args:
            connection (sqlite3.Connection):
                The database to read.

            job_id (str):
                Job to resume.

        Raises:
            UpstreamError:
                If the job cannot be read.

        Returns:
            found (Tuple[Job, str | None] | None):
                The job and why it may not be resumed, or None when
                there is no such job.
    """

    job = JobRepository(connection=connection).get(job_id=job_id)

    if job is None:
        return None

    run = RunRepository(connection=connection).get(run_id=job.run_id)

    if run is None:
        return None

    return job, why_not_resume(job=job, run=run)


def replayed(
        record: IdempotencyRecord,
        run_id: str,
        fingerprint: str,
        refuse: Callable[[str], Exception],
        conflict: Callable[[str], Exception]
) -> Dict[str, Any]:
    """ Return what a used key already answered, or refuse the request.

        Both halves classify a request arriving on a used key the same
        way and refuse the same two things about it; what they differ
        in is only the kind of failure each raises, which is a property
        of how it is being asked rather than of what was asked.  So the
        two failures arrive as arguments and everything else is decided
        here.

        Args:
            record (IdempotencyRecord):
                What the key reserved.

            run_id (str):
                Run this request is about.

            fingerprint (str):
                What it asks for.

            refuse (Callable[[str], Exception]):
                What to raise when the key carries another request.

            conflict (Callable[[str], Exception]):
                What to raise when the first request has not answered.

        Raises:
            Exception:
                Whichever of the two the caller supplied.

        Returns:
            answer (Dict[str, Any]):
                The body the first request answered with.
    """

    kind, reason = replay(
        record=record,
        run_id=run_id,
        fingerprint=fingerprint
    )

    if kind == REPLAY_DIFFERENT:
        raise refuse(reason)

    if kind == REPLAY_RUNNING:
        raise conflict(reason)

    return record.response


@dataclass(frozen=True)
class KeyedWrite:
    """ One write claimed under a key, and what carrying it out means.

        A record rather than four more parameters, and written once
        rather than per write: the sequence around it is the same
        every time and it is the sequence that is the decision.

        Attributes:
            operation (str):
                Which write, one of 'IDEMPOTENT_OPERATIONS'.  A key is
                per operation, so the same value used on two of them
                is two reservations rather than one replaying the
                other.

            fingerprint (str):
                What this request asks for, as the key remembers it.
                A second request on the same key carrying a different
                one is refused rather than answered from the first.

            status_code (int):
                What the answer is recorded under, so a replay is
                given the status the first request was.

            carry_out (Callable):
                Called with the connection once the key is claimed.
                Returns the answer as the contract publishes it, or
                None when the run turned out not to be there.
    """

    operation: str
    fingerprint: str
    status_code: int
    carry_out: Callable[[sqlite3.Connection], Optional[Dict[str, Any]]]


def keyed_write(
        connection: sqlite3.Connection,
        run_id: str,
        key: str,
        principal_id: str,
        *,
        write: KeyedWrite,
        refusals: WriteRefusals
) -> Dict[str, Any]:
    """ Claim the key, carry the write out, and record what it answered.

        Below both halves, and below every write that is answered in
        the request that asked for it, because **the sequence is the
        decision**.  Claiming the key after the write would let a
        retry write twice; recording the answer before the write would
        answer a retry from something that never happened; and reading
        the run after the claim would spend a reservation on a run
        that is not there -- which reported a foreign key violation as
        a malformed request, once.

        Args:
            connection (sqlite3.Connection):
                Connection to write on.

            run_id (str):
                Run the write acts on.

            key (str):
                What this action is claimed under (D13, D16).

            principal_id (str):
                Who asked (D13).

            write (KeyedWrite):
                Which write it is, and what carrying it out means.

            refusals (WriteRefusals):
                How this half says no.  A status code belongs to the
                transport, so each half supplies its own.

        Raises:
            Whatever 'refusals' raises: the run is not there, the
            write cannot be carried out, or the key carries a
            different request.

        Returns:
            answer (Dict[str, Any]):
                What the write answered, shaped as the contract
                publishes it.
    """

    # Before the key is claimed: a run that does not exist would make
    # the reservation a foreign key violation, which reads as a
    # malformed request rather than as the missing run it is.
    if RunRepository(connection=connection).get(run_id=run_id) is None:
        raise refusals.missing(run_id=run_id)

    # Named for what a non-empty answer means here: the action was
    # already claimed, and this request is its second arrival.
    keys = IdempotencyRepository(connection=connection)
    claimed = keys.reserve(
        operation=write.operation,
        run_id=run_id,
        key=key,
        principal_id=principal_id,
        fingerprint=write.fingerprint
    )

    if claimed is not None:
        return replayed(
            record=claimed,
            run_id=run_id,
            fingerprint=write.fingerprint,
            refuse=refusals.refuse,
            conflict=refusals.conflict
        )

    try:
        answer = write.carry_out(connection)

    except ValidationError as error:
        # The reservation stays, holding this key against the request
        # that failed: a retry with the same key and the same request
        # is the same failed action, not a new one.
        raise refusals.conflict(detail=str(error)) from error

    if answer is None:
        raise refusals.missing(run_id=run_id)

    keys.complete(
        operation=write.operation,
        key=key,
        status_code=write.status_code,
        response=answer
    )

    return answer


def edited(
        connection: sqlite3.Connection,
        run_id: str,
        asked: EditRequest,
        key: str,
        principal_id: str,
        *,
        refusals: WriteRefusals
) -> Dict[str, Any]:
    """ Apply one action's operations to a run's current revision.

        Args:
            connection (sqlite3.Connection):
                Connection to write on.

            run_id (str):
                Run whose current revision to edit.

            asked (EditRequest):
                What the reviewer did.

            key (str):
                What this action is claimed under (D13, D16).

            principal_id (str):
                Who did it (D13).

            refusals (WriteRefusals):
                How this half says no.

        Raises:
            Whatever 'refusals' raises: the run is not there, an
            operation cannot be applied, or the key carries a
            different request.

        Returns:
            answer (Dict[str, Any]):
                The revision as it now is and what was logged, shaped
                as the contract publishes it.
    """

    def apply_the_edit(
            open_connection: sqlite3.Connection
    ) -> Optional[Dict[str, Any]]:
        """ Edit the run and return the revision it left. """
        result = edit(
            connection=open_connection,
            run_id=run_id,
            operations=to_operations(asked=asked),
            principal_id=principal_id
        )

        if result is None:
            return None

        events, entries = result

        return to_edit_view(
            events=events,
            opportunities=RunRepository(
                connection=open_connection
            ).get_opportunities(run_id=run_id),
            entries=entries
        ).model_dump(by_alias=True, mode='json')

    return keyed_write(
        connection=connection,
        run_id=run_id,
        key=key,
        principal_id=principal_id,
        write=KeyedWrite(
            operation=OPERATION_EDIT,
            fingerprint=asked.fingerprint(),
            status_code=EDIT_STATUS_CODE,
            carry_out=apply_the_edit
        ),
        refusals=refusals
    )


def sealed(
        connection: sqlite3.Connection,
        run_id: str,
        key: str,
        principal_id: str,
        *,
        refusals: WriteRefusals
) -> Dict[str, Any]:
    """ Seal the revision a run is working in and open the next one.

        The fingerprint is the operation itself, because the request
        carries nothing else: sealing a run twice under one key is one
        seal, and a second key is a second seal.

        Args:
            connection (sqlite3.Connection):
                Connection to write on.

            run_id (str):
                Run to seal the current revision of.

            key (str):
                What the seal is claimed under, so a retry opens no
                second revision (D13, D16).

            principal_id (str):
                Who sealed it (D13).

            refusals (WriteRefusals):
                What this half raises when it will not carry the write
                out.

        Raises:
            Whatever 'refusals' raises: no such run, nothing collected
            to seal, or a key already carrying another request.

        Returns:
            answer (Dict[str, Any]):
                The revision now being worked in, shaped as the
                contract publishes it.
    """

    def seal_the_revision(
            open_connection: sqlite3.Connection
    ) -> Optional[Dict[str, Any]]:
        """ Seal the current revision and return the one it opened. """
        opened = seal(connection=open_connection, run_id=run_id)

        if opened is None:
            return None

        run = RunRepository(connection=open_connection).get(run_id=run_id)

        return to_revision_views(
            run=run,
            revisions=[opened]
        )[0].model_dump(by_alias=True, mode='json')

    return keyed_write(
        connection=connection,
        run_id=run_id,
        key=key,
        principal_id=principal_id,
        write=KeyedWrite(
            operation=OPERATION_SEAL,
            fingerprint=OPERATION_SEAL,
            status_code=SEAL_STATUS_CODE,
            carry_out=seal_the_revision
        ),
        refusals=refusals
    )
