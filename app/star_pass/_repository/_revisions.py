#!/usr/bin/env python3
""" The numbered versions of a run's events. """

# Imports - Python Standard Library
import sqlite3
from typing import List, Optional

# Imports - Local
from .._database import execute, query, query_one, transaction
from .._exceptions import ValidationError
from .._logging import get_logger
from .._records import Revision
from ._common import (
    copy_statement,
    EVENT_COLUMNS,
    EVENT_ROLE_COLUMNS,
    insert_statement,
    Repository,
    utc_now
)

# Constants
# A revision and the count of what was done while it was current.
# Derived in the statement that reads a revision rather than by
# whoever displays one, so a run's whole history costs one query
# however many revisions it holds.
REVISION_SELECT = """
    SELECT
        revisions.run_id      AS run_id,
        revisions.number      AS number,
        revisions.created_at  AS created_at,
        revisions.label       AS label,
        (
            SELECT COUNT(*)
            FROM change_log
            WHERE change_log.run_id = revisions.run_id
              AND change_log.revision = revisions.number
        ) AS change_count
    FROM revisions
"""

# Module logger
logger = get_logger(__name__)


def _to_revision(
        row: sqlite3.Row
) -> Revision:
    """ Build a revision record from a row.

        Args:
            row (sqlite3.Row):
                A row from the revisions table.

        Returns:
            revision (Revision):
                The revision the row describes.
    """

    return Revision(
        run_id=row['run_id'],
        number=row['number'],
        created_at=row['created_at'],
        label=row['label'],
        change_count=row['change_count']
    )


class RevisionRepository(Repository):
    """ The numbered versions of a run's events.

        A revision is created by copying the current one, so editing
        never destroys what came before it, and reverting is another
        forward step rather than an undo: it adds a revision holding a
        copy of the one being reverted to.
    """

    def create(
            self,
            run_id: str,
            label: str,
            replacing: bool = False
    ) -> Revision:
        """ Add a revision, continuing from the current one or replacing it.

            An edit continues: the new revision holds a copy, so what
            was there is still there and only the edit differs.  A
            collection replaces: what the calendar says now is the
            whole of it, and carrying the old events forward would
            leave behind ones the calendar no longer has.

            The first revision of a run has nothing to copy either
            way.

            Args:
                run_id (str):
                    Run to add the revision to.

                label (str):
                    How to name the revision to a reader.

                replacing (bool, optional):
                    Whether the revision starts empty rather than
                    holding a copy of the current one.  Defaults to
                    False, which continues from it.

            Raises:
                ValidationError:
                    If there is no such run.

                UpstreamError:
                    If the revision cannot be written.

            Returns:
                revision (Revision):
                    The revision that was added, now the current one.
        """

        with transaction(connection=self._connection):
            current = self._current_number(run_id=run_id)

            return self._add(
                run_id=run_id,
                label=label,
                source=None if replacing else (current or None)
            )

    def revert_to(
            self,
            run_id: str,
            number: int,
            label: str
    ) -> Revision:
        """ Add a revision holding a copy of an earlier one.

            Nothing is deleted: the revisions between the two stay
            readable, so the record of what was done to a run survives
            being undone.

            Args:
                run_id (str):
                    Run to revert.

                number (int):
                    Revision to copy.

                label (str):
                    How to name the new revision to a reader.

            Raises:
                ValidationError:
                    If the run has no such revision.

                UpstreamError:
                    If the revision cannot be written.

            Returns:
                revision (Revision):
                    The revision that was added, now the current one.
        """

        with transaction(connection=self._connection):
            if self.get(run_id=run_id, number=number) is None:
                message = (
                    f'Run "{run_id}" has no revision {number} to '
                    'revert to.'
                )
                logger.error(message)
                raise ValidationError(message)

            return self._add(
                run_id=run_id,
                label=label,
                source=number
            )

    def get(
            self,
            run_id: str,
            number: int
    ) -> Optional[Revision]:
        """ Return one revision.

            Args:
                run_id (str):
                    Run the revision belongs to.

                number (int):
                    Which revision to read.

            Raises:
                UpstreamError:
                    If the revision cannot be read.

            Returns:
                revision (Revision | None):
                    The revision, or None when there is no such one.
        """

        row = query_one(
            connection=self._connection,
            statement=(
                f'{REVISION_SELECT} '
                'WHERE revisions.run_id = ? AND revisions.number = ?'
            ),
            parameters=(run_id, number)
        )

        return _to_revision(row=row) if row is not None else None

    def list_all(
            self,
            run_id: str
    ) -> List[Revision]:
        """ Return a run's revisions, oldest first.

            Args:
                run_id (str):
                    Run to read the revisions of.

            Raises:
                UpstreamError:
                    If they cannot be read.

            Returns:
                revisions (List[Revision]):
                    Every revision of the run, in order.
        """

        rows = query(
            connection=self._connection,
            statement=(
                f'{REVISION_SELECT} '
                'WHERE revisions.run_id = ? ORDER BY revisions.number'
            ),
            parameters=(run_id,)
        )

        return [_to_revision(row=row) for row in rows]

    def delete(
            self,
            run_id: str,
            number: int
    ) -> None:
        """ Delete one revision and the events in it.

            Used by the retention policy, which deletes a superseded
            revision once it is no longer reachable.

            Args:
                run_id (str):
                    Run the revision belongs to.

                number (int):
                    Which revision to delete.

            Raises:
                UpstreamError:
                    If the revision cannot be deleted.

            Returns:
                None.
        """

        execute(
            connection=self._connection,
            statement=(
                'DELETE FROM revisions '
                'WHERE run_id = ? AND number = ?'
            ),
            parameters=(run_id, number)
        )

        return None

    def _add(
            self,
            run_id: str,
            label: str,
            source: Optional[int]
    ) -> Revision:
        """ Add the next revision, optionally copying an earlier one.

            Args:
                run_id (str):
                    Run to add the revision to.

                label (str):
                    How to name the revision to a reader.

                source (int, optional):
                    Revision to copy the events of, or None to start
                    the revision empty.

            Raises:
                ValidationError:
                    If there is no such run.

                UpstreamError:
                    If the revision cannot be written.

            Returns:
                revision (Revision):
                    The revision that was added.
        """

        with transaction(connection=self._connection):
            number = self._current_number(run_id=run_id) + 1
            created_at = utc_now()

            execute(
                connection=self._connection,
                statement=insert_statement(
                    table='revisions',
                    columns=('run_id', 'number', 'created_at', 'label')
                ),
                parameters=(run_id, number, created_at, label)
            )

            if source is not None:
                # Events first: a role points at an event, so copying
                # the roles before them would break the reference.
                for table, columns in (
                    ('events', EVENT_COLUMNS),
                    ('event_roles', EVENT_ROLE_COLUMNS)
                ):
                    execute(
                        connection=self._connection,
                        statement=copy_statement(
                            table=table,
                            columns=columns
                        ),
                        parameters=(number, run_id, source)
                    )

        message = f'Added revision {number} to run {run_id}'
        logger.debug(message)

        # A revision this new is one nothing has been done in yet:
        # the changes it will count are the ones made from now on.
        return Revision(
            run_id=run_id,
            number=number,
            created_at=created_at,
            label=label,
            change_count=0
        )

    def _current_number(
            self,
            run_id: str
    ) -> int:
        """ Return a run's highest revision number.

            Args:
                run_id (str):
                    Run to read.

            Raises:
                UpstreamError:
                    If the number cannot be read.

            Returns:
                number (int):
                    The current revision number, or 0 when the run has
                    no revision yet.
        """

        row = query_one(
            connection=self._connection,
            statement=(
                'SELECT COALESCE(MAX(number), 0) AS number '
                'FROM revisions WHERE run_id = ?'
            ),
            parameters=(run_id,)
        )

        return row['number'] if row is not None else 0
