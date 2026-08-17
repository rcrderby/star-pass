#!/usr/bin/env python3
""" SQLite connection, schema and statement helpers.

    The database is a backing service attached by an environment
    variable, so a deployment can point it at a mounted volume without
    a code change.  This module owns everything SQLite-specific that is
    not a query: opening a connection, the pragmas that make one behave,
    the schema, and the two helpers every query goes through.

    It is the lower half of the repository layer.  '_repository' holds
    the statements and the records they produce; nothing above either
    module sees a cursor, a row or an exception from 'sqlite3'.

    A failure here reaches a caller as one of the core's own exceptions,
    chosen by what the caller can do about it: a database that cannot be
    opened is a deployment to fix (ConfigurationError), a constraint the
    values violated is data to correct (ValidationError), and anything
    else is a backing service that failed (UpstreamError).  Those are
    the same three distinctions the rest of the core already makes, so
    the repository layer adds no exception of its own.
"""

# Imports - Python Standard Library
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, List, Optional, Sequence

# Imports - Local
from . import _defaults
from ._exceptions import (
    ConfigurationError,
    StarPassError,
    UpstreamError,
    ValidationError
)
from ._logging import get_logger

# Constants
DATABASE_FILE = _defaults.DATABASE_FILE
DATABASE_BUSY_TIMEOUT = _defaults.DATABASE_BUSY_TIMEOUT

# Version of the schema this module creates, held in the database's
# 'user_version' pragma.  An empty database is created at this version,
# one already at it is used as it is, and an earlier one is carried
# forward.  A later one means the file was written by a newer version
# of the application, which is a deployment problem rather than
# something to guess at.
SCHEMA_VERSION = 4

# Pragmas applied to every connection.  'foreign_keys' is off by
# default and is per-connection rather than stored in the file, so
# every connection has to ask for it or the cascades below never fire.
# 'journal_mode' is stored in the file; setting it each time is
# harmless and means a database created elsewhere still ends up in
# write-ahead logging, where a reader does not block the writer.
# 'synchronous = NORMAL' is the durability setting write-ahead logging
# is designed for: a crash cannot corrupt the database, and the only
# loss is the most recent transactions after an operating system
# failure.
CONNECTION_PRAGMAS = (
    'PRAGMA foreign_keys = ON',
    'PRAGMA journal_mode = WAL',
    'PRAGMA synchronous = NORMAL'
)

# The schema.  Times are ISO-8601 strings: SQLite has no date type, and
# a sortable text format keeps ordering and comparison working in SQL.
# A timestamp the application records is UTC; a window bound is a plain
# local date, because a window is a run of calendar days in the
# league's own time zone rather than an instant.
#
# Only facts are stored.  A shift's length, whether an opportunity's
# maximum shortened it, which events collide, and the counts on a run
# are all derived from these columns by the code that reads them;
# storing a derived value is storing a second copy that can disagree.
# A run's current revision and the time it was last revised are derived
# for the same reason: the highest revision number is by definition the
# current one, and the newest change log entry is by definition the
# last time anything changed.
SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS runs (
        id            TEXT NOT NULL PRIMARY KEY,
        calendar      TEXT NOT NULL,
        window_start  TEXT NOT NULL,
        window_end    TEXT NOT NULL,
        status        TEXT NOT NULL,
        collected_at  TEXT NOT NULL,
        sent_at       TEXT
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_runs_collected_at
        ON runs (collected_at)
    """,
    """
    CREATE TABLE IF NOT EXISTS revisions (
        run_id      TEXT    NOT NULL
                            REFERENCES runs (id) ON DELETE CASCADE,
        number      INTEGER NOT NULL,
        created_at  TEXT    NOT NULL,
        label       TEXT    NOT NULL,
        PRIMARY KEY (run_id, number)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS opportunities (
        run_id         TEXT    NOT NULL
                               REFERENCES runs (id) ON DELETE CASCADE,
        need_id        TEXT    NOT NULL,
        title          TEXT    NOT NULL,
        url            TEXT    NOT NULL,
        max_length     INTEGER,
        offset_start   INTEGER NOT NULL,
        offset_end     INTEGER NOT NULL,
        default_slots  INTEGER NOT NULL,
        PRIMARY KEY (run_id, need_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS events (
        run_id          TEXT    NOT NULL,
        revision        INTEGER NOT NULL,
        id              TEXT    NOT NULL,
        title           TEXT    NOT NULL,
        date            TEXT    NOT NULL,
        calendar_start  TEXT    NOT NULL,
        calendar_end    TEXT    NOT NULL,
        shift_start     TEXT    NOT NULL,
        shift_end       TEXT    NOT NULL,
        category        TEXT,
        match_kind      TEXT,
        match_keyword   TEXT,
        match_score     INTEGER,
        added_by_hand   INTEGER NOT NULL,
        PRIMARY KEY (run_id, revision, id),
        FOREIGN KEY (run_id, revision)
            REFERENCES revisions (run_id, number) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS event_roles (
        run_id    TEXT    NOT NULL,
        revision  INTEGER NOT NULL,
        event_id  TEXT    NOT NULL,
        need_id   TEXT    NOT NULL,
        slots     INTEGER NOT NULL,
        edited    INTEGER NOT NULL,
        PRIMARY KEY (run_id, revision, event_id, need_id),
        FOREIGN KEY (run_id, revision, event_id)
            REFERENCES events (run_id, revision, id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS change_log (
        id            INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
        run_id        TEXT    NOT NULL
                              REFERENCES runs (id) ON DELETE CASCADE,
        revision      INTEGER NOT NULL,
        logged_at     TEXT    NOT NULL,
        principal_id  TEXT    NOT NULL,
        entry         TEXT    NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_change_log_run
        ON change_log (run_id, id)
    """,
    """
    CREATE TABLE IF NOT EXISTS jobs (
        id            TEXT NOT NULL PRIMARY KEY,
        run_id        TEXT NOT NULL
                           REFERENCES runs (id) ON DELETE CASCADE,
        kind          TEXT NOT NULL,
        status        TEXT NOT NULL,
        principal_id  TEXT NOT NULL,
        held_by       TEXT NOT NULL DEFAULT 'service',
        created_at    TEXT NOT NULL,
        started_at    TEXT,
        finished_at   TEXT,
        detail        TEXT
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_jobs_run
        ON jobs (run_id, created_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_jobs_status
        ON jobs (status)
    """,
    """
    CREATE TABLE IF NOT EXISTS job_events (
        id           INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
        job_id       TEXT    NOT NULL
                             REFERENCES jobs (id) ON DELETE CASCADE,
        recorded_at  TEXT    NOT NULL,
        kind         TEXT    NOT NULL,
        payload      TEXT    NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_job_events_job
        ON job_events (job_id, id)
    """,
    # What a send put into Amplify.  The key is the four columns a
    # shift is identified by plus the run, because that is the unit
    # idempotency and duplicate safety work in (D16): a retry asks
    # which rows it already created, and a count could not say which.
    #
    # The reference to 'runs' deliberately does not cascade, unlike
    # every other one above.  This record is never purged (D12), so a
    # deletion that would take it away has to fail rather than succeed
    # quietly; a cascade would make "never purged" a sentence in a
    # document instead of something the database holds to.
    """
    CREATE TABLE IF NOT EXISTS sent_shifts (
        run_id           TEXT NOT NULL REFERENCES runs (id),
        need_id          TEXT NOT NULL,
        date             TEXT NOT NULL,
        shift_start      TEXT NOT NULL,
        shift_end        TEXT NOT NULL,
        sent_at          TEXT NOT NULL,
        principal_id     TEXT NOT NULL,
        idempotency_key  TEXT NOT NULL,
        PRIMARY KEY (run_id, need_id, date, shift_start, shift_end)
    )
    """,
    # Writes that have been asked for, and what each answered.  Keyed
    # on the operation as well as the key, so one value used on two
    # operations cannot have one of them replay the other's answer.
    #
    # The response columns are empty between the reservation and the
    # answer, which is what lets a second request tell a write still
    # running from one that finished.
    """
    CREATE TABLE IF NOT EXISTS idempotency_keys (
        operation     TEXT NOT NULL,
        key           TEXT NOT NULL,
        run_id        TEXT NOT NULL
                           REFERENCES runs (id) ON DELETE CASCADE,
        fingerprint   TEXT NOT NULL,
        principal_id  TEXT NOT NULL,
        created_at    TEXT NOT NULL,
        status_code   INTEGER,
        response      TEXT,
        PRIMARY KEY (operation, key)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_idempotency_keys_run
        ON idempotency_keys (run_id, created_at)
    """
)


@dataclass(frozen=True)
class AddedColumn:
    """ A column added to a table that already existed.

        Attributes:
            table (str):
                Table the column belongs to.

            column (str):
                What it is called, which is what says whether the step
                still has anything to do.

            statement (str):
                What adds it.  It declares the column exactly as the
                create above declares it, so a database carried here
                and one built here are the same database.
    """

    table: str
    column: str
    statement: str


# What carries a database that already exists forward, by the version
# each step raises it to.  Separate from the statements above because
# those create things and these change a thing that is already there:
# a 'CREATE TABLE IF NOT EXISTS' does nothing at all to a table that
# exists, so a column added to one arrives here or not at all.
#
# A step runs on a database below its version whose table still lacks
# the column.  The second half of that matters: a database from before
# the table itself existed is given the current table by the
# statements above, so there is nothing left for the step to add and
# adding it again would fail.
#
# Nothing here may be edited after a release has run it, because a
# database already carried past it will never run it again; a
# correction is a further step.
MIGRATIONS = {
    4: (
        # Which process is holding a job, so a sweep of what a stopped
        # process left behind can leave alone what it never held.  The
        # service and the command line share a database, and a sweep
        # that took everything unfinished would mark a live send
        # interrupted.
        #
        # The default is what a job written before the column existed
        # was held by: the service, which was the only thing writing
        # jobs then.  It is a literal because a schema statement takes
        # one, and it is the value of '_records.JOB_HOLDER_SERVICE'.
        AddedColumn(
            table='jobs',
            column='held_by',
            statement=(
                'ALTER TABLE jobs '
                "ADD COLUMN held_by TEXT NOT NULL DEFAULT 'service'"
            )
        ),
    )
}

# Module logger
logger = get_logger(__name__)


def connect(
        path: Optional[Path] = None
) -> sqlite3.Connection:
    """ Open a connection and make sure the schema is present.

        Args:
            path (Path, optional):
                Database file to open.  Defaults to None, which uses
                the configured path.  ':memory:' opens a database that
                lasts as long as the connection.

        Raises:
            ConfigurationError:
                If the file cannot be created or opened, or holds a
                schema this version does not know.

        Returns:
            connection (sqlite3.Connection):
                An open connection with the schema applied.
    """

    database_path = Path(path) if path is not None else DATABASE_FILE

    try:
        database_path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

    except OSError as error:
        message = (
            f'Cannot create the directory for the database '
            f'"{database_path}": {error}'
        )
        logger.error(message)
        raise ConfigurationError(message) from error

    try:
        connection = sqlite3.connect(
            database=str(database_path),
            timeout=DATABASE_BUSY_TIMEOUT,
            # Transactions are opened and closed explicitly, by
            # 'transaction' below, so that a group of statements
            # either all apply or none do.  The alternative is an
            # implicit transaction whose extent depends on which
            # statement types were run.
            isolation_level=None
        )

    except sqlite3.Error as error:
        message = f'Cannot open the database "{database_path}": {error}'
        logger.error(message)
        raise ConfigurationError(message) from error

    connection.row_factory = sqlite3.Row
    _apply_pragmas(connection=connection)
    _apply_schema(
        connection=connection,
        database_path=database_path
    )

    message = f'Opened the database "{database_path}"'
    logger.debug(message)

    return connection


def _apply_pragmas(
        connection: sqlite3.Connection
) -> None:
    """ Apply the per-connection pragmas.

        Args:
            connection (sqlite3.Connection):
                The connection to configure.

        Raises:
            UpstreamError:
                If a pragma is refused.

        Returns:
            None.
    """

    for pragma in CONNECTION_PRAGMAS:
        execute(
            connection=connection,
            statement=pragma
        )

    return None


def _lacks_column(
        connection: sqlite3.Connection,
        table: str,
        column: str
) -> bool:
    """ Return whether a table is still without one of its columns.

        Args:
            connection (sqlite3.Connection):
                The database to look at.

            table (str):
                Table to examine.

            column (str):
                Column to look for.

        Returns:
            lacking (bool):
                Whether the column has still to be added.
    """

    # A pragma takes a literal rather than a placeholder, and the value
    # is this module's own, so nothing a caller supplies reaches it.
    rows = query(
        connection=connection,
        statement=f'PRAGMA table_info({table})'  # nosec B608
    )

    return column not in {row['name'] for row in rows}


def _migrations_from(
        connection: sqlite3.Connection,
        version: int
) -> List[str]:
    """ Return the migrations that carry a database forward.

        None at all for a database being created: the statements above
        build it at the current version, and a step replaying their
        work would fail on a column that is already there.

        Args:
            connection (sqlite3.Connection):
                The database being carried forward, which is asked
                what it already has.

            version (int):
                The version the database is at, zero for one that does
                not exist yet.

        Returns:
            statements (List[str]):
                What to run, in the order the versions came.
    """

    if not version:
        return []

    return [
        step.statement
        for level in range(version + 1, SCHEMA_VERSION + 1)
        for step in MIGRATIONS.get(level, ())
        if _lacks_column(
            connection=connection,
            table=step.table,
            column=step.column
        )
    ]


def _apply_schema(
        connection: sqlite3.Connection,
        database_path: Path
) -> None:
    """ Create the schema in an empty database, or check an existing one.

        The version lives in the database's own 'user_version' pragma
        rather than a table of its own, so reading it needs no schema
        and an empty file reports zero.

        Args:
            connection (sqlite3.Connection):
                The connection to apply the schema to.

            database_path (Path):
                Where the database is, for the error message.

        Raises:
            ConfigurationError:
                If the database is at a version this module does not
                know how to read.

        Returns:
            None.
    """

    row = query_one(
        connection=connection,
        statement='PRAGMA user_version'
    )
    version = row[0] if row is not None else 0

    if version == SCHEMA_VERSION:
        return None

    if version > SCHEMA_VERSION:
        message = (
            f'The database "{database_path}" is at schema version '
            f'{version}, which is newer than the version '
            f'{SCHEMA_VERSION} this release reads. Run the release '
            'that wrote it.'
        )
        logger.error(message)
        raise ConfigurationError(message)

    # Every statement above creates something only if it is not
    # already there, so running them all against an earlier database
    # adds what that version lacked and leaves the rest untouched.
    #
    # That carries a NEW table or index and nothing else.  A column
    # added to a table that already exists is not created by a
    # 'CREATE TABLE IF NOT EXISTS' -- the table is already there, so
    # the statement does nothing -- which is what 'MIGRATIONS' is for.
    with transaction(connection=connection):
        for statement in SCHEMA_STATEMENTS:
            execute(
                connection=connection,
                statement=statement
            )

        for statement in _migrations_from(
            connection=connection,
            version=version
        ):
            execute(
                connection=connection,
                statement=statement
            )

        # The version cannot be set through a parameter: a pragma takes
        # a literal, not a placeholder.  The value is this module's own
        # constant, so nothing a caller supplies reaches the statement.
        execute(
            connection=connection,
            statement=f'PRAGMA user_version = {SCHEMA_VERSION}'
        )

    message = (
        f'Created schema version {SCHEMA_VERSION} in "{database_path}"'
        if version == 0
        else (
            f'Carried "{database_path}" from schema version {version} '
            f'to {SCHEMA_VERSION}'
        )
    )
    logger.debug(message)

    return None


@contextmanager
def transaction(
        connection: sqlite3.Connection
) -> Iterator[sqlite3.Connection]:
    """ Apply a group of statements as one unit, or none of them.

        Re-entrant: a block opened inside another one leaves the
        transaction to the outermost block.  SQLite has no nested
        transaction, and committing on the way out of an inner block
        would end the outer one early, publishing half of it.

        Args:
            connection (sqlite3.Connection):
                The connection to run the statements on.

        Raises:
            UpstreamError:
                If the transaction cannot be started or committed.

        Yields:
            connection (sqlite3.Connection):
                The same connection, for use inside the block.
    """

    if connection.in_transaction:
        yield connection
        return

    committed = False

    try:
        connection.execute('BEGIN')
        yield connection
        connection.commit()
        committed = True

    except sqlite3.Error as error:
        raise _translated(error=error) from error

    finally:
        if not committed:
            connection.rollback()


def execute(
        connection: sqlite3.Connection,
        statement: str,
        parameters: Sequence[Any] = ()
) -> sqlite3.Cursor:
    """ Run one statement.

        Args:
            connection (sqlite3.Connection):
                The connection to run the statement on.

            statement (str):
                SQL, with placeholders for every supplied value.

            parameters (Sequence[Any], optional):
                Values for the placeholders.  Defaults to an empty
                sequence.

        Raises:
            UpstreamError:
                If the statement fails.

        Returns:
            cursor (sqlite3.Cursor):
                The cursor the statement ran on.
    """

    try:
        return connection.execute(statement, parameters)

    except sqlite3.Error as error:
        raise _translated(error=error) from error


def execute_many(
        connection: sqlite3.Connection,
        statement: str,
        parameters: Sequence[Sequence[Any]]
) -> None:
    """ Run one statement once per set of values.

        Args:
            connection (sqlite3.Connection):
                The connection to run the statement on.

            statement (str):
                SQL, with placeholders for every supplied value.

            parameters (Sequence[Sequence[Any]]):
                One set of placeholder values per execution.

        Raises:
            UpstreamError:
                If any execution fails.

        Returns:
            None.
    """

    try:
        connection.executemany(statement, parameters)

    except sqlite3.Error as error:
        raise _translated(error=error) from error

    return None


def query(
        connection: sqlite3.Connection,
        statement: str,
        parameters: Sequence[Any] = ()
) -> List[sqlite3.Row]:
    """ Run a query and return every row.

        Args:
            connection (sqlite3.Connection):
                The connection to run the query on.

            statement (str):
                SQL, with placeholders for every supplied value.

            parameters (Sequence[Any], optional):
                Values for the placeholders.  Defaults to an empty
                sequence.

        Raises:
            UpstreamError:
                If the query fails.

        Returns:
            rows (List[sqlite3.Row]):
                Every matching row, in the query's own order.
    """

    cursor = execute(
        connection=connection,
        statement=statement,
        parameters=parameters
    )

    try:
        return cursor.fetchall()

    except sqlite3.Error as error:
        raise _translated(error=error) from error


def query_one(
        connection: sqlite3.Connection,
        statement: str,
        parameters: Sequence[Any] = ()
) -> Optional[sqlite3.Row]:
    """ Run a query written to match one row, and return it.

        A reading of 'query' for the statements that look something up
        by its key, so that a caller expecting a single row does not
        index into a list to say so.

        Args:
            connection (sqlite3.Connection):
                Connection to run it on.

            statement (str):
                SQL matching at most one row.

            parameters (Sequence[Any], optional):
                Placeholder values.  Defaults to none.

        Raises:
            UpstreamError:
                If it fails.

        Returns:
            row (sqlite3.Row | None):
                The first row, or None when nothing matched.
    """

    rows = query(
        connection=connection,
        statement=statement,
        parameters=parameters
    )

    return rows[0] if rows else None


def _translated(
        error: sqlite3.Error
) -> StarPassError:
    """ Return the core exception a database failure belongs to.

        A constraint violation says the values were wrong -- a run that
        does not exist, a revision already used -- which the caller
        fixes by supplying different ones.  Anything else says the
        database itself failed, which the caller can only retry.  Those
        are the two different actions, so they are two exceptions.

        The statement is left out of both messages deliberately.  A
        message is written for the person running the command, and the
        values bound to a statement here can include a volunteer's
        name; the SQL itself is in this package and does not need
        quoting back.

        Args:
            error (sqlite3.Error):
                The failure to describe.

        Returns:
            exception (StarPassError):
                The exception to raise, already logged.
    """

    if isinstance(error, sqlite3.IntegrityError):
        message = f'The database rejected the data: {error}'
        logger.error(message)

        return ValidationError(message)

    message = f'The database reported an error: {error}'
    logger.error(message)

    return UpstreamError(message)
