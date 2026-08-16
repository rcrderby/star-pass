#!/usr/bin/env python3
""" Runs, and the opportunities each one resolved. """

# Imports - Python Standard Library
import sqlite3
from typing import Any, Iterable, List, Optional, Tuple
from uuid import uuid4

# Imports - Local
from .._database import execute, execute_many, query, query_one, transaction
from .._logging import get_logger
from .._records import (
    JOB_STATUSES_UNFINISHED,
    Opportunity,
    Run,
    RUN_STATUS_COLLECTING,
    RUN_STATUSES
)
from ._common import (
    insert_statement,
    Repository,
    require_one_of,
    require_row,
    utc_now
)

# Constants
# An 'IN' list has one placeholder per value and SQLite has no way to
# bind a whole list, so the placeholders are counted out here.  What is
# interpolated is question marks and commas; the statuses themselves
# bind like every other value.
UNFINISHED_PLACEHOLDERS = ', '.join('?' * len(JOB_STATUSES_UNFINISHED))

# Everything a caller reads about a run that the run's own row cannot
# say.  All of it is derived, and all of it is derived here rather than
# by whoever is displaying a run, so that the runs list costs one query
# however many runs it holds: read per run instead, a list of thirty
# runs would be a hundred and twenty queries.
#
# The current revision is joined rather than sub-selected per column,
# so that "the current revision" is defined once and the three counts
# below cannot drift from each other or from 'current_revision'.  A run
# that has not reached its first revision joins to nothing: the
# revision number reads through COALESCE, and the counts match no row
# and come back as zero, which is what a run with no events holds.
#
# Nothing stops a run holding two unfinished jobs, so the active one is
# the most recently created.  Ordered by 'rowid' rather than by
# 'created_at': the stamp is written to the second, so two jobs asked
# for in the same second would tie and be separated by whichever
# identifier sorted higher, and a job identifier is a random value.
# The rowid ascends in the order rows were written, which is the order
# the jobs were asked for.
RUN_SELECT = f"""
    SELECT
        runs.id            AS id,
        runs.calendar      AS calendar,
        runs.window_start  AS window_start,
        runs.window_end    AS window_end,
        runs.status        AS status,
        runs.collected_at  AS collected_at,
        runs.sent_at       AS sent_at,
        COALESCE(current.number, 0) AS current_revision,
        COALESCE(
            (
                SELECT MAX(change_log.logged_at)
                FROM change_log
                WHERE change_log.run_id = runs.id
            ),
            runs.collected_at
        ) AS revised_at,
        (
            SELECT COUNT(*)
            FROM events
            WHERE events.run_id = runs.id
              AND events.revision = current.number
        ) AS event_count,
        (
            SELECT COUNT(*)
            FROM event_roles
            WHERE event_roles.run_id = runs.id
              AND event_roles.revision = current.number
        ) AS shift_count,
        (
            SELECT COUNT(*)
            FROM events
            WHERE events.run_id = runs.id
              AND events.revision = current.number
              AND NOT EXISTS (
                  SELECT 1
                  FROM event_roles
                  WHERE event_roles.run_id = events.run_id
                    AND event_roles.revision = events.revision
                    AND event_roles.event_id = events.id
              )
        ) AS unmatched_count,
        (
            SELECT jobs.id
            FROM jobs
            WHERE jobs.run_id = runs.id
              AND jobs.status IN ({UNFINISHED_PLACEHOLDERS})
            ORDER BY jobs.rowid DESC
            LIMIT 1
        ) AS active_job_id
    FROM runs
    LEFT JOIN (
        SELECT
            revisions.run_id      AS run_id,
            MAX(revisions.number) AS number
        FROM revisions
        GROUP BY revisions.run_id
    ) AS current ON current.run_id = runs.id
"""  # nosec B608

# Module logger
logger = get_logger(__name__)


def _to_run(
        row: sqlite3.Row
) -> Run:
    """ Build a run record from a row.

        Args:
            row (sqlite3.Row):
                A row from 'RUN_SELECT'.

        Returns:
            run (Run):
                The run the row describes.
    """

    return Run(
        id=row['id'],
        calendar=row['calendar'],
        window_start=row['window_start'],
        window_end=row['window_end'],
        status=row['status'],
        collected_at=row['collected_at'],
        sent_at=row['sent_at'],
        current_revision=row['current_revision'],
        revised_at=row['revised_at'],
        event_count=row['event_count'],
        shift_count=row['shift_count'],
        unmatched_count=row['unmatched_count'],
        active_job_id=row['active_job_id']
    )


def _run_parameters(
        *rest: Any
) -> Tuple:
    """ Return what 'RUN_SELECT' binds, followed by a caller's own.

        'RUN_SELECT' binds values of its own -- the statuses a job is
        still in hand under -- and they come first because that is
        where their placeholders are in the statement.  Built here so
        that a caller adding a clause supplies only what the clause
        needs and cannot get the order wrong.

        Args:
            *rest (Any):
                Values the caller's own clauses bind, in their order.

        Returns:
            parameters (Tuple):
                Every value the statement binds, in order.
    """

    return (*JOB_STATUSES_UNFINISHED, *rest)


def _to_opportunity(
        row: sqlite3.Row
) -> Opportunity:
    """ Build an opportunity record from a row.

        Args:
            row (sqlite3.Row):
                A row from the opportunities table.

        Returns:
            opportunity (Opportunity):
                The opportunity the row describes.
    """

    return Opportunity(
        need_id=row['need_id'],
        title=row['title'],
        url=row['url'],
        max_length=row['max_length'],
        offset_start=row['offset_start'],
        offset_end=row['offset_end'],
        default_slots=row['default_slots']
    )


class RunRepository(Repository):
    """ Runs, and the opportunities each one resolved.

        The opportunities belong to the run rather than to a repository
        of their own: they are resolved once while the run is collected
        and are replaced as a set, never edited one at a time.
    """

    def create(
            self,
            *,
            calendar: str,
            window_start: str,
            window_end: str
    ) -> Run:
        """ Create a run and mint its identifier.

            The identifier is minted here rather than supplied, so that
            nothing outside the server decides what a run is called.

            Args:
                calendar (str):
                    Which configured calendar is being collected.

                window_start (str):
                    First day the run covers, as an ISO date.

                window_end (str):
                    Day after the last day it covers, as an ISO date.

            Raises:
                UpstreamError:
                    If the run cannot be written.

            Returns:
                run (Run):
                    The run as stored, with no revision yet.
        """

        run_id = uuid4().hex
        collected_at = utc_now()

        execute(
            connection=self._connection,
            statement=insert_statement(
                table='runs',
                columns=(
                    'id',
                    'calendar',
                    'window_start',
                    'window_end',
                    'status',
                    'collected_at'
                )
            ),
            parameters=(
                run_id,
                calendar,
                window_start,
                window_end,
                RUN_STATUS_COLLECTING,
                collected_at
            )
        )

        message = f'Created run {run_id} for calendar "{calendar}"'
        logger.debug(message)

        # The derived columns are known for a run this new: it has no
        # revision and so nothing to count, and the only thing that has
        # happened to it is being collected.  A job for it is created
        # after the run it works on, so there is not one yet either.
        return Run(
            id=run_id,
            calendar=calendar,
            window_start=window_start,
            window_end=window_end,
            status=RUN_STATUS_COLLECTING,
            collected_at=collected_at,
            sent_at=None,
            current_revision=0,
            revised_at=collected_at,
            event_count=0,
            shift_count=0,
            unmatched_count=0,
            active_job_id=None
        )

    def get(
            self,
            run_id: str
    ) -> Optional[Run]:
        """ Return one run.

            Args:
                run_id (str):
                    Identifier of the run to read.

            Raises:
                UpstreamError:
                    If the run cannot be read.

            Returns:
                run (Run | None):
                    The run, or None when there is no such run.
        """

        row = query_one(
            connection=self._connection,
            statement=f'{RUN_SELECT} WHERE runs.id = ?',
            parameters=_run_parameters(run_id)
        )

        return _to_run(row=row) if row is not None else None

    def list_all(self) -> List[Run]:
        """ Return every run, most recently collected first.

            Args:
                None.

            Raises:
                UpstreamError:
                    If the runs cannot be read.

            Returns:
                runs (List[Run]):
                    Every run, newest first.
        """

        rows = query(
            connection=self._connection,
            statement=(
                f'{RUN_SELECT} '
                'ORDER BY runs.collected_at DESC, runs.id'
            ),
            parameters=_run_parameters()
        )

        return [_to_run(row=row) for row in rows]

    def set_status(
            self,
            run_id: str,
            status: str,
            sent_at: Optional[str] = None
    ) -> None:
        """ Record what has become of a run.

            The send time is set with the status rather than by a call
            of its own, because a run becoming sent and the time it was
            sent are one fact.  Passing None leaves an existing send
            time alone: nothing un-sends a run.

            Args:
                run_id (str):
                    Identifier of the run to update.

                status (str):
                    One of 'RUN_STATUSES'.

                sent_at (str, optional):
                    When shifts reached Amplify, as an ISO-8601 UTC
                    timestamp.  Defaults to None, which leaves the
                    stored value unchanged.

            Raises:
                ValidationError:
                    If the status is not one the run can hold, or there
                    is no such run.

                UpstreamError:
                    If the run cannot be updated.

            Returns:
                None.
        """

        require_one_of(
            value=status,
            allowed=RUN_STATUSES,
            description='a run status'
        )

        cursor = execute(
            connection=self._connection,
            statement=(
                'UPDATE runs '
                'SET status = ?, sent_at = COALESCE(?, sent_at) '
                'WHERE id = ?'
            ),
            parameters=(status, sent_at, run_id)
        )

        require_row(
            cursor=cursor,
            message=f'There is no run with the ID "{run_id}".'
        )

        return None

    def set_opportunities(
            self,
            run_id: str,
            opportunities: Iterable[Opportunity]
    ) -> None:
        """ Replace the opportunities a run resolved.

            Replaced as a set rather than merged: they are read from
            Amplify together, and a title that disappeared between
            reads should disappear here too.

            Args:
                run_id (str):
                    Identifier of the run.

                opportunities (Iterable[Opportunity]):
                    Every opportunity the run touches.

            Raises:
                ValidationError:
                    If there is no such run.

                UpstreamError:
                    If they cannot be written.

            Returns:
                None.
        """

        columns = (
            'run_id',
            'need_id',
            'title',
            'url',
            'max_length',
            'offset_start',
            'offset_end',
            'default_slots'
        )

        with transaction(connection=self._connection):
            execute(
                connection=self._connection,
                statement='DELETE FROM opportunities WHERE run_id = ?',
                parameters=(run_id,)
            )
            execute_many(
                connection=self._connection,
                statement=insert_statement(
                    table='opportunities',
                    columns=columns
                ),
                parameters=[
                    (
                        run_id,
                        opportunity.need_id,
                        opportunity.title,
                        opportunity.url,
                        opportunity.max_length,
                        opportunity.offset_start,
                        opportunity.offset_end,
                        opportunity.default_slots
                    )
                    for opportunity in opportunities
                ]
            )

        return None

    def get_opportunities(
            self,
            run_id: str
    ) -> List[Opportunity]:
        """ Return the opportunities a run resolved.

            Args:
                run_id (str):
                    Identifier of the run.

            Raises:
                UpstreamError:
                    If they cannot be read.

            Returns:
                opportunities (List[Opportunity]):
                    Every opportunity stored for the run, by need ID.
        """

        rows = query(
            connection=self._connection,
            statement=(
                'SELECT * FROM opportunities '
                'WHERE run_id = ? ORDER BY need_id'
            ),
            parameters=(run_id,)
        )

        return [_to_opportunity(row=row) for row in rows]

    def delete(
            self,
            run_id: str
    ) -> None:
        """ Delete a run and everything belonging to it.

            Used by the retention policy, which is the only thing that
            removes a run: a caller cannot ask for one to be deleted.

            Args:
                run_id (str):
                    Identifier of the run to delete.

            Raises:
                UpstreamError:
                    If the run cannot be deleted.

            Returns:
                None.
        """

        execute(
            connection=self._connection,
            statement='DELETE FROM runs WHERE id = ?',
            parameters=(run_id,)
        )

        return None
