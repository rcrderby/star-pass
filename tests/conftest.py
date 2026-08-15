""" Shared pytest configuration and fixtures.

    Sets dummy credentials/config in the environment *before* any
    star_pass module is imported, so import-time getenv() calls succeed
    and no test requires a real .env file or network access.
"""

# Imports - Python Standard Library
import os
import sqlite3
from pathlib import Path
from typing import Any, Callable, Iterator

# Imports - Third-Party
import dotenv

# Neutralize the .env load before star_pass is imported.
# 'star_pass._defaults' calls 'load_dotenv' at import time with a path
# relative to the working directory, so running pytest from a checkout
# that has a real .env let deployment settings decide test results: a
# value set there and read after the load (for example
# 'SLACK_SUMMARY_EMOJI') reached the code under test, and the suite
# passed in continuous integration -- where no .env exists -- while
# failing on a contributor's machine.  Stubbing the function here is
# what makes "tests require no .env" true rather than merely intended.
dotenv.load_dotenv = lambda *args, **kwargs: False

# Populate dummy environment variables prior to importing star_pass.
# Values are intentionally fake; no test may make a live API call.
os.environ.setdefault('AMPLIFY_TOKEN', 'test-amplify-token')
os.environ.setdefault('GCAL_TOKEN', 'test-gcal-token')
# Set so the run-mode credential preflight passes. Tests that exercise a
# missing credential delete the variable with monkeypatch.
os.environ.setdefault('SLACK_BOT_TOKEN', 'test-slack-not-a-real-token')
# Long enough to pass the service's minimum-length check, which is
# what a deployment's real token has to clear.
os.environ.setdefault(
    'STAR_PASS_API_TOKEN',
    'test-star-pass-api-value-not-a-real-one'
)
os.environ.setdefault('GCAL_WINDOW_START', '2099-01-01T00:00:00-00:00')
os.environ.setdefault('GCAL_WINDOW_END', '2099-01-31T00:00:00-00:00')

# Imports below intentionally follow the env setup above.
# pylint: disable=wrong-import-position

# Imports - Third-Party
import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

# Imports - Local
from star_pass._database import connect  # noqa: E402
from star_pass._helpers import Helpers  # noqa: E402
from star_pass._records import Event, EventRole, Opportunity  # noqa: E402
from star_pass._repository import (  # noqa: E402
    ChangeLogRepository,
    EventRepository,
    JobRepository,
    RevisionRepository,
    RunRepository
)
from star_pass_api import create_app  # noqa: E402


@pytest.fixture
def helpers() -> Helpers:
    """ Return a fresh Helpers instance for each test. """
    return Helpers()


@pytest.fixture(name='database_path')
def fixture_database_path(tmp_path: Path) -> Path:
    """ Return a path for a database that does not exist yet. """
    return tmp_path / 'state' / 'star_pass.db'


@pytest.fixture(name='connection')
def fixture_connection(database_path: Path) -> Iterator[sqlite3.Connection]:
    """ Return a connection to an empty database of this test's own. """
    open_connection = connect(path=database_path)
    yield open_connection
    open_connection.close()


@pytest.fixture(name='runs')
def fixture_runs(connection: sqlite3.Connection) -> RunRepository:
    """ Return a run repository on the test's database. """
    return RunRepository(connection=connection)


@pytest.fixture(name='revisions')
def fixture_revisions(connection: sqlite3.Connection) -> RevisionRepository:
    """ Return a revision repository on the test's database. """
    return RevisionRepository(connection=connection)


@pytest.fixture(name='events')
def fixture_events(connection: sqlite3.Connection) -> EventRepository:
    """ Return an event repository on the test's database. """
    return EventRepository(connection=connection)


@pytest.fixture(name='change_log')
def fixture_change_log(connection: sqlite3.Connection) -> ChangeLogRepository:
    """ Return a change log repository on the test's database. """
    return ChangeLogRepository(connection=connection)


@pytest.fixture(name='jobs')
def fixture_jobs(connection: sqlite3.Connection) -> JobRepository:
    """ Return a job repository on the test's database. """
    return JobRepository(connection=connection)


@pytest.fixture(name='run_id')
def fixture_run_id(runs: RunRepository) -> str:
    """ Return the ID of a run stored with a one-month window. """
    return runs.create(
        calendar='practices',
        window_start='2026-09-01',
        window_end='2026-10-01'
    ).id


@pytest.fixture(name='revision')
def fixture_revision(
    revisions: RevisionRepository,
    run_id: str
) -> int:
    """ Return the number of a first, empty revision of the run. """
    return revisions.create(
        run_id=run_id,
        label='As collected'
    ).number


@pytest.fixture(name='make_event')
def fixture_make_event() -> Callable[..., Event]:
    """ Return a factory building an event, with fields overridable. """

    def build(**overrides: Any) -> Event:
        """ Return an event, replacing any field named in 'overrides'. """
        fields: dict = {
            'id': 'event-1',
            'title': 'Adult Scrimmages',
            'date': '2026-09-03',
            'calendar_start': '19:00',
            'calendar_end': '21:00',
            'shift_start': '19:15',
            'shift_end': '21:30',
            'category': 'scrimmage',
            'roles': (EventRole(need_id='905196', slots=4),)
        }
        fields.update(overrides)

        return Event(**fields)

    return build


@pytest.fixture(name='make_opportunity')
def fixture_make_opportunity() -> Callable[..., Opportunity]:
    """ Return a factory building an opportunity, fields overridable. """

    def build(**overrides: Any) -> Opportunity:
        """ Return an opportunity, replacing any overridden field. """
        fields: dict = {
            'need_id': '905196',
            'title': 'Adult Scrimmages: Skating Officials',
            'url': 'https://example.test/need/detail/905196',
            'max_length': 240,
            'offset_start': 15,
            'offset_end': 30,
            'default_slots': 4
        }
        fields.update(overrides)

        return Opportunity(**fields)

    return build


@pytest.fixture(name='api')
def fixture_api() -> FastAPI:
    """ Return a service of this test's own. """
    return create_app()


@pytest.fixture(name='client')
def fixture_client(api: FastAPI) -> TestClient:
    """ Return a client that returns problems rather than raising.

        An unhandled exception is a response the service produces, so a
        test has to be able to read it; the default re-raises it in the
        test instead.
    """
    return TestClient(
        app=api,
        raise_server_exceptions=False
    )


@pytest.fixture(name='api_credential')
def fixture_api_credential() -> str:
    """ Return the token the test service authenticates against. """
    return os.environ['STAR_PASS_API_TOKEN']


@pytest.fixture(name='authenticated_client')
def fixture_authenticated_client(
    api: FastAPI,
    api_credential: str
) -> TestClient:
    """ Return a client that presents a valid bearer token. """
    return TestClient(
        app=api,
        raise_server_exceptions=False,
        headers={'Authorization': f'Bearer {api_credential}'}
    )
