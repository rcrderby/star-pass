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
from star_pass_client import (
    ApiProblem,
    Client,
    LocalClient,
    LocalOperationUnavailable
)
from star_pass_client._local import HANDLERS, UNAVAILABLE
from star_pass_client._generator import specification

# Constants
# Where the in-process application answers.  A name rather than a host:
# nothing resolves it, because nothing sends to it.
SERVICE_URL = 'http://star-pass.test'


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
        before = len(adapter.requests)
        answers = (
            getattr(local_client, operation)(**parameters),
            getattr(remote_client, operation)(**parameters)
        )

        assert len(adapter.requests) == before + 1, (
            f'{operation} did not reach the service, so the two '
            'answers compared did not come from two modes.'
        )

        return answers

    return ask


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
