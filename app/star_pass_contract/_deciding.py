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
from typing import Any, Callable, Dict, Optional, Tuple

# Imports - Local
from star_pass._opportunities import shifts_in_amplify
from star_pass._reading import read_run_for_send
from star_pass._records import IdempotencyRecord, Run
from star_pass._repository import RunRepository
from ._messages import replay, REPLAY_DIFFERENT, REPLAY_RUNNING, why_not_send
from ._views import previewed


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
