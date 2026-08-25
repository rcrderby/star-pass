#!/usr/bin/env python3
""" Statement building and shared values for the repositories.

    What every repository in the package needs and none of them owns:
    the time format their records are stamped with, the two statements
    that are built from a column list rather than written out, and the
    check that a write matched something.

    The column lists live here too, because a copy from one revision to
    the next and an insert into a fresh one have to name the same
    columns in the same order.  Written twice they would drift, and a
    copy that silently dropped a column is the kind of fault that only
    shows up in a revision someone reverted to weeks later.
"""

# Imports - Python Standard Library
import re
import sqlite3
from datetime import datetime, timezone
from typing import Sequence

# Imports - Local
from .._exceptions import ValidationError
from .._logging import get_logger

# Constants
# Columns an event is written with and read back by, in one order, so
# that an insert, a copy and a select cannot drift apart.
EVENT_COLUMNS = (
    'run_id',
    'revision',
    'id',
    'title',
    'date',
    'calendar_start',
    'calendar_end',
    'shift_start',
    'shift_end',
    'category',
    'match_kind',
    'match_keyword',
    'match_score',
    'added_by_hand',
    'collected_category'
)
EVENT_ROLE_COLUMNS = (
    'run_id',
    'revision',
    'event_id',
    'need_id',
    'slots',
    'edited',
    'offset_start',
    'offset_end',
    'max_length',
    'default_slots'
)

# SQLite has no placeholder for a table or a column name, so the two
# statement builders below interpolate those.  Every name they are
# given is a constant in this package and none reaches them from a
# caller, but 'check_identifiers' enforces that rather than trusting
# it: a name that is not a plain lower-case identifier cannot become
# part of a statement.  Values are never interpolated -- they bind
# through placeholders, which is what makes the statements safe.
IDENTIFIER = re.compile(r'^[a-z][a-z0-9_]*$')

# When a run was last worked on, as an expression over 'runs'.  Stated
# once because two callers read it and they have to agree: the run's
# own select publishes it, and the sweep that forgets superseded
# revisions decides by it.  A run one of them called untouched and the
# other called in use is a run whose middle revisions are swept while
# somebody is working on it.
#
# Three sources, not the change log alone.  Sealing a revision and
# reverting to one are both somebody working on the run and both
# deliberately write no change-log entry; what each writes is a
# 'revisions' row.  Collection is the floor, for a run nothing has
# happened to since.  Times are ISO-8601 UTC to the second, so the
# largest string is the latest moment.
#
# 'revisions' is aliased because one caller deletes from that table,
# and a correlated name is easier to trust than a scoping rule.
LAST_TOUCHED = """
    MAX(
        runs.collected_at,
        COALESCE(
            (
                SELECT MAX(change_log.logged_at)
                FROM change_log
                WHERE change_log.run_id = runs.id
            ),
            runs.collected_at
        ),
        COALESCE(
            (
                SELECT MAX(touched.created_at)
                FROM revisions AS touched
                WHERE touched.run_id = runs.id
            ),
            runs.collected_at
        )
    )
"""

# Module logger
logger = get_logger(__name__)


def check_identifiers(
        names: Sequence[str]
) -> None:
    """ Fail unless every name can be part of a statement.

        Args:
            names (Sequence[str]):
                Table and column names about to be interpolated.

        Raises:
            ValidationError:
                If any name is not a plain lower-case identifier.

        Returns:
            None.
    """

    for name in names:
        if not IDENTIFIER.match(name):
            message = f'"{name}" is not a table or column name.'
            logger.error(message)
            raise ValidationError(message)

    return None


class Repository:
    """ What every repository in the package is made of.

        The connection is supplied rather than opened here, so that a
        caller holding several repositories runs them against one
        database, and a transaction opened around a group of calls
        covers all of them.
    """

    def __init__(
            self,
            connection: sqlite3.Connection
    ) -> None:
        """ Store the connection the repository works on.

            Args:
                connection (sqlite3.Connection):
                    An open connection from '_database.connect'.

            Returns:
                None.
        """

        self._connection = connection


def require_one_of(
        value: str,
        allowed: Sequence[str],
        description: str
) -> None:
    """ Fail unless a value is one of a closed set.

        The vocabularies the layer defines -- a run's status, a job's
        kind, the status a job finishes in -- are checked here rather
        than by the database, so that a value the caller chose badly
        comes back as their error naming the alternatives, instead of
        as a constraint violation naming a column.

        Args:
            value (str):
                What the caller supplied.

            allowed (Sequence[str]):
                Every value the layer accepts.

            description (str):
                What the value is, for the message: "a run status".

        Raises:
            ValidationError:
                If the value is not one of 'allowed'.

        Returns:
            None.
    """

    if value not in allowed:
        message = (
            f'"{value}" is not {description}. Use one of: '
            f'{", ".join(allowed)}.'
        )
        logger.error(message)
        raise ValidationError(message)

    return None


def utc_now() -> str:
    """ Return the current time as an ISO-8601 UTC timestamp.

        Args:
            None.

        Returns:
            timestamp (str):
                The current time, to the second, with its offset.
    """

    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def placeholders(
        columns: Sequence[str]
) -> str:
    """ Return a placeholder list matching a column list.

        Args:
            columns (Sequence[str]):
                The columns being written.

        Returns:
            placeholders (str):
                A comma-separated placeholder for each column.
    """

    return ', '.join('?' * len(columns))


def insert_statement(
        table: str,
        columns: Sequence[str],
        or_ignore: bool = False
) -> str:
    """ Return an insert statement for a table and its columns.

        Args:
            table (str):
                Table to insert into.

            columns (Sequence[str]):
                Columns to write, in the order values are supplied.

            or_ignore (bool, optional):
                Whether a row already there should leave the statement
                doing nothing instead of failing.  Defaults to False.
                A caller that asks for this is one for which a row
                already there is an answer rather than a fault, and it
                reads the cursor's row count to tell the two apart.
                It gives way to the primary key and nothing else: a
                foreign key violation is still raised.

        Raises:
            ValidationError:
                If a name is not a table or column name.

        Returns:
            statement (str):
                The insert statement.
    """

    check_identifiers(names=(table, *columns))

    verb = 'INSERT OR IGNORE INTO' if or_ignore else 'INSERT INTO'

    return (
        f'{verb} {table} ({", ".join(columns)}) '  # nosec B608
        f'VALUES ({placeholders(columns)})'
    )


def copy_statement(
        table: str,
        columns: Sequence[str]
) -> str:
    """ Return a statement copying rows into another revision.

        The revision is replaced with a supplied value and every other
        column is carried across unchanged, which is what makes a new
        revision a copy of the one before it.

        Args:
            table (str):
                Table to copy within.

            columns (Sequence[str]):
                Columns to copy, including 'revision'.

        Raises:
            ValidationError:
                If a name is not a table or column name.

        Returns:
            statement (str):
                The insert-select statement, taking the new revision
                number, the run ID and the source revision number.
    """

    check_identifiers(names=(table, *columns))

    selected = [
        '?' if column == 'revision' else column
        for column in columns
    ]

    return (
        f'INSERT INTO {table} ({", ".join(columns)}) '  # nosec B608
        f'SELECT {", ".join(selected)} FROM {table} '
        f'WHERE run_id = ? AND revision = ?'
    )


def require_row(
        cursor: sqlite3.Cursor,
        message: str
) -> None:
    """ Fail when a statement changed nothing.

        A write that matches no row is not a database failure: the
        values named something that is not there, which is the caller's
        to fix.

        Args:
            cursor (sqlite3.Cursor):
                Cursor the statement ran on.

            message (str):
                What to tell the caller.

        Raises:
            ValidationError:
                If no row was affected.

        Returns:
            None.
    """

    if cursor.rowcount == 0:
        logger.error(message)
        raise ValidationError(message)

    return None
