#!/usr/bin/env python3
""" Runs, and the opportunities each one resolved. """

# Imports - Python Standard Library
import sqlite3
from typing import Iterable, List, Optional
from uuid import uuid4

# Imports - Local
from .._database import execute, execute_many, query, query_one, transaction
from .._exceptions import ValidationError
from .._logging import get_logger
from .._records import Opportunity, Run, RUN_STATUS_COLLECTING, RUN_STATUSES
from ._common import (
    insert_statement,
    Repository,
    require_row,
    utc_now
)

# Constants
RUN_SELECT = """
    SELECT
        runs.id            AS id,
        runs.calendar      AS calendar,
        runs.window_start  AS window_start,
        runs.window_end    AS window_end,
        runs.status        AS status,
        runs.collected_at  AS collected_at,
        runs.sent_at       AS sent_at,
        COALESCE(
            (
                SELECT MAX(revisions.number)
                FROM revisions
                WHERE revisions.run_id = runs.id
            ),
            0
        ) AS current_revision,
        COALESCE(
            (
                SELECT MAX(change_log.logged_at)
                FROM change_log
                WHERE change_log.run_id = runs.id
            ),
            runs.collected_at
        ) AS revised_at
    FROM runs
"""

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
        revised_at=row['revised_at']
    )


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
        # revision, and the only thing that has happened to it is being
        # collected.
        return Run(
            id=run_id,
            calendar=calendar,
            window_start=window_start,
            window_end=window_end,
            status=RUN_STATUS_COLLECTING,
            collected_at=collected_at,
            sent_at=None,
            current_revision=0,
            revised_at=collected_at
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
            parameters=(run_id,)
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
            )
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

        if status not in RUN_STATUSES:
            message = (
                f'"{status}" is not a run status. Use one of: '
                f'{", ".join(RUN_STATUSES)}.'
            )
            logger.error(message)
            raise ValidationError(message)

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
