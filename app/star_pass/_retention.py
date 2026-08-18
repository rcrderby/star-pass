#!/usr/bin/env python3
""" Forgetting what a run leaves behind, on a policy (D12, D20).

    The driver is what this data *is*, not how much of it there is: a
    job's event log names volunteers and the times they were asked to
    be somewhere, and a revision holds the events that were in it.
    None of it is small enough a reason to keep forever, and none of
    it is what the tool exists to produce.

    **What is never forgotten is the sent record.**  Duplicate safety
    reads it to know which rows a run already created, so a window
    there would eventually have a run offering to create shifts
    Amplify already has -- which is the failure this whole design is
    arranged around.  It is deliberately absent below.

    Three things are swept and each is swept on its own terms, because
    the question 'is this still worth keeping' has a different answer
    for each:

    - A **job's event log** is worth keeping while somebody might look
      into what a run did, which is one monthly cycle and some room.
      The job row outlives it: that a send ran and how it ended is not
      what the window is protecting.
    - A **revision** is worth keeping while somebody might go back to
      it.  The first and the current one always are, so what expires
      is the sealed points in between, once the run itself has stopped
      being worked on.
    - An **unmatched title** is worth keeping until the data model
      matches it, which is the entire reason one is recorded.  Age is
      the wrong question to ask of it -- its value is that it
      accumulates -- so the model answers first and age is only a
      backstop for a title nobody ever acted on (D20).

    Nothing here is reachable over the API and nothing should be.  The
    contract deliberately publishes no deletion: retention removes a
    run's leavings, a caller does not (plan section 5).
"""

# Imports - Python Standard Library
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

# Imports - Local
from . import _defaults
from ._helpers import Helpers
from ._logging import get_logger
from ._repository import (
    JobRepository,
    RevisionRepository,
    UnmatchedTitleRepository
)

# Module logger
logger = get_logger(__name__)


@dataclass(frozen=True)
class Swept:
    """ What one sweep removed.

        Returned rather than only logged, so a caller can say whether
        anything happened and a test can ask what did.

        Attributes:
            job_events (int):
                Event log rows deleted.

            revisions (int):
                Revisions deleted, not counting the events inside them,
                which the database removes with each one.

            unmatched_titles (int):
                Sightings deleted, across every title forgotten.
    """

    job_events: int = 0
    revisions: int = 0
    unmatched_titles: int = 0

    def __bool__(self) -> bool:
        """ Return whether the sweep removed anything at all.

            Args:
                None.

            Returns:
                removed (bool):
                    Whether any count is above zero.
        """

        return bool(
            self.job_events
            or self.revisions
            or self.unmatched_titles
        )


def sweep(
        connection: sqlite3.Connection,
        now: Optional[datetime] = None,
        helpers: Optional[Helpers] = None
) -> Swept:
    """ Forget everything the policy says is no longer worth keeping.

        Args:
            connection (sqlite3.Connection):
                Connection to write on.  The caller owns it, because a
                connection belongs to the thread that opened it.

            now (datetime, optional):
                What to measure the windows back from.  Defaults to
                the current time; supplied by a test, which cannot
                wait ninety days.

            helpers (Helpers, optional):
                What answers whether the data model matches a title.
                Defaults to a new one.

        Raises:
            UpstreamError:
                If anything cannot be removed.

        Returns:
            swept (Swept):
                What was removed.
    """

    moment = now if now is not None else datetime.now(timezone.utc)

    swept = Swept(
        job_events=JobRepository(
            connection=connection
        ).forget_events_before(
            cutoff=_before(
                moment=moment,
                days=_defaults.RETENTION_JOB_LOG_DAYS
            )
        ),
        revisions=RevisionRepository(
            connection=connection
        ).forget_superseded(
            cutoff=_before(
                moment=moment,
                days=_defaults.RETENTION_REVISION_DAYS
            )
        ),
        unmatched_titles=_forget_titles(
            connection=connection,
            moment=moment,
            helpers=helpers if helpers is not None else Helpers()
        )
    )

    if swept:
        message = (
            f'Retention removed {swept.job_events} job event(s), '
            f'{swept.revisions} revision(s) and '
            f'{swept.unmatched_titles} unmatched title sighting(s).'
        )
        logger.info(message)

    return swept


def _forget_titles(
        connection: sqlite3.Connection,
        moment: datetime,
        helpers: Helpers
) -> int:
    """ Forget the titles that have stopped being worth a look.

        A title goes when the data model matches it, because that is
        what recording it was for and the row is then a person's name
        being kept for no reason.  The check is the same one that
        decided to record it, so nothing new has to be agreed on: a
        title the model matches produces no fresh sighting either.

        Age is only the backstop, and it is measured from the most
        recent sighting rather than each row's own.  Measured per row,
        a title still turning up would quietly lose its early
        sightings and report a smaller count -- which reads as a title
        that has stopped recurring, and is the opposite of true.

        Args:
            connection (sqlite3.Connection):
                Connection to write on.

            moment (datetime):
                What the backstop is measured back from.

            helpers (Helpers):
                What answers whether the model matches a title.

        Raises:
            UpstreamError:
                If a title cannot be read or removed.

        Returns:
            removed (int):
                How many sightings were deleted.
    """

    unmatched = UnmatchedTitleRepository(connection=connection)
    stale = _before(
        moment=moment,
        days=_defaults.RETENTION_UNMATCHED_TITLE_DAYS
    )
    removed = 0

    for entry in unmatched.list_all():
        matched_now = helpers.match_shift_info(
            gcal_name=entry.calendar,
            need_name=entry.title
        ).category is not None

        if matched_now or entry.last_seen < stale:
            removed += unmatched.forget(
                calendar=entry.calendar,
                title=entry.title
            )

    return removed


def _before(
        moment: datetime,
        days: int
) -> str:
    """ Return the timestamp a window of days reaches back to.

        Args:
            moment (datetime):
                What to measure back from.

            days (int):
                How long the window is.

        Returns:
            cutoff (str):
                ISO-8601 UTC, written the way the repository writes
                one, so a string comparison in SQL orders correctly.
    """

    return (
        moment.astimezone(timezone.utc) - timedelta(days=days)
    ).isoformat(timespec='seconds')
