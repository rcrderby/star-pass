#!/usr/bin/env python3
""" Marking where a run has got to, and going back to a mark.

    An edit changes the revision a run is working in, in place.
    Sealing fixes what the run holds now as something numbered and
    readable and moves the work to a new revision, so a reviewer about
    to try something can come back to what they had.  Reverting is
    coming back.

    Both are forward steps and neither destroys anything.  Sealing
    adds a revision holding a copy of the current one; reverting adds
    a revision holding a copy of an earlier one, one per revert, and
    the revision that was current stays readable at its own number.

    Reverting to the revision a collection filled drops the events a
    person pulled in by hand, because that revision is the run as the
    calendar gave it.

    In the core, not the service: a revision means the same thing to
    whoever asks for one.
"""

# Imports - Python Standard Library
import sqlite3
from typing import Optional

# Imports - Local
from ._database import transaction
from ._exceptions import ValidationError
from ._logging import get_logger
from ._records import Revision
from ._repository import EventRepository, RevisionRepository, RunRepository

# Constants
# The revision a collection fills.  Reverting to it is asking for the
# run as the calendar gave it, which is why it is the one revert that
# drops what a person pulled in by hand.
COLLECTED_REVISION = 1

# Module logger
logger = get_logger(__name__)


def seal(
        connection: sqlite3.Connection,
        run_id: str
) -> Optional[Revision]:
    """ Fix what a run holds now, and open a revision to work in.

        Who sealed it is recorded against the key the write was
        claimed under rather than in the change log: the change
        count on a revision is what was done *while it was current*,
        and an entry written as one opens would have every sealed
        revision starting at one change nobody made.

        Args:
            connection (sqlite3.Connection):
                Connection to write on.

            run_id (str):
                Run to seal the current revision of.

        Raises:
            ValidationError:
                If the run has collected nothing yet, so there is no
                revision to seal.

            UpstreamError:
                If the revision cannot be written.

        Returns:
            revision (Revision | None):
                The revision now being worked in, or None when there
                is no such run.
    """

    if RunRepository(connection=connection).get(run_id=run_id) is None:
        return None

    revisions = RevisionRepository(connection=connection)
    sealed = revisions.list_all(run_id=run_id)

    if not sealed:
        # The first revision is the collection's to open, and it is
        # labelled for what filled it. One opened here would be an
        # empty revision the collection then replaced.
        message = (
            f'Run {run_id} has collected nothing yet, so there is no '
            'revision to seal.'
        )
        logger.error(message)
        raise ValidationError(message)

    opened = revisions.create(run_id=run_id)

    message = (
        f'Sealed revision {opened.number - 1} of run {run_id} and '
        f'opened revision {opened.number}'
    )
    logger.info(message)

    return opened


def revert(
        connection: sqlite3.Connection,
        run_id: str,
        number: int
) -> Optional[Revision]:
    """ Take a run back to what an earlier revision holds.

        One revision per revert.  Nothing between the two is deleted,
        so the revision that was current is still readable at its own
        number and there is nothing to seal before going back: a seal
        first would add a revision holding an identical copy of the
        one it sealed.

        Reverting to the revision the collection filled also drops the
        events a person pulled in by hand.  That revision is the run
        as the calendar gave it, and what puts a dropped event back on
        the list of what was not collected is the current revision no
        longer holding it -- the row was never deleted.

        Args:
            connection (sqlite3.Connection):
                Connection to write on.

            run_id (str):
                Run to take back.

            number (int):
                Revision to go back to the contents of.

        Raises:
            ValidationError:
                If the run has no such revision.

            UpstreamError:
                If the revision cannot be written.

        Returns:
            revision (Revision | None):
                The revision now being worked in, holding what the
                one reverted to held, or None when there is no such
                run.
    """

    if RunRepository(connection=connection).get(run_id=run_id) is None:
        return None

    with transaction(connection=connection):
        opened = RevisionRepository(connection=connection).revert_to(
            run_id=run_id,
            number=number
        )

        if number == COLLECTED_REVISION:
            _drop_hand_added(
                connection=connection,
                run_id=run_id,
                revision=opened.number
            )

    message = (
        f'Reverted run {run_id} to revision {number} and opened '
        f'revision {opened.number}'
    )
    logger.info(message)

    return opened


def _drop_hand_added(
        connection: sqlite3.Connection,
        run_id: str,
        revision: int
) -> None:
    """ Remove from a revision the events a person pulled in.

        Args:
            connection (sqlite3.Connection):
                Connection to write on.

            run_id (str):
                Run the revision belongs to.

            revision (int):
                Revision to remove them from.

        Raises:
            UpstreamError:
                If an event cannot be removed.

        Returns:
            None.
    """

    events = EventRepository(connection=connection)

    for event in events.list_all(run_id=run_id, revision=revision):
        if event.added_by_hand:
            events.remove(
                run_id=run_id,
                revision=revision,
                event_id=event.id
            )

    return None
