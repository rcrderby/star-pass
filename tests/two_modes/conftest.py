#!/usr/bin/env python3
""" Asking both modes the same thing, and comparing the two answers.

    The command line works with no server running, which only holds
    while both modes answer the same question the same way.  So every
    operation is asked of both and the answers are compared -- not
    described and checked separately, which would compare two
    descriptions rather than two answers.

    A directory with a conftest of its own rather than a module, so the
    two halves of the comparison -- the reads and the writes -- can be
    two files sharing this harness.  Everything the rest of the suite
    uses is inherited from the conftest above.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

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
from star_pass_client import ApiProblem, Client, LocalClient
from two_modes._asked import A_COLLECTION

# Constants
# Where the in-process application answers.  A name rather than a host:
# nothing resolves it, because nothing sends to it.
SERVICE_URL = 'http://star-pass.test'


class InProcessAdapter(BaseAdapter):
    """ Hands a request to an application instead of to a socket.

        Counts what it was asked for, which lets a test prove the
        remote half was really used.

        Waits for what the request started.  A write the service
        answers leaves a job running on a thread and answers before
        that job is done; the local half has no such gap.  Without the
        wait, a comparison would pass or fail depending on which
        thread got there first.
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

        for started in self._served_by.app.state.runner.futures:
            started.result()

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
    started_client: TestClient
) -> InProcessAdapter:
    """ Return the adapter the remote client answers through.

        A service whose jobs can be waited for, because the adapter
        waits for them: what these tests compare is what each mode has
        finished doing.
    """
    return InProcessAdapter(served_by=started_client)


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

    def nothing(
        connection: Any,
        run_id: str,
        reporter: Any,
        principal_id: str
    ) -> None:
        """ Stand in for the collection. """
        del connection, run_id, reporter, principal_id

    monkeypatch.setattr('star_pass_api._runs.collect', nothing)
    monkeypatch.setattr('star_pass_client._local_writes.collect', nothing)

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


@pytest.fixture(name='problem_from')
def fixture_problem_from() -> Callable[..., ApiProblem]:
    """ Return a way to read the failure an operation raised. """

    def raised(
        client: Any,
        operation: str,
        **parameters: Any
    ) -> ApiProblem:
        """ Return the failure, failing the test if there was none. """
        with pytest.raises(ApiProblem) as error:
            getattr(client, operation)(**parameters)

        return error.value

    return raised


@pytest.fixture(name='both_refuse')
def fixture_both_refuse(
    local_client: LocalClient,
    remote_client: Client,
    problem_from: Callable[..., ApiProblem]
) -> Callable[..., int]:
    """ Return a way to check both modes refuse one thing the same way.

        The run identifiers differ, because each mode minted its own,
        so they are taken out of the messages before those are
        compared.  What is left is the wording, which must not differ.
    """

    def refused(
        collected: Tuple[str, str],
        operation: str = 'recollect_run',
        **parameters: Any
    ) -> int:
        """ Return the status both modes refused with. """
        local_run, remote_run = collected
        local = problem_from(
            local_client,
            operation,
            run_id=local_run,
            **parameters
        )
        remote = problem_from(
            remote_client,
            operation,
            run_id=remote_run,
            **parameters
        )

        assert local.status == remote.status
        assert local.detail.replace(local_run, '') == (
            remote.detail.replace(remote_run, '')
        )

        return local.status

    return refused
