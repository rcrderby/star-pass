#!/usr/bin/env python3
""" Forgetting what a run leaves behind, on a policy.

    Four things are swept, each on its own window:

    - a **job's event log**, which names volunteers and the times they
      were asked to be somewhere; the job row outlives it;
    - a **revision**, except the first and the current one;
    - an **abandoned idempotency reservation**, one that recorded no
      response, which every replay of its key is told is still
      running;
    - an **unmatched title**, once the data model matches it, with age
      only a backstop.

    **The sent record is never forgotten** and has no window here.
    Duplicate safety reads it to know which rows a run already
    created.

    Nothing here is reachable over the API: retention removes a run's
    leavings, a caller does not.
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
    IdempotencyRepository,
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

            idempotency_keys (int):
                Reservations deleted that never recorded a response.
    """

    job_events: int = 0
    revisions: int = 0
    unmatched_titles: int = 0
    idempotency_keys: int = 0

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
            or self.idempotency_keys
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
        ),
        idempotency_keys=IdempotencyRepository(
            connection=connection
        ).forget_abandoned(
            cutoff=_before(
                moment=moment,
                hours=_defaults.RETENTION_ABANDONED_KEY_HOURS
            )
        )
    )

    if swept:
        message = (
            f'Retention removed {swept.job_events} job event(s), '
            f'{swept.revisions} revision(s), '
            f'{swept.unmatched_titles} unmatched title sighting(s) '
            f'and {swept.idempotency_keys} abandoned reservation(s).'
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
        days: int = 0,
        hours: int = 0
) -> str:
    """ Return the timestamp a window reaches back to.

        Args:
            moment (datetime):
                What to measure back from.

            days (int, optional):
                How many days the window is.

            hours (int, optional):
                How many hours the window is.

        Returns:
            cutoff (str):
                ISO-8601 UTC, written the way the repository writes
                one, so a string comparison in SQL orders correctly.
    """

    return (
        moment.astimezone(timezone.utc)
        - timedelta(days=days, hours=hours)
    ).isoformat(timespec='seconds')
