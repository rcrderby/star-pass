#!/usr/bin/env python3
""" Titles the data model did not match, kept for the next model edit.

    An event whose title matches no category is collected under the
    fallback, which has no need IDs, so it blocks the send and is
    named.  That is enough to get one run out of the door.  What it is
    not enough for is the next edit of 'shift_info.yml', which wants
    every title that has wanted an alias -- across runs, and after the
    run that showed it has been superseded.

    So this belongs to no run.  A row records **one sighting**, and a
    run contributes at most one of them per title: a window holding
    the same unmatched title four times saw one title, and collecting
    that window again is the same window read twice rather than a
    title that came back.  What the count therefore measures is how
    many **runs** a title turned up in -- which is the question being
    asked of it, since a title that turns up every month is a category
    the model is missing and one that turned up once is an event that
    happened once.  A sighting recorded by hand against no run is
    always a new one, because nothing else can say it is the same.

    Read back, the sightings are counted into one entry per title,
    because a list showing the same title eleven times is a list
    nobody works through.

    Nothing here updates a row.  One thing deletes them, and only
    together: retention forgets a title outright once the decision has
    been made -- once the model matches it, which is what recording it
    was for -- or once nothing has seen it for a very long time.  A
    title is forgotten whole rather than sighting by sighting, because
    the count means the runs a title turned up in, and a count that
    lost its early rows would say a recurring title were a new one
    (D20).
"""

# Imports - Python Standard Library
import sqlite3
from typing import List, Optional

# Imports - Local
from .._database import execute, query, query_one, transaction
from .._logging import get_logger
from .._records import UnmatchedTitle
from ._common import insert_statement, Repository, utc_now

# Constants
# Columns a sighting is written with.
UNMATCHED_COLUMNS = (
    'calendar',
    'title',
    'run_id',
    'recorded_at',
    'principal_id'
)

# One entry per title in a calendar, with its sightings counted.
# Derived in the statement that reads them rather than by whoever
# displays one, for the reason a run's counts are: a caller asking
# what the model is missing should not read every row to find out.
UNMATCHED_SELECT = """
    SELECT
        calendar             AS calendar,
        title                AS title,
        COUNT(*)             AS times_seen,
        MIN(recorded_at)     AS first_seen,
        MAX(recorded_at)     AS last_seen
    FROM unmatched_titles
"""

# Newest first, so the titles that have just started turning up are
# read before the ones somebody has already decided about.  By the
# most recent sighting's own row rather than by its time: the times
# this layer records are whole seconds, and two sightings a moment
# apart would otherwise come back in an order nothing decided.
UNMATCHED_ORDER = 'ORDER BY MAX(id) DESC'

# Module logger
logger = get_logger(__name__)


def _to_unmatched(
        row: sqlite3.Row
) -> UnmatchedTitle:
    """ Build an unmatched title from a row.

        Args:
            row (sqlite3.Row):
                A grouped row of sightings.

        Returns:
            unmatched (UnmatchedTitle):
                The title the row describes.
    """

    return UnmatchedTitle(
        calendar=row['calendar'],
        title=row['title'],
        times_seen=row['times_seen'],
        first_seen=row['first_seen'],
        last_seen=row['last_seen']
    )


class UnmatchedTitleRepository(Repository):
    """ Titles the data model did not match, and how often.

        Written a sighting at a time and read as one entry per title,
        which is why nothing here returns a row: a row on its own says
        only that somebody once saw a title, and the question being
        asked is which titles keep turning up.
    """

    def record(
            self,
            calendar: str,
            title: str,
            principal_id: str,
            run_id: Optional[str] = None
    ) -> UnmatchedTitle:
        """ Record one sighting of a title the model did not match.

            A run that has already recorded the title records nothing
            further.  The rule is here rather than left to the caller
            because both callers would otherwise have to know it, and
            the one that most needs it is the collection: collecting a
            window again is how a corrected model is picked up, so a
            count that grew with every recollection would report the
            operator's own fixing as the title coming back.

            Args:
                calendar (str):
                    Which configured calendar it was seen in.

                title (str):
                    The title, as the calendar gave it.

                principal_id (str):
                    Who recorded it (D13).

                run_id (str, optional):
                    The run it was noticed in, or None when it was not
                    noticed in one.  Defaults to None.

            Raises:
                UpstreamError:
                    If the sighting cannot be written.

            Returns:
                unmatched (UnmatchedTitle):
                    The title as the log now holds it, this sighting
                    included.
        """

        with transaction(connection=self._connection):
            if not self._recorded_by(
                run_id=run_id,
                calendar=calendar,
                title=title
            ):
                execute(
                    connection=self._connection,
                    statement=insert_statement(
                        table='unmatched_titles',
                        columns=UNMATCHED_COLUMNS
                    ),
                    parameters=(
                        calendar,
                        title,
                        run_id,
                        utc_now(),
                        principal_id
                    )
                )

                message = (
                    'Recorded an unmatched title in the '
                    f'"{calendar}" calendar'
                )
                logger.info(message)

        # Read back rather than assembled here: what the caller is
        # given is the count over every sighting, and this one is not
        # the only one.
        return self.get(calendar=calendar, title=title)

    def _recorded_by(
            self,
            run_id: Optional[str],
            calendar: str,
            title: str
    ) -> bool:
        """ Return whether a run has already recorded a title.

            Args:
                run_id (str | None):
                    Run to ask about, or None for a sighting recorded
                    against no run, which nothing can be the same as.

                calendar (str):
                    Which configured calendar it was seen in.

                title (str):
                    The title.

            Raises:
                UpstreamError:
                    If the log cannot be read.

            Returns:
                recorded (bool):
                    Whether that run's sighting is already there.
        """

        if run_id is None:
            return False

        return query_one(
            connection=self._connection,
            statement=(
                'SELECT 1 FROM unmatched_titles '
                'WHERE run_id = ? AND calendar = ? AND title = ? '
                'LIMIT 1'
            ),
            parameters=(run_id, calendar, title)
        ) is not None

    def get(
            self,
            calendar: str,
            title: str
    ) -> Optional[UnmatchedTitle]:
        """ Return one title's sightings, counted.

            Args:
                calendar (str):
                    Which configured calendar it was seen in.

                title (str):
                    The title to read.

            Raises:
                UpstreamError:
                    If it cannot be read.

            Returns:
                unmatched (UnmatchedTitle | None):
                    The title, or None when nothing has recorded one.
        """

        row = query_one(
            connection=self._connection,
            statement=(
                f'{UNMATCHED_SELECT} '
                'WHERE calendar = ? AND title = ? '
                'GROUP BY calendar, title'
            ),
            parameters=(calendar, title)
        )

        return _to_unmatched(row=row) if row is not None else None

    def forget(
            self,
            calendar: str,
            title: str
    ) -> int:
        """ Delete every sighting of one title in one calendar.

            All of them or none: what a caller reads is one entry per
            title with its sightings counted, so removing some would
            leave the same title reporting a smaller number rather
            than leaving nothing.  Whether a title should be forgotten
            is not decided here -- it needs the data model, which this
            layer does not read.

            Args:
                calendar (str):
                    Calendar the title was seen in.

                title (str):
                    The title to forget.

            Raises:
                UpstreamError:
                    If the sightings cannot be removed.

            Returns:
                removed (int):
                    How many sightings were deleted.
        """

        cursor = execute(
            connection=self._connection,
            statement=(
                'DELETE FROM unmatched_titles '
                'WHERE calendar = ? AND title = ?'
            ),
            parameters=(calendar, title)
        )

        return cursor.rowcount

    def list_all(self) -> List[UnmatchedTitle]:
        """ Return every title the model has not matched, newest first.

            Args:
                None.

            Raises:
                UpstreamError:
                    If they cannot be read.

            Returns:
                unmatched (List[UnmatchedTitle]):
                    One entry per title in a calendar.
        """

        rows = query(
            connection=self._connection,
            statement=(
                f'{UNMATCHED_SELECT} '
                f'GROUP BY calendar, title {UNMATCHED_ORDER}'
            )
        )

        return [_to_unmatched(row=row) for row in rows]
