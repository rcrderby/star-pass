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
    'added_by_hand'
)
EVENT_ROLE_COLUMNS = (
    'run_id',
    'revision',
    'event_id',
    'need_id',
    'slots',
    'edited'
)

# SQLite has no placeholder for a table or a column name, so the two
# statement builders below interpolate those.  Every name they are
# given is a constant in this package and none reaches them from a
# caller, but 'check_identifiers' enforces that rather than trusting
# it: a name that is not a plain lower-case identifier cannot become
# part of a statement.  Values are never interpolated -- they bind
# through placeholders, which is what makes the statements safe.
IDENTIFIER = re.compile(r'^[a-z][a-z0-9_]*$')

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
        columns: Sequence[str]
) -> str:
    """ Return an insert statement for a table and its columns.

        Args:
            table (str):
                Table to insert into.

            columns (Sequence[str]):
                Columns to write, in the order values are supplied.

        Raises:
            ValidationError:
                If a name is not a table or column name.

        Returns:
            statement (str):
                The insert statement.
    """

    check_identifiers(names=(table, *columns))

    return (
        f'INSERT INTO {table} ({", ".join(columns)}) '  # nosec B608
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
