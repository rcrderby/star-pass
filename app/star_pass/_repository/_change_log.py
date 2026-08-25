#!/usr/bin/env python3
""" A run's change log, appended to and never edited. """

# Imports - Python Standard Library
import sqlite3
from dataclasses import replace
from typing import List

# Imports - Local
from .._database import execute, query
from .._logging import get_logger
from .._records import LogEntry
from ._common import insert_statement, Repository, utc_now

# What an entry is written with, in the order its values bind.
LOG_COLUMNS = (
    'run_id',
    'revision',
    'logged_at',
    'principal_id',
    'action',
    'subject',
    'subject_count',
    'category',
    'shift_time',
    'minutes',
    'slots',
    'need_id'
)

# Module logger
logger = get_logger(__name__)


def _to_log_entry(
        row: sqlite3.Row
) -> LogEntry:
    """ Build a change log record from a row.

        Args:
            row (sqlite3.Row):
                A row from the change log table.

        Returns:
            entry (LogEntry):
                The entry the row describes.
    """

    return LogEntry(
        id=row['id'],
        run_id=row['run_id'],
        revision=row['revision'],
        logged_at=row['logged_at'],
        principal_id=row['principal_id'],
        action=row['action'],
        subject=row['subject'],
        subject_count=row['subject_count'],
        category=row['category'],
        shift_time=row['shift_time'],
        minutes=row['minutes'],
        slots=row['slots'],
        need_id=row['need_id']
    )


class ChangeLogRepository(Repository):
    """ A run's change log, appended to and never edited.

        The log is written where the change is made rather than
        assembled by whatever is displaying it, so it survives a reload
        and reads the same in a browser and a terminal.
    """

    def add(
            self,
            run_id: str,
            revision: int,
            principal_id: str,
            recorded: LogEntry
    ) -> LogEntry:
        """ Append one entry to a run's change log.

            The entry arrives as a record rather than as a column per
            value, because which values an action carries is the
            action's own business: a signature naming all of them
            would grow every time one is added, and every caller would
            pass most of them as None.

            Args:
                run_id (str):
                    Run the entry belongs to.

                revision (int):
                    Revision that was current when the change was made.

                principal_id (str):
                    Who made the change.

                recorded (LogEntry):
                    What was done and the values it carried.  Its
                    identifier, run, revision, time and principal are
                    ignored: those are this method's to set.

            Raises:
                ValidationError:
                    If there is no such run.

                UpstreamError:
                    If the entry cannot be written.

            Returns:
                entry (LogEntry):
                    The entry as stored, with the identifier it was
                    given.
        """

        stored = replace(
            recorded,
            id=0,
            run_id=run_id,
            revision=revision,
            logged_at=utc_now(),
            principal_id=principal_id
        )

        cursor = execute(
            connection=self._connection,
            statement=insert_statement(
                table='change_log',
                columns=LOG_COLUMNS
            ),
            parameters=(
                stored.run_id,
                stored.revision,
                stored.logged_at,
                stored.principal_id,
                stored.action,
                stored.subject,
                stored.subject_count,
                stored.category,
                stored.shift_time,
                stored.minutes,
                stored.slots,
                stored.need_id
            )
        )

        return replace(stored, id=cursor.lastrowid or 0)

    def list_all(
            self,
            run_id: str
    ) -> List[LogEntry]:
        """ Return a run's change log, oldest entry first.

            Ordered by identifier rather than by time: entries made in
            the same second have to keep the order they were made in,
            and the identifier always ascends.

            Args:
                run_id (str):
                    Run to read the log of.

            Raises:
                UpstreamError:
                    If the log cannot be read.

            Returns:
                entries (List[LogEntry]):
                    Every entry for the run, in order.
        """

        rows = query(
            connection=self._connection,
            statement=(
                'SELECT * FROM change_log WHERE run_id = ? ORDER BY id'
            ),
            parameters=(run_id,)
        )

        return [_to_log_entry(row=row) for row in rows]
