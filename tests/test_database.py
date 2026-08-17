#!/usr/bin/env python3
""" Tests for the SQLite connection, schema and statement helpers. """

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
import sqlite3
from pathlib import Path

# Imports - Third-Party
import pytest

# Imports - Local
from star_pass import _database
from star_pass._exceptions import (
    ConfigurationError,
    UpstreamError,
    ValidationError
)

# Constants
EXPECTED_TABLES = {
    'change_log',
    'event_roles',
    'events',
    'idempotency_keys',
    'opportunities',
    'revisions',
    'runs',
    'sent_shifts',
    'uncollected_events'
}

# Every version this application has written, and what the one after
# it added: the tables, and the columns added to a table that already
# existed.  Carrying a database forward is checked at each of them
# rather than only at the newest, because a release that skipped two
# versions has to gain every set.
#
# A column is wound back as well as a table, because the two are
# carried forward by different halves of the schema code: a table
# arrives from a 'CREATE TABLE IF NOT EXISTS' that does nothing to one
# already there, and a column can only arrive from a migration.  A
# test that dropped only tables would pass against a release that had
# forgotten the migration entirely.
EARLIER_VERSIONS = (
    (1, ('job_events', 'jobs'), ()),
    (2, ('idempotency_keys', 'sent_shifts'), ()),
    (3, (), (('jobs', 'held_by'),)),
    (4, ('uncollected_events',), ())
)


INSERT_RUN = (
    'INSERT INTO runs (id, calendar, window_start, window_end, '
    'status, collected_at) VALUES (?, ?, ?, ?, ?, ?)'
)


def insert_run(
    connection: sqlite3.Connection,
    run_id: str
) -> None:
    _database.execute(
        connection=connection,
        statement=INSERT_RUN,
        parameters=(
            run_id,
            'practices',
            '2026-09-01',
            '2026-10-01',
            'collecting',
            '2026-09-01T00:00:00+00:00'
        )
    )


def table_names(connection: sqlite3.Connection) -> set:
    return {
        row['name']
        for row in _database.query(
            connection=connection,
            statement="SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }


def column_names(
    connection: sqlite3.Connection,
    table: str
) -> set:
    return {
        row['name']
        for row in _database.query(
            connection=connection,
            statement=f'PRAGMA table_info({table})'
        )
    }


def test_connect_creates_every_table(connection: sqlite3.Connection) -> None:
    assert EXPECTED_TABLES <= table_names(connection=connection)


def test_connect_records_the_schema_version(
    connection: sqlite3.Connection
) -> None:
    row = _database.query_one(
        connection=connection,
        statement='PRAGMA user_version'
    )

    assert row[0] == _database.SCHEMA_VERSION


def test_connect_creates_a_missing_directory(database_path: Path) -> None:
    assert not database_path.parent.exists()

    connection = _database.connect(path=database_path)
    connection.close()

    assert database_path.is_file()


def test_connect_enables_foreign_keys(
    connection: sqlite3.Connection
) -> None:
    row = _database.query_one(
        connection=connection,
        statement='PRAGMA foreign_keys'
    )

    assert row[0] == 1


def test_connect_reuses_an_existing_database(database_path: Path) -> None:
    first = _database.connect(path=database_path)
    insert_run(
        connection=first,
        run_id='kept'
    )
    first.close()

    second = _database.connect(path=database_path)
    row = _database.query_one(
        connection=second,
        statement='SELECT id FROM runs'
    )
    second.close()

    assert row['id'] == 'kept'


def test_connect_reports_an_unusable_path(tmp_path: Path) -> None:
    blocking_file = tmp_path / 'not-a-directory'
    blocking_file.write_text(data='', encoding='utf-8')

    with pytest.raises(ConfigurationError) as error:
        _database.connect(path=blocking_file / 'star_pass.db')

    assert 'directory for the database' in str(error.value)


def test_connect_uses_the_configured_path(
    monkeypatch: pytest.MonkeyPatch,
    database_path: Path
) -> None:
    monkeypatch.setattr(_database, 'DATABASE_FILE', database_path)

    connection = _database.connect()
    connection.close()

    assert database_path.is_file()


def test_a_broken_statement_is_an_upstream_error(
    connection: sqlite3.Connection
) -> None:
    with pytest.raises(UpstreamError) as error:
        _database.query(
            connection=connection,
            statement='SELECT * FROM nothing_here'
        )

    assert 'reported an error' in str(error.value)


def test_a_violated_constraint_is_a_validation_error(
    connection: sqlite3.Connection
) -> None:
    with pytest.raises(ValidationError) as error:
        _database.execute(
            connection=connection,
            statement=(
                'INSERT INTO revisions (run_id, number, created_at, label) '
                'VALUES (?, ?, ?, ?)'
            ),
            parameters=('no-such-run', 1, '2026-09-01T00:00:00+00:00', 'x')
        )

    assert 'rejected the data' in str(error.value)


def test_a_failure_message_omits_the_statement(
    connection: sqlite3.Connection
) -> None:
    # A message is written for the operator, and the values bound to a
    # statement can carry a volunteer's name.
    with pytest.raises(UpstreamError) as error:
        _database.query(
            connection=connection,
            statement='SELECT * FROM nothing_here'
        )

    assert 'SELECT' not in str(error.value)


def test_transaction_applies_every_statement(
    connection: sqlite3.Connection
) -> None:
    with _database.transaction(connection=connection):
        insert_run(
            connection=connection,
            run_id='a'
        )

    rows = _database.query(
        connection=connection,
        statement='SELECT id FROM runs'
    )

    assert [row['id'] for row in rows] == ['a']


def test_transaction_rolls_back_a_failure(
    connection: sqlite3.Connection
) -> None:
    with pytest.raises(ValueError):
        with _database.transaction(connection=connection):
            insert_run(
                connection=connection,
                run_id='b'
            )
            raise ValueError('the caller gave up part way through')

    rows = _database.query(
        connection=connection,
        statement='SELECT id FROM runs'
    )

    assert rows == []
    assert connection.in_transaction is False


def test_a_nested_transaction_leaves_the_commit_to_the_outer_one(
    connection: sqlite3.Connection
) -> None:
    # SQLite has no nested transaction, so an inner block that
    # committed would publish half of the outer one.
    with _database.transaction(connection=connection):
        with _database.transaction(connection=connection):
            insert_run(
                connection=connection,
                run_id='c'
            )

        assert connection.in_transaction is True

    assert connection.in_transaction is False


@pytest.fixture(name='surviving_run')
def fixture_surviving_run(database_path: Path) -> str:
    """ Return a run written before the database is wound back. """
    connection = _database.connect(path=database_path)
    insert_run(
        connection=connection,
        run_id='survives'
    )
    connection.close()

    return 'survives'


@pytest.fixture(name='wound_back', params=EARLIER_VERSIONS)
def fixture_wound_back(
    request: pytest.FixtureRequest,
    database_path: Path
) -> tuple:
    """ Return a database wound back to an earlier version.

        Stands in for one written before those tables and columns
        existed: they are dropped and the version is wound back.  A
        fixture rather than a step in each test, because winding back
        is one arrangement and the three tests below ask three
        different things about it.
    """
    version, tables, columns = request.param
    connection = _database.connect(path=database_path)

    for table in tables:
        _database.execute(
            connection=connection,
            statement=f'DROP TABLE {table}'
        )

    for table, column in columns:
        _database.execute(
            connection=connection,
            statement=f'ALTER TABLE {table} DROP COLUMN {column}'
        )

    _database.execute(
        connection=connection,
        statement=f'PRAGMA user_version = {version}'
    )
    connection.close()

    return database_path, tables, columns


class TestCarryingAnOlderDatabaseForward:
    def test_an_earlier_database_gains_what_it_lacked(
        self,
        wound_back: tuple
    ) -> None:
        database_path, tables, columns = wound_back

        connection = _database.connect(path=database_path)
        names = table_names(connection=connection)
        gained = {
            (table, column)
            for table, _ignored in columns
            for column in column_names(
                connection=connection,
                table=table
            )
        }
        connection.close()

        assert set(tables) <= names
        assert set(columns) <= gained

    def test_an_earlier_database_is_recorded_at_the_new_version(
        self,
        wound_back: tuple
    ) -> None:
        database_path, _tables, _columns = wound_back

        connection = _database.connect(path=database_path)
        row = _database.query_one(
            connection=connection,
            statement='PRAGMA user_version'
        )
        connection.close()

        assert row[0] == _database.SCHEMA_VERSION

    def test_carrying_forward_keeps_what_was_there(
        self,
        database_path: Path,
        surviving_run: str,
        wound_back: tuple
    ) -> None:
        # The upgrade adds; it must not rebuild a table that already
        # holds rows.
        del wound_back

        connection = _database.connect(path=database_path)
        row = _database.query_one(
            connection=connection,
            statement='SELECT id FROM runs'
        )
        connection.close()

        assert row['id'] == surviving_run

    def test_a_newer_database_is_refused(
        self,
        database_path: Path
    ) -> None:
        # It holds a schema this release does not know how to read, and
        # guessing at it is how data is lost.
        first = _database.connect(path=database_path)
        _database.execute(
            connection=first,
            statement=f'PRAGMA user_version = {_database.SCHEMA_VERSION + 1}'
        )
        first.close()

        with pytest.raises(ConfigurationError) as error:
            _database.connect(path=database_path)

        assert 'newer than' in str(error.value)
