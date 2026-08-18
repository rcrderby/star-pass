#!/usr/bin/env python3
""" Marking where a run has got to, so it can be gone back to.

    An edit changes the revision a run is working in, in place.  That
    is what makes a revision worth sealing: it fixes what the run
    holds now as something numbered and readable, and moves the work
    to a new revision, so a reviewer who is about to try something can
    come back to what they had.

    Nothing here deletes anything, and nothing here decides what a
    caller is told.  Sealing adds a revision holding a copy of the
    current one; the revision that was current keeps its rows and
    stays readable at its own number.

    In the core, not the service: nothing about it is HTTP, and a
    revision means the same thing to whoever asks for one.
"""

# Imports - Python Standard Library
import sqlite3
from typing import Optional

# Imports - Local
from ._exceptions import ValidationError
from ._logging import get_logger
from ._records import Revision
from ._repository import RevisionRepository, RunRepository

# Constants
# How a revision opened by sealing the one before it is named to a
# reader.  It says what happened rather than what is in it, because
# what is in it is a copy of the revision it names.
CONTINUED_LABEL = 'Continued from revision {number}'

# Module logger
logger = get_logger(__name__)


def seal(
        connection: sqlite3.Connection,
        run_id: str
) -> Optional[Revision]:
    """ Fix what a run holds now, and open a revision to work in.

        Who sealed it is recorded against the key the write was
        claimed under (D13) rather than in the change log: the change
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

    opened = revisions.create(
        run_id=run_id,
        label=CONTINUED_LABEL.format(number=sealed[-1].number)
    )

    message = (
        f'Sealed revision {opened.number - 1} of run {run_id} and '
        f'opened revision {opened.number}'
    )
    logger.info(message)

    return opened
