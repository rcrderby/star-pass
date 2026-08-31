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
from star_pass._records import Event, LogEntry, OP_NUDGE
from star_pass._repository import (
    ChangeLogRepository,
    EventRepository,
    RevisionRepository
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
    'uncollected_events',
    'unmatched_titles'
}

# Every version this application has written, and what the one after
# it added: the tables, and the columns added to a table that already
# existed.  Carrying a database forward is checked at each version
# rather than only at the newest, because a release that skipped two
# has to gain every set.
#
# A column is wound back as well as a table.  The two are carried
# forward by different halves of the schema code, and a test that
# dropped only tables would pass against a release with no migration
# at all.
EARLIER_VERSIONS = (
    (1, ('job_events', 'jobs'), ()),
    (2, ('idempotency_keys', 'sent_shifts'), ()),
    (3, (), (('jobs', 'held_by'),)),
    (4, ('uncollected_events',), ()),
    (5, ('unmatched_titles',), ()),
    (8, (), (('events', 'collected_category'),)),
    (
        9,
        (),
        (
            ('change_log', 'action'),
            ('change_log', 'subject'),
            ('change_log', 'subject_count'),
            ('change_log', 'category'),
            ('change_log', 'shift_time'),
            ('change_log', 'minutes'),
            ('change_log', 'slots'),
            ('change_log', 'need_id')
        )
    )
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
                'INSERT INTO revisions (run_id, number, created_at, kind) '
                'VALUES (?, ?, ?, ?)'
            ),
            parameters=(
                'no-such-run',
                1,
                '2026-09-01T00:00:00+00:00',
                'collected'
            )
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


# The four sentences the core ever wrote into a revision's row, and
# what each was saying.  A migration reads them back into an
# identifier and the revision it names, so this is the whole of what
# version 7 has to recover.
# One of them names a revision with two digits in it, because a
# sentence is read back by counting past its opening words and a
# count that was one out would still cast " 2" to 2.  It is numbered
# past a gap for the same reason retention leaves gaps: the middle
# revisions of an old run are removed and the ones around them stay.
LABELLED_REVISIONS = (
    (1, 'As collected', 'collected', None),
    (2, 'Continued from revision 1', 'continued', 1),
    (3, 'As recollected', 'recollected', None),
    (4, 'Reverted to revision 2', 'reverted', 2),
    (14, 'Continued from revision 13', 'continued', 13)
)

# The revisions table as version 6 wrote it, which is the shape the
# migration has to find.  Written out rather than wound back from the
# current one: the column it reads no longer exists to be restored,
# and a test that dropped 'kind' from today's table would be testing
# the migration against a row it could recover nothing from.
VERSION_SIX_REVISIONS = """
    CREATE TABLE revisions (
        run_id      TEXT    NOT NULL
                            REFERENCES runs (id) ON DELETE CASCADE,
        number      INTEGER NOT NULL,
        created_at  TEXT    NOT NULL,
        label       TEXT    NOT NULL,
        PRIMARY KEY (run_id, number)
    )
"""


@pytest.fixture(name='labelled_database')
def fixture_labelled_database(
    database_path: Path
) -> Path:
    """ Return a database at version 6, holding the old sentences.

        The table is replaced rather than altered, because what
        version 7 changed about it cannot be undone by dropping a
        column: 'kind' is NOT NULL and 'label' is gone.
    """
    connection = _database.connect(path=database_path)

    insert_run(connection=connection, run_id='run-1')
    _database.execute(connection=connection, statement='DROP TABLE revisions')
    _database.execute(connection=connection, statement=VERSION_SIX_REVISIONS)

    for number, label, _kind, _source in LABELLED_REVISIONS:
        _database.execute(
            connection=connection,
            statement=(
                'INSERT INTO revisions (run_id, number, created_at, '
                'label) VALUES (?, ?, ?, ?)'
            ),
            parameters=('run-1', number, '2026-09-01T00:00:00+00:00', label)
        )

    _database.execute(
        connection=connection,
        statement='PRAGMA user_version = 6'
    )
    connection.close()

    return database_path


class TestReadingTheOldRevisionLabels:
    def test_each_label_becomes_what_it_was_saying(
        self,
        labelled_database: Path
    ) -> None:
        connection = _database.connect(path=labelled_database)
        rows = _database.query(
            connection=connection,
            statement=(
                'SELECT number, kind, source FROM revisions '
                'ORDER BY number'
            )
        )
        connection.close()

        assert [
            (row['number'], row['kind'], row['source']) for row in rows
        ] == [
            (number, kind, source)
            for number, _label, kind, source in LABELLED_REVISIONS
        ]

    def test_the_sentence_itself_is_gone(
        self,
        labelled_database: Path
    ) -> None:
        # It has to be: an insert now names 'kind' and 'source' and
        # not 'label', so a NOT NULL column left behind would refuse
        # every revision written after the migration.
        connection = _database.connect(path=labelled_database)
        columns = column_names(connection=connection, table='revisions')
        connection.close()

        assert 'label' not in columns

    def test_a_revision_can_still_be_written(
        self,
        labelled_database: Path
    ) -> None:
        # The question the column above exists to answer, asked of the
        # statement that would actually fail.
        connection = _database.connect(path=labelled_database)

        RevisionRepository(connection=connection).create(run_id='run-1')

        rows = _database.query(
            connection=connection,
            statement='SELECT number FROM revisions ORDER BY number'
        )
        connection.close()

        assert [row['number'] for row in rows] == [1, 2, 3, 4, 14, 15]


# An event as version 8 held one, which is every column of the current
# table but the one version 9 adds.  The two rows are the two things a
# collection produces: a title that reached a category, and one that
# reached nothing and blocks the run until somebody assigns it a
# category by hand.
INSERT_EVENT = (
    'INSERT INTO events (run_id, revision, id, title, date, '
    'calendar_start, calendar_end, shift_start, shift_end, category, '
    'added_by_hand) VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?, 0)'
)

VERSION_EIGHT_EVENTS = (
    ('gcal-1', 'Adult Scrimmages', 'scrimmage'),
    ('gcal-2', 'Board Retreat', None)
)


@pytest.fixture(name='uncategorized_database')
def fixture_uncategorized_database(
    database_path: Path
) -> Path:
    """ Return a database at version 8, holding events with no record
        of what the collection matched.

        Wound back rather than written out: version 9 only adds a
        column, so dropping it leaves the table in exactly the shape
        the migration has to find.
    """
    connection = _database.connect(path=database_path)

    insert_run(connection=connection, run_id='run-1')
    _database.execute(
        connection=connection,
        statement=(
            'INSERT INTO revisions (run_id, number, created_at, kind) '
            "VALUES ('run-1', 1, '2026-09-01T00:00:00+00:00', "
            "'collected')"
        )
    )

    for identifier, title, category in VERSION_EIGHT_EVENTS:
        _database.execute(
            connection=connection,
            statement=INSERT_EVENT,
            parameters=(
                'run-1',
                identifier,
                title,
                '2026-09-03',
                '19:00',
                '21:00',
                '19:15',
                '21:30',
                category
            )
        )

    _database.execute(
        connection=connection,
        statement='ALTER TABLE events DROP COLUMN collected_category'
    )
    _database.execute(
        connection=connection,
        statement='PRAGMA user_version = 8'
    )
    connection.close()

    return database_path


class TestFillingInWhatTheCollectionMatched:
    def test_each_event_takes_the_category_it_is_under(
        self,
        uncategorized_database: Path
    ) -> None:
        # The nearest true thing a database can say about rows written
        # before the column existed: an unedited event is under what
        # it was collected under, and an edited one has nothing left
        # that says what that was.
        connection = _database.connect(path=uncategorized_database)
        rows = _database.query(
            connection=connection,
            statement=(
                'SELECT id, category, collected_category FROM events '
                'ORDER BY id'
            )
        )
        connection.close()

        assert [
            (row['id'], row['collected_category']) for row in rows
        ] == [
            (identifier, category)
            for identifier, _title, category in VERSION_EIGHT_EVENTS
        ]

    def test_an_event_can_still_be_written(
        self,
        uncategorized_database: Path
    ) -> None:
        # The column is nullable, so nothing about the fill can stop
        # an insert that names it.
        connection = _database.connect(path=uncategorized_database)

        EventRepository(connection=connection).add(
            run_id='run-1',
            revision=1,
            event=Event(
                id='gcal-3',
                title='Junior Scrimmages',
                date='2026-09-04',
                calendar_start='17:00',
                calendar_end='19:00',
                shift_start='17:00',
                shift_end='19:00',
                category='junior_scrimmage',
                collected_category='junior_scrimmage'
            )
        )

        stored = EventRepository(connection=connection).get(
            run_id='run-1',
            revision=1,
            event_id='gcal-3'
        )
        connection.close()

        assert stored.collected_category == 'junior_scrimmage'


# The change log as version 9 wrote it: one English sentence, with no
# record of what was done or what it carried.
VERSION_NINE_CHANGE_LOG = """
    CREATE TABLE change_log (
        id            INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
        run_id        TEXT    NOT NULL
                              REFERENCES runs (id) ON DELETE CASCADE,
        revision      INTEGER NOT NULL,
        logged_at     TEXT    NOT NULL,
        principal_id  TEXT    NOT NULL,
        entry         TEXT    NOT NULL
    )
"""


@pytest.fixture(name='sentenced_database')
def fixture_sentenced_database(
    database_path: Path
) -> Path:
    """ Return a database at version 9, holding the old sentences.

        The table is replaced rather than altered, because what
        version 10 changed about it cannot be undone by dropping
        columns: 'action' is NOT NULL and 'entry' is gone.
    """
    connection = _database.connect(path=database_path)

    insert_run(connection=connection, run_id='run-1')
    _database.execute(connection=connection, statement='DROP TABLE change_log')
    _database.execute(connection=connection, statement=VERSION_NINE_CHANGE_LOG)
    _database.execute(
        connection=connection,
        statement=(
            'INSERT INTO change_log (run_id, revision, logged_at, '
            "principal_id, entry) VALUES ('run-1', 1, "
            "'2026-09-01T00:00:00+00:00', 'static-token', "
            "'Set the category of \"X\" to \"junior_scrimmage\".')"
        )
    )
    _database.execute(
        connection=connection,
        statement='PRAGMA user_version = 9'
    )
    connection.close()

    return database_path


class TestDiscardingTheOldSentences:
    def test_the_sentence_itself_is_gone(
        self,
        sentenced_database: Path
    ) -> None:
        # It has to be: an insert now names 'action' and not 'entry',
        # so a NOT NULL column left behind would refuse every entry
        # written after the migration.
        connection = _database.connect(path=sentenced_database)
        columns = column_names(connection=connection, table='change_log')
        connection.close()

        assert 'entry' not in columns

    def test_the_entry_is_left_saying_nothing_was_done(
        self,
        sentenced_database: Path
    ) -> None:
        # Nothing recovers an action from prose.  What a sentence
        # carried is an event title, a time and a category
        # interpolated into English, and reading those back would be a
        # migration written against wording -- for entries the wipe
        # that follows this release discards anyway.
        connection = _database.connect(path=sentenced_database)
        row = _database.query_one(
            connection=connection,
            statement='SELECT action, subject FROM change_log'
        )
        connection.close()

        assert (row['action'], row['subject']) == ('', None)

    def test_an_entry_can_still_be_written(
        self,
        sentenced_database: Path
    ) -> None:
        # The question the column above exists to answer, asked of the
        # statement that would actually fail.
        connection = _database.connect(path=sentenced_database)
        _database.execute(
            connection=connection,
            statement=(
                "INSERT INTO revisions (run_id, number, created_at, kind) "
                "VALUES ('run-1', 1, '2026-09-01T00:00:00+00:00', "
                "'collected')"
            )
        )

        written = ChangeLogRepository(connection=connection).add(
            run_id='run-1',
            revision=1,
            principal_id='static-token',
            recorded=LogEntry(action=OP_NUDGE, minutes=-15)
        )
        connection.close()

        assert (written.action, written.minutes) == (OP_NUDGE, -15)


@pytest.fixture(name='unnoted_database')
def fixture_unnoted_database(
    database_path: Path
) -> Path:
    """ Return a database at version 10, before the note existed.

        Both columns are dropped, because version 11 adds one to each
        of two tables and a migration proved on one of them is a
        migration half proved.
    """
    connection = _database.connect(path=database_path)

    insert_run(connection=connection, run_id='run-1')
    _database.execute(
        connection=connection,
        statement=(
            "INSERT INTO revisions (run_id, number, created_at, kind) "
            "VALUES ('run-1', 1, '2026-09-01T00:00:00+00:00', 'collected')"
        )
    )
    _database.execute(
        connection=connection,
        statement=(
            'INSERT INTO events (run_id, revision, id, title, date, '
            'calendar_start, calendar_end, shift_start, shift_end, '
            "added_by_hand) VALUES ('run-1', 1, 'event-1', 'A Game', "
            "'2026-09-03', '19:00', '21:00', '19:15', '21:30', 0)"
        )
    )
    _database.execute(
        connection=connection,
        statement=(
            'INSERT INTO uncollected_events (run_id, id, reason) '
            "VALUES ('run-1', 'gcal-9', 'search')"
        )
    )

    for table in ('events', 'uncollected_events'):
        _database.execute(
            connection=connection,
            statement=f'ALTER TABLE {table} DROP COLUMN calendar_note'
        )

    _database.execute(
        connection=connection,
        statement='PRAGMA user_version = 10'
    )
    connection.close()

    return database_path


class TestMakingRoomForWhatTheCalendarSaid:
    @pytest.mark.parametrize(
        'table', ['events', 'uncollected_events']
    )
    def test_the_column_arrives_on_both_tables(
        self,
        unnoted_database: Path,
        table: str
    ) -> None:
        connection = _database.connect(path=unnoted_database)
        columns = column_names(connection=connection, table=table)
        connection.close()

        assert 'calendar_note' in columns

    def test_a_row_written_before_it_has_no_note(
        self,
        unnoted_database: Path
    ) -> None:
        # Nothing is filled in.  A note can only come from reading
        # the calendar, and nothing the run holds recovers it, so
        # those rows read as having none until the run is collected
        # again.
        connection = _database.connect(path=unnoted_database)
        row = _database.query_one(
            connection=connection,
            statement='SELECT calendar_note FROM events'
        )
        connection.close()

        assert row['calendar_note'] is None

    def test_a_note_can_be_written_afterwards(
        self,
        unnoted_database: Path
    ) -> None:
        # The question the column exists to answer, asked of the
        # statement that would actually fail.
        connection = _database.connect(path=unnoted_database)
        _database.execute(
            connection=connection,
            statement=(
                "UPDATE events SET calendar_note = 'Doors at 6 PM' "
                "WHERE id = 'event-1'"
            )
        )
        row = _database.query_one(
            connection=connection,
            statement='SELECT calendar_note FROM events'
        )
        connection.close()

        assert row['calendar_note'] == 'Doors at 6 PM'
