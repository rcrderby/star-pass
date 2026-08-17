#!/usr/bin/env python3
""" The two modes answer the same question the same way.

    D2 lets the command line client work with no server running, and
    that is only worth having while both modes agree.  The plan is
    explicit about the consequence: if local and remote start behaving
    differently, the core boundary has leaked and HTTP-only becomes
    the honest fix.

    So these tests do not check the local client against what it was
    written to return.  They run BOTH clients over ONE database and
    compare the answers to each other.  A difference fails here, which
    is the only place it is cheap to find.

    The remote client is the real one -- its session, its headers, its
    timeouts, its failure mapping -- driven against the real
    application through an adapter that hands the request to it in
    process.  No port is bound: a test that needed one would be
    testing the socket as well.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring
# pylint: disable=too-many-arguments,too-many-positional-arguments

# Imports - Python Standard Library
import sqlite3
from io import BytesIO
from typing import Any, Callable, List, Tuple

# Imports - Third-Party
import pytest
from fastapi.testclient import TestClient
from requests import Response, Session
from requests.adapters import BaseAdapter

# Imports - Local
from star_pass._exceptions import ValidationError as CoreValidationError
from star_pass._records import RUN_STATUS_SENT
from star_pass._repository import RunRepository
from star_pass._repository import JobRepository
from star_pass_api._defaults import API_PRINCIPAL_ID
from star_pass_client import (
    ApiProblem,
    Client,
    LocalClient,
    LocalOperationUnavailable
)
from star_pass_client._generator import specification
from star_pass_client._local import HANDLERS, UNAVAILABLE

# Constants
# Where the in-process application answers.  A name rather than a host:
# nothing resolves it, because nothing sends to it.
SERVICE_URL = 'http://star-pass.test'

# What both modes are asked to collect.
A_COLLECTION = {
    'calendar': 'events',
    'window': {'start': '2026-09-01', 'end': '2026-10-01'}
}

# A recollection of a run nothing has been done to since.
NO_CHANGES = {'expectedChangeCount': 0}


class InProcessAdapter(BaseAdapter):
    """ Hands a request to an application instead of to a socket.

        Counts what it was asked for, which is what lets a test prove
        the remote half was really used.  Without that, a harness that
        asked the same client twice would compare an answer with
        itself and pass while testing nothing.
    """

    def __init__(
        self,
        served_by: TestClient
    ) -> None:
        """ Answer through the given application. """
        super().__init__()
        self._served_by = served_by
        self.requests: List[str] = []

    # Stands in for a transport adapter and never reaches a socket.
    # pylint: disable=arguments-differ
    def send(self, request, **kwargs) -> Response:
        """ Return what the application answered. """
        del kwargs

        self.requests.append(request.url)
        answered = self._served_by.request(
            method=request.method,
            url=request.url,
            headers=dict(request.headers),
            content=request.body
        )

        response = Response()
        response.status_code = answered.status_code
        response.headers.update(answered.headers)
        # pylint: disable=protected-access
        response._content = answered.content
        response.raw = BytesIO(answered.content)
        response.url = request.url

        return response

    def close(self) -> None:
        """ Release nothing: the application is not this test's. """
        return None


@pytest.fixture(name='adapter')
def fixture_adapter(
    running_client: TestClient
) -> InProcessAdapter:
    """ Return the adapter the remote client answers through. """
    return InProcessAdapter(served_by=running_client)


@pytest.fixture(name='remote_client')
def fixture_remote_client(
    adapter: InProcessAdapter,
    api_credential: str
) -> Client:
    """ Return the real remote client, answered in process. """
    session = Session()
    session.mount(SERVICE_URL, adapter)

    return Client(
        base_url=SERVICE_URL,
        token=api_credential,
        session=session
    )


@pytest.fixture(name='local_client')
def fixture_local_client(
    connect_to_database: Callable[[], sqlite3.Connection]
) -> LocalClient:
    """ Return a local client on the same database. """
    return LocalClient(connect_to=connect_to_database)


@pytest.fixture(name='collecting_service')
def fixture_collecting_service(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """ Replace the collecting itself in both modes.

        What a collection does is pinned in 'test_collect.py'.  What
        these tests ask is whether the two modes create the same
        things and refuse the same requests, which the reading of a
        calendar would only slow down.
    """

    def nothing(connection: Any, run_id: str, reporter: Any) -> None:
        """ Stand in for the collection. """
        del connection, run_id, reporter

    monkeypatch.setattr('star_pass_api._runs.collect', nothing)
    monkeypatch.setattr('star_pass_client._local.collect', nothing)

    return None


@pytest.fixture(name='collected_in_both')
def fixture_collected_in_both(
    both: Callable[..., Tuple[Any, Any]]
) -> Tuple[str, str]:
    """ Return a run each mode collected, for asking about again.

        Two runs rather than one: each mode mints its own identifier,
        and a recollection is about a run rather than about a shape,
        so the pair is what a comparison needs.
    """
    local, remote = both('collect_run', body=A_COLLECTION)

    return local['runId'], remote['runId']


@pytest.fixture(name='both')
def fixture_both(
    adapter: InProcessAdapter,
    local_client: LocalClient,
    remote_client: Client
) -> Callable[..., Tuple[Any, Any]]:
    """ Return a way to ask both clients the same thing.

        The count of requests the adapter saw is checked around the
        pair, because comparing two answers proves nothing unless they
        came from different places: a harness that asked one client
        twice would compare an answer with itself and pass.
    """

    def ask(operation: str, **parameters: Any) -> Tuple[Any, Any]:
        """ Return what each client answered, local first. """
        return asked(
            operation=operation,
            local=parameters,
            remote=parameters
        )

    def asked(
        operation: str,
        local: dict,
        remote: dict
    ) -> Tuple[Any, Any]:
        """ Ask each client with parameters of its own.

            A run is minted by whichever mode collected it, so an
            operation addressing one is asked with a different
            identifier in each mode.  What is compared is still one
            answer from each.
        """
        before = len(adapter.requests)
        answers = (
            getattr(local_client, operation)(**local),
            getattr(remote_client, operation)(**remote)
        )

        assert len(adapter.requests) == before + 1, (
            f'{operation} did not reach the service, so the two '
            'answers compared did not come from two modes.'
        )

        return answers

    ask.asked = asked

    return ask


def both_refuse(
    local_client: Any,
    remote_client: Any,
    collected: Tuple[str, str],
    body: dict
) -> int:
    """ Return the status both modes refused a recollection with.

        The run identifiers differ, because each mode minted its own,
        so they are taken out of the messages before those are
        compared.  What is left is the wording, which must not differ.
    """
    local_run, remote_run = collected
    local = problem_from(
        local_client,
        'recollect_run',
        run_id=local_run,
        body=body
    )
    remote = problem_from(
        remote_client,
        'recollect_run',
        run_id=remote_run,
        body=body
    )

    assert local.status == remote.status
    assert local.detail.replace(local_run, '') == (
        remote.detail.replace(remote_run, '')
    )

    return local.status


def problem_from(
    client: Any,
    operation: str,
    **parameters: Any
) -> ApiProblem:
    """ Return the failure an operation raised, failing if it did not. """
    with pytest.raises(ApiProblem) as error:
        getattr(client, operation)(**parameters)

    return error.value


class TestTheTwoModesAgree:
    def test_the_runs_read_the_same(
        self,
        both: Callable[..., Tuple[Any, Any]],
        populated: str
    ) -> None:
        local, remote = both('list_runs')

        assert local == remote
        assert [run['id'] for run in local] == [populated]

    def test_one_run_reads_the_same(
        self,
        both: Callable[..., Tuple[Any, Any]],
        populated: str
    ) -> None:
        local, remote = both('get_run', run_id=populated)

        assert local == remote
        # Guard against both answering an empty document identically.
        assert len(local['events']) == 4
        assert local['opportunities']

    def test_the_revisions_read_the_same(
        self,
        both: Callable[..., Tuple[Any, Any]],
        populated: str
    ) -> None:
        local, remote = both('list_revisions', run_id=populated)

        assert local == remote
        assert [item['number'] for item in local] == [1, 2]

    def test_the_preview_reads_the_same(
        self,
        both: Callable[..., Tuple[Any, Any]],
        populated: str
    ) -> None:
        local, remote = both('get_preview', run_id=populated)

        assert local == remote
        assert local['totals']['willCreate']
        assert local['totals']['repeatedRows']
        assert local['blockers']

    def test_a_job_reads_the_same(
        self,
        both: Callable[..., Tuple[Any, Any]],
        job_id: str
    ) -> None:
        local, remote = both('get_job', job_id=job_id)

        assert local == remote
        assert local['id'] == job_id

    def test_the_version_reads_the_same(
        self,
        both: Callable[..., Tuple[Any, Any]]
    ) -> None:
        local, remote = both('get_version')

        assert local == remote

    def test_an_empty_database_reads_the_same(
        self,
        both: Callable[..., Tuple[Any, Any]],
        service_database: Any
    ) -> None:
        del service_database

        local, remote = both('list_runs')

        assert local == remote == []


class TestTheTwoModesFailTheSame:
    def test_an_unknown_run_fails_the_same(
        self,
        local_client: LocalClient,
        remote_client: Client
    ) -> None:
        local = problem_from(local_client, 'get_run', run_id='no-such-run')
        remote = problem_from(
            remote_client,
            'get_run',
            run_id='no-such-run'
        )

        assert local.status == remote.status == 404
        assert local.detail == remote.detail
        assert 'no-such-run' in local.detail

    def test_an_unknown_job_fails_the_same(
        self,
        local_client: LocalClient,
        remote_client: Client
    ) -> None:
        local = problem_from(local_client, 'get_job', job_id='no-such-job')
        remote = problem_from(
            remote_client,
            'get_job',
            job_id='no-such-job'
        )

        assert local.status == remote.status == 404
        assert local.detail == remote.detail

    def test_an_unknown_run_fails_the_same_for_every_run_operation(
        self,
        local_client: LocalClient,
        remote_client: Client
    ) -> None:
        for operation in ('get_run', 'list_revisions', 'get_preview'):
            local = problem_from(
                local_client,
                operation,
                run_id='no-such-run'
            )
            remote = problem_from(
                remote_client,
                operation,
                run_id='no-such-run'
            )

            assert local.detail == remote.detail, operation


class TestTheTwoModesCollectTheSame:
    def test_a_collection_answers_with_the_same_kind_of_job(
        self,
        both: Callable[..., Tuple[Any, Any]],
        collecting_service: None
    ) -> None:
        del collecting_service
        local, remote = both('collect_run', body=A_COLLECTION)

        assert local['kind'] == remote['kind'] == 'collect'
        assert local['runId'] != remote['runId']

    def test_each_collection_produces_a_run_of_its_own(
        self,
        both: Callable[..., Tuple[Any, Any]],
        collecting_service: None,
        local_client: LocalClient
    ) -> None:
        del collecting_service
        both('collect_run', body=A_COLLECTION)

        assert len(local_client.list_runs()) == 2

    def test_a_local_collection_records_who_asked(
        self,
        local_client: LocalClient,
        collecting_service: None,
        connection: sqlite3.Connection
    ) -> None:
        # The column exists so that two writers can be told apart
        # (D13), and a local run is not the service acting.
        del collecting_service
        answered = local_client.collect_run(body=A_COLLECTION)

        recorded = JobRepository(connection=connection).get(
            job_id=answered['id']
        ).principal_id

        assert recorded == 'local-cli'
        assert recorded != API_PRINCIPAL_ID

    def test_a_local_collection_is_over_when_it_answers(
        self,
        local_client: LocalClient,
        collecting_service: None
    ) -> None:
        # The process that would run the job is the one about to
        # return, so the work happens in the call.
        del collecting_service
        answered = local_client.collect_run(body=A_COLLECTION)

        assert answered['status'] == 'succeeded'
        assert answered['finishedAt'] is not None

    def test_a_local_run_whose_job_cannot_be_written_is_not_created(
        self,
        local_client: LocalClient,
        collecting_service: None,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        del collecting_service

        def refuse(*_: Any, **__: Any) -> None:
            raise CoreValidationError('The job could not be written.')

        monkeypatch.setattr(JobRepository, 'create', refuse)

        with pytest.raises(CoreValidationError):
            local_client.collect_run(body=A_COLLECTION)

        assert local_client.list_runs() == []

    def test_a_calendar_neither_mode_reads_fails_the_same(
        self,
        local_client: LocalClient,
        remote_client: Client
    ) -> None:
        asked = {**A_COLLECTION, 'calendar': 'knitting'}
        local = problem_from(local_client, 'collect_run', body=asked)
        remote = problem_from(remote_client, 'collect_run', body=asked)

        assert local.status == remote.status == 422
        assert local.detail == remote.detail
        assert 'knitting' in local.detail

    def test_a_window_neither_mode_accepts_fails_the_same(
        self,
        local_client: LocalClient,
        remote_client: Client
    ) -> None:
        asked = {
            **A_COLLECTION,
            'window': {'start': '2026-10-01', 'end': '2026-09-01'}
        }
        local = problem_from(local_client, 'collect_run', body=asked)
        remote = problem_from(remote_client, 'collect_run', body=asked)

        assert local.status == remote.status == 422
        assert local.detail == remote.detail

    def test_a_refused_collection_creates_no_run_in_either_mode(
        self,
        local_client: LocalClient,
        remote_client: Client
    ) -> None:
        asked = {**A_COLLECTION, 'calendar': 'knitting'}

        for client in (local_client, remote_client):
            with pytest.raises(ApiProblem):
                client.collect_run(body=asked)

        assert local_client.list_runs() == []


class TestTheTwoModesCollectAgainTheSame:
    def test_a_recollection_answers_with_a_job_on_the_same_run(
        self,
        both: Callable[..., Tuple[Any, Any]],
        collecting_service: None,
        collected_in_both: Tuple[str, str]
    ) -> None:
        # One question, not two: a recollection answers with a job of
        # the right kind, working on the run it was asked about, and
        # a mode that got either wrong would be answering about
        # something else.
        del collecting_service
        local_run, remote_run = collected_in_both

        local, remote = both.asked(
            operation='recollect_run',
            local={'run_id': local_run, 'body': NO_CHANGES},
            remote={'run_id': remote_run, 'body': NO_CHANGES}
        )

        assert local['kind'] == remote['kind'] == 'recollect'
        assert local['runId'] == local_run
        assert remote['runId'] == remote_run

    def test_a_run_neither_mode_has_fails_the_same(
        self,
        local_client: LocalClient,
        remote_client: Client
    ) -> None:
        local = problem_from(
            local_client,
            'recollect_run',
            run_id='no-such-run',
            body=NO_CHANGES
        )
        remote = problem_from(
            remote_client,
            'recollect_run',
            run_id='no-such-run',
            body=NO_CHANGES
        )

        assert local.status == remote.status == 404
        assert local.detail == remote.detail

    def test_a_change_count_that_has_moved_fails_the_same(
        self,
        collecting_service: None,
        collected_in_both: Tuple[str, str],
        local_client: LocalClient,
        remote_client: Client
    ) -> None:
        del collecting_service
        moved = {'expectedChangeCount': 3}

        assert both_refuse(
            local_client=local_client,
            remote_client=remote_client,
            collected=collected_in_both,
            body=moved
        ) == 409

    def test_a_sent_run_fails_the_same(
        self,
        collecting_service: None,
        collected_in_both: Tuple[str, str],
        local_client: LocalClient,
        remote_client: Client,
        runs: RunRepository
    ) -> None:
        del collecting_service

        for run_id in collected_in_both:
            runs.set_status(run_id=run_id, status=RUN_STATUS_SENT)

        assert both_refuse(
            local_client=local_client,
            remote_client=remote_client,
            collected=collected_in_both,
            body=NO_CHANGES
        ) == 409


class TestWhatLocalModeCannotDo:
    def test_every_operation_is_handled_or_declared_unavailable(
        self
    ) -> None:
        # The point of generating the surface: an endpoint added to
        # the contract without a local answer fails here rather than
        # being discovered when somebody runs the command.
        published = {
            (verb.upper(), path)
            for path, verbs in specification()['paths'].items()
            for verb in verbs
        }

        assert published == set(HANDLERS) | set(UNAVAILABLE)

    def test_nothing_is_both_handled_and_unavailable(self) -> None:
        assert not set(HANDLERS) & set(UNAVAILABLE)

    def test_health_says_why_it_has_no_local_answer(
        self,
        local_client: LocalClient
    ) -> None:
        with pytest.raises(LocalOperationUnavailable) as error:
            local_client.get_health()

        assert 'nothing is serving' in str(error.value).lower()

    def test_following_a_job_says_why_it_has_no_local_answer(
        self,
        local_client: LocalClient
    ) -> None:
        with pytest.raises(LocalOperationUnavailable) as error:
            list(local_client.stream_job_events(job_id='j-1'))

        assert 'local mode' in str(error.value)

    def test_the_two_clients_offer_the_same_operations(
        self,
        local_client: LocalClient,
        remote_client: Client
    ) -> None:
        # Both inherit the generated surface, so this holds by
        # construction -- and the test is what says so out loud if
        # either ever stops inheriting it.
        published = {
            operation['operationId']
            for verbs in specification()['paths'].values()
            for operation in verbs.values()
        }

        for name in published:
            assert callable(getattr(local_client, name))
            assert callable(getattr(remote_client, name))
