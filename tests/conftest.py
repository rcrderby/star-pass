""" Shared pytest configuration and fixtures.

    Sets dummy credentials/config in the environment *before* any
    star_pass module is imported, so import-time getenv() calls succeed
    and no test requires a real .env file or network access.
"""

# Imports - Python Standard Library
import importlib.util
import os
import sqlite3
from contextlib import contextmanager
from functools import partial
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List

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
# What the front end signs a session with, long enough to clear its
# own minimum. Its cookies are marked insecure here because the test
# client speaks plain HTTP, and a browser drops a Secure cookie from
# an insecure origin -- which would look like sessions not working.
os.environ.setdefault(
    'STAR_PASS_SESSION_SECRET',
    'test-star-pass-signing-value-not-a-real-one'
)
os.environ.setdefault('STAR_PASS_COOKIES_SECURE', 'false')

# Fixtures that stand in for a service outside this process, which
# are their own subject and their own module.  Registered here because
# a plugin is how a fixture reaches every test without being imported
# by each one.
pytest_plugins = ('_upstream',)

# Imports below intentionally follow the env setup above.
# pylint: disable=wrong-import-position

# Imports - Third-Party
import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

# Imports - Local
from star_pass import _database  # noqa: E402
from star_pass import _models  # noqa: E402
from star_pass._database import connect  # noqa: E402
from star_pass._helpers import Helpers  # noqa: E402
from star_pass._job_runner import JobRunner  # noqa: E402
from star_pass._records import (  # noqa: E402
    Event,
    EventRole,
    JOB_KIND_COLLECT,
    JOB_KIND_SEND,
    JOB_STATUS_SUCCEEDED,
    Match,
    MATCH_KIND_FUZZY,
    Opportunity,
    RUN_STATUS_UNSENT,
    ShiftIdentity,
    UncollectedEvent,
    UNCOLLECTED_ALL_DAY,
    UNCOLLECTED_EXCLUDED,
    UNCOLLECTED_SEARCH,
    UNCOLLECTED_UNTITLED
)
from star_pass._repository import (  # noqa: E402
    ChangeLogRepository,
    EventRepository,
    IdempotencyRepository,
    JobRepository,
    RevisionRepository,
    RunRepository,
    SentShiftRepository,
    UncollectedRepository,
    UnmatchedTitleRepository
)
from star_pass_api import create_app  # noqa: E402
from star_pass_api._defaults import API_PRINCIPAL_ID  # noqa: E402
from star_pass_cli._commands import run_command  # noqa: E402
from star_pass_cli._mode import API_URL_VARIABLE  # noqa: E402


# Path to the entry point, which is executed as a script rather than
# imported, so nothing puts it on the import path.
ENTRY_POINT = Path(__file__).resolve().parent.parent / 'app' / '__main__.py'


def load_entry_point() -> Any:
    """ Return 'app/__main__.py' as an importable module.

        Loaded under a name other than '__main__', so the guard at the
        foot of the file does not run the application on import.
    """
    spec = importlib.util.spec_from_file_location(
        'star_pass_main',
        ENTRY_POINT
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return module


@pytest.fixture(name='entry_point')
def fixture_entry_point() -> Any:
    """ Return the entry point, with nothing replaced. """
    return load_entry_point()


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


@pytest.fixture(name='connect_to_database')
def fixture_connect_to_database(
    database_path: Path
) -> Callable[[], sqlite3.Connection]:
    """ Return a way to open a connection to the test's database.

        A connection belongs to the thread that opened it, so anything
        working on another thread is given this rather than one.
    """
    return partial(connect, path=database_path)


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


@pytest.fixture(name='sent')
def fixture_sent(connection: sqlite3.Connection) -> SentShiftRepository:
    """ Return a sent shift repository on the test's database. """
    return SentShiftRepository(connection=connection)


@pytest.fixture(name='uncollected')
def fixture_uncollected(
    connection: sqlite3.Connection
) -> UncollectedRepository:
    """ Return an uncollected event repository on the database. """
    return UncollectedRepository(connection=connection)


@pytest.fixture(name='unmatched')
def fixture_unmatched(
    connection: sqlite3.Connection
) -> UnmatchedTitleRepository:
    """ Return an unmatched title repository on the database. """
    return UnmatchedTitleRepository(connection=connection)


@pytest.fixture(name='idempotency')
def fixture_idempotency(
    connection: sqlite3.Connection
) -> IdempotencyRepository:
    """ Return an idempotency repository on the test's database. """
    return IdempotencyRepository(connection=connection)


@pytest.fixture(name='shift_identity')
def fixture_shift_identity() -> ShiftIdentity:
    """ Return one shift's identity: need, date, start and end. """
    return ('123456', '2026-09-05', '18:00', '20:00')


@pytest.fixture(name='run_id')
def fixture_run_id(runs: RunRepository) -> str:
    """ Return the ID of a run stored with a one-month window. """
    return runs.create(
        calendar='practices',
        window_start='2026-09-01',
        window_end='2026-10-01'
    ).id


@pytest.fixture(name='other_run_id')
def fixture_other_run_id(runs: RunRepository) -> str:
    """ Return the ID of a second run, for a test that needs two. """
    return runs.create(
        calendar='events',
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


@pytest.fixture(name='collected')
def fixture_collected(
    events: EventRepository,
    runs: RunRepository,
    run_id: str,
    revision: int,
    make_event: Callable[..., Event]
) -> str:
    """ Return a run whose first revision holds one event.

        Left 'unsent' rather than 'collecting', which is where a real
        collection leaves a run it has finished filling in.  A fixture
        that stopped short of that would be a run nothing may be done
        with, and a test using it would be testing the wrong refusal.
    """
    events.add(
        run_id=run_id,
        revision=revision,
        event=make_event()
    )
    runs.set_status(run_id=run_id, status=RUN_STATUS_UNSENT)

    return run_id


@pytest.fixture(name='edited')
def fixture_edited(
    events: EventRepository,
    revisions: RevisionRepository,
    collected: str,
    make_event: Callable[..., Event]
) -> str:
    """ Return that run with a second revision moving the event. """
    revisions.create(run_id=collected, label='Edited')
    events.replace(
        run_id=collected,
        revision=2,
        event=make_event(shift_start='19:45')
    )

    return collected


@pytest.fixture(name='populated')
# Seven fixtures because the run has something of everything in it, and
# a shorter list would be a run that agrees by accident.
# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def fixture_populated(
    add_log_entry: Callable[..., None],
    edited: str,
    events: EventRepository,
    job_id: str,
    make_event: Callable[..., Event],
    make_opportunity: Callable[..., Opportunity],
    runs: RunRepository
) -> str:
    """ Return a run with something of everything in it.

        A run holding one plain event can be read correctly by code
        that is wrong about everything a run can also hold, so this one
        has two revisions, a repeat, a blocked event, a fuzzy match, an
        opportunity and a change log entry.
    """
    del job_id

    runs.set_opportunities(
        run_id=edited,
        opportunities=[make_opportunity(max_length=120)]
    )
    events.add(
        run_id=edited,
        revision=2,
        event=make_event(
            id='event-2',
            match=Match(kind=MATCH_KIND_FUZZY, keyword=None, score=71)
        )
    )
    events.add(
        run_id=edited,
        revision=2,
        event=make_event(id='event-3', category=None, roles=())
    )
    events.add(
        run_id=edited,
        revision=2,
        event=make_event(id='event-4', added_by_hand=True)
    )
    add_log_entry(
        run_id=edited,
        revision=2,
        entry='Nudged Adult Scrimmages by 30 minutes'
    )

    return edited


@pytest.fixture(name='not_collected')
def fixture_not_collected(
    uncollected: UncollectedRepository
) -> Callable[[str], List[Any]]:
    """ Return a way to record what a run's window left out.

        One of each reason, because a grouping read correctly for one
        group can be read wrongly for the rest, and only the first is
        addable.  Dated in the order the reasons are declared is
        deliberately avoided: the rows go in by date and come out
        grouped, so a group order taken from the row order would show.
    """

    def record(run_id: str) -> List[Any]:
        """ Store one left-out event per reason, and return them. """
        rows = [
            UncollectedEvent(
                id='gcal-8',
                reason=UNCOLLECTED_UNTITLED,
                date='2026-09-08',
                calendar_start='08:00',
                calendar_end='09:00'
            ),
            UncollectedEvent(
                id='gcal-9',
                reason=UNCOLLECTED_ALL_DAY,
                title='Board Retreat',
                date='2026-09-09'
            ),
            UncollectedEvent(
                id='gcal-10',
                reason=UNCOLLECTED_EXCLUDED,
                title='CANCELED: Adult Scrimmages',
                date='2026-09-10',
                calendar_start='19:00',
                calendar_end='21:00'
            ),
            UncollectedEvent(
                id='gcal-11',
                reason=UNCOLLECTED_SEARCH,
                title='Junior Bout',
                date='2026-09-11',
                calendar_start='18:00',
                calendar_end='20:00'
            )
        ]
        uncollected.replace(run_id=run_id, uncollected=rows)

        return rows

    return record


@pytest.fixture(name='add_second_event')
def fixture_add_second_event(
    events: EventRepository,
    collected: str,
    revision: int,
    make_event: Callable[..., Event]
) -> Callable[..., None]:
    """ Return a way to add one more event to the collected run.

        A figure over a revision is only interesting once there is
        more than one thing in it, so most tests of one want a second
        event differing from the first in the single respect under
        test.
    """

    def add(**overrides: Any) -> None:
        """ Add an event, replacing any field named in 'overrides'. """
        events.add(
            run_id=collected,
            revision=revision,
            event=make_event(id='event-2', **overrides)
        )

    return add


@pytest.fixture(name='add_log_entry')
def fixture_add_log_entry(
    change_log: ChangeLogRepository
) -> Callable[..., None]:
    """ Return a way to append one entry to a run's change log. """

    def add(
        run_id: str,
        revision: int,
        entry: str
    ) -> None:
        """ Append the entry, recorded against the one principal. """
        change_log.add(
            run_id=run_id,
            revision=revision,
            principal_id=API_PRINCIPAL_ID,
            entry=entry
        )

    return add


@pytest.fixture(name='job_principal')
def fixture_job_principal() -> str:
    """ Return the principal ID a test's jobs are asked for by. """
    return 'static-token'


@pytest.fixture(name='job_id')
def fixture_job_id(
    jobs: JobRepository,
    run_id: str,
    job_principal: str
) -> str:
    """ Return the ID of a queued collect job for the run. """
    return jobs.create(
        run_id=run_id,
        kind=JOB_KIND_COLLECT,
        principal_id=job_principal
    ).id


@pytest.fixture(name='finished_job')
def fixture_finished_job(
    jobs: JobRepository,
    job_principal: str,
    run_id: str
) -> str:
    """ Return a job that has ended, with an entry in its log.

        Here rather than in any of the three modules that want one:
        the retention policy, the service that applies it at startup
        and the command that applies it by hand all need the same
        arrangement, and three copies would let them drift into
        arranging different things while claiming to test one policy.
    """
    job = jobs.create(
        run_id=run_id,
        kind=JOB_KIND_SEND,
        principal_id=job_principal
    )
    jobs.start(job_id=job.id)
    jobs.add_event(job_id=job.id, kind='step')
    jobs.finish(job_id=job.id, status=JOB_STATUS_SUCCEEDED)

    return job.id


@pytest.fixture(name='build_parser')
def fixture_build_parser(
    entry_point: Any
) -> Callable[[], Any]:
    """ Return the entry point's parser builder. """
    return entry_point.build_parser


@pytest.fixture(name='cli')
def fixture_cli(
    build_parser: Callable[[], Any],
    monkeypatch: pytest.MonkeyPatch,
    service_database: Path
) -> Callable[..., int]:
    """ Return a way to run a command against the test's database.

        Nothing is stubbed: the command picks its own client, so the
        mode selection is exercised rather than replaced.  The database
        it opens is redirected instead, which is the one thing a test
        cannot let it choose.
    """
    del service_database

    monkeypatch.delenv(API_URL_VARIABLE, raising=False)

    def run(*argv: str) -> int:
        """ Parse the arguments and run what they selected. """
        return run_command(args=build_parser().parse_args(argv))

    return run


@pytest.fixture(name='working_on')
def fixture_working_on(
    jobs: JobRepository
) -> Callable[..., Any]:
    """ Return a way to put a running job on a run.

        The arrangement more than one test of "something else is
        already working on this" needs, made once: what a run refuses
        while a job holds it is asked of every write.
    """

    def start(
        run_id: str,
        kind: str = JOB_KIND_SEND,
        principal_id: str = 'someone-else'
    ) -> Any:
        """ Return a job that has begun on that run. """
        job = jobs.create(
            run_id=run_id,
            kind=kind,
            principal_id=principal_id
        )
        jobs.start(job_id=job.id)

        return job

    return start


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


@pytest.fixture(name='window_document')
def fixture_window_document() -> dict:
    """ Return a one-month window as an answer carries one.

        Shared by the fixtures standing in for a service, because a
        window is one fact: two copies of it can disagree about which
        day a run ends on, which is the disagreement 'lastDay' was
        published to stop.
    """
    return {
        'start': '2026-09-01',
        'end': '2026-10-01',
        'lastDay': '2026-09-30',
        'timezone': 'America/Los_Angeles'
    }


@pytest.fixture(name='make_run_document')
def fixture_make_run_document(
    window_document: dict
) -> Callable[..., dict]:
    """ Return a factory building a run as an answer carries one. """

    def build(**overrides: Any) -> dict:
        """ Return the document, replacing any overridden count. """
        return {
            'id': 'r-1',
            'calendar': 'practices',
            'window': dict(window_document),
            'status': 'unsent',
            'revisedAt': '2026-09-02T01:00:00+00:00',
            'counts': {
                'events': overrides.get('events', 1),
                'shifts': overrides.get('shifts', 1),
                'unmatched': overrides.get('unmatched', 0),
                'uncollected': overrides.get('uncollected', 0)
            }
        }

    return build


@pytest.fixture(name='make_event_document')
def fixture_make_event_document() -> Callable[..., dict]:
    """ Return a factory building an event as an answer carries one.

        Written out rather than read from a database, because what
        reads one is deciding how to show a field and wants to set
        that field.  A test holds these keys to the shape the contract
        publishes, so a rename cannot leave this passing on its own.
    """

    def build(**overrides: Any) -> dict:
        """ Return the document, replacing any overridden field. """
        document: dict = {
            'id': 'event-1',
            'title': 'Adult Scrimmages',
            'date': '2026-09-03',
            'calendarStart': '19:00',
            'calendarEnd': '21:00',
            'shiftStart': '19:15',
            'shiftEnd': '21:30',
            'lengthMinutes': 135,
            'cappedAt': None,
            'category': 'scrimmage',
            'match': None,
            'addedByHand': False,
            'roles': [
                {'needId': '905196', 'slots': 4, 'edited': False}
            ],
            'duplicateOf': None,
            'blocking': False
        }
        document.update(overrides)

        return document

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


@pytest.fixture(name='service_database')
def fixture_service_database(
    monkeypatch: pytest.MonkeyPatch,
    database_path: Path
) -> Path:
    """ Point the service at the test's own database.

        The service opens the configured database by name rather than
        being handed a connection, so a test redirects the name.
    """
    monkeypatch.setattr(_database, 'DATABASE_FILE', database_path)

    return database_path


@pytest.fixture(name='start_service')
def fixture_start_service(
    service_database: Path,
    api_credential: str
) -> Callable[[], Any]:
    """ Return a way to start a service on the test's database.

        A started service is one whose startup and shutdown work has
        run; the plain client fixture skips it, which is what most
        tests want.
    """
    del service_database

    @contextmanager
    def start() -> Iterator[TestClient]:
        """ Start a service and yield a client that authenticates. """
        with TestClient(
            app=create_app(),
            raise_server_exceptions=False,
            headers={'Authorization': f'Bearer {api_credential}'}
        ) as client:
            yield client

    return start


class WaitingRunner(JobRunner):
    """ The real runner, with a way to wait for what it was given.

        A job runs on a thread, so a test that read the database
        straight after asking for one would be racing it.  This is not
        a stand-in for the runner: it is the runner, keeping the
        futures it already returns so a test can wait on the last one.
    """

    def __init__(self, connect_to: Any) -> None:
        """ Run one job at a time and remember them. """
        super().__init__(connect=connect_to, workers=1)
        self.futures: list = []

    def submit(self, job_id: str, work: Any) -> Any:
        """ Submit the job and keep what it returned. """
        future = super().submit(job_id=job_id, work=work)
        self.futures.append(future)

        return future


@pytest.fixture(name='started_client')
def fixture_started_client(
    running_client: TestClient
) -> TestClient:
    """ Return a started service whose jobs a test can wait for. """
    running_client.app.state.runner = WaitingRunner(
        # pylint: disable-next=protected-access
        connect_to=running_client.app.state.runner._connect
    )

    return running_client


@pytest.fixture(name='finish_jobs')
def fixture_finish_jobs(
    started_client: TestClient
) -> Callable[[], None]:
    """ Return a way to wait for every job the service has started. """

    def wait() -> None:
        """ Wait for each future the runner kept. """
        for future in started_client.app.state.runner.futures:
            future.result()

        return None

    return wait


@pytest.fixture(name='anonymous_client')
def fixture_anonymous_client(
    service_database: Path
) -> Iterator[TestClient]:
    """ Return a started service's client that presents no credential. """
    del service_database

    with TestClient(
        app=create_app(),
        raise_server_exceptions=False
    ) as client:
        yield client


@pytest.fixture(name='running_client')
def fixture_running_client(
    start_service: Callable[[], Any]
) -> Iterator[TestClient]:
    """ Return a client for a service that has actually started. """
    with start_service() as client:
        yield client


# The shift data model, as a test arranges one.  Here rather than in
# either test module: collection and editing both read what a category
# asks for, and two builders would let the two see different models
# while both claimed to describe the same one.
SHIFT_CALENDAR = 'events'
REPEATING_SHIFT_CALENDAR = 'practices'
SHIFT_NEED_ID = '879609'
OTHER_SHIFT_NEED_ID = '879610'


def a_need(
    identifier: str = SHIFT_NEED_ID,
    offset_start: int = 15,
    offset_end: int = 30,
    max_length: Any = 165,
    slots: int = 12
) -> Dict[str, Any]:
    """ Return one need ID's entry in a category. """
    return {
        'id': identifier,
        'offset_start': offset_start,
        'offset_end': offset_end,
        'max_length': max_length,
        'slots': slots
    }


def a_category(
    need_ids: List[Dict[str, Any]],
    aliases: tuple = ('wheels',)
) -> Dict[str, Any]:
    """ Return one category of the shift data model. """
    return {
        'description': 'Adult Games',
        'aliases': list(aliases),
        'need_ids': need_ids
    }


def a_model(
    categories: Dict[str, Any],
    calendars: tuple = (SHIFT_CALENDAR, REPEATING_SHIFT_CALENDAR)
) -> Dict[str, Any]:
    """ Return a shift data model holding one set of categories.

        Every named calendar is given the same categories, so a test
        can read either one without arranging a second model.
    """
    entry = {
        'categories': categories,
        'default': {
            'description': 'Unknown Game',
            'need_ids': [a_need(identifier='')]
        }
    }

    return {'calendar': {calendar: entry for calendar in calendars}}


@pytest.fixture(name='shift_model')
def fixture_shift_model(
    monkeypatch: pytest.MonkeyPatch
) -> Callable[..., None]:
    """ Return a way to replace the shift data model. """

    def replace(
        categories: Dict[str, Any],
        calendars: tuple = (SHIFT_CALENDAR, REPEATING_SHIFT_CALENDAR)
    ) -> None:
        monkeypatch.setattr(
            _models,
            'get_shifts_info',
            lambda: a_model(categories=categories, calendars=calendars)
        )

    return replace
