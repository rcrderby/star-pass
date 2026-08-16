#!/usr/bin/env python3
""" Asking the service to collect a calendar window into a run.

    What a collection does is pinned in 'test_collect.py', and it is
    replaced here.  These tests ask a narrower question: that the
    endpoint creates the run before it answers, hands the work to the
    runner, and refuses what it cannot carry out before anything is
    written.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
from typing import Any, Callable, List

# Imports - Third-Party
import pytest
from fastapi.testclient import TestClient

# Imports - Local
from star_pass._exceptions import ValidationError as CoreValidationError
from star_pass._job_runner import JobRunner
from star_pass._repository import JobRepository
from star_pass_api import _defaults

# Constants
RUNS_PATH = f'{_defaults.API_VERSION_PREFIX}/runs'


def run_path(run_id: str) -> str:
    """ Return the address of one run. """
    return f'{RUNS_PATH}/{run_id}'


class WaitingRunner(JobRunner):
    """ The real runner, with a way to wait for what it was given.

        A job runs on a thread, so a test that read the database
        straight after asking for one would be racing it.  This is not
        a stand-in for the runner: it is the runner, keeping the
        futures it already returns so a test can wait on the last one.
    """

    def __init__(self, connect: Any) -> None:
        """ Run one job at a time and remember them. """
        super().__init__(connect=connect, workers=1)
        self.futures: List[Any] = []

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
        connect=running_client.app.state.runner.__dict__['_connect']
    )

    return running_client


@pytest.fixture(name='collecting')
def fixture_collecting(
    started_client: TestClient,
    monkeypatch: pytest.MonkeyPatch
) -> Callable[..., Any]:
    """ Return a way to ask for a collection and wait for it.

        The collecting itself is replaced.  What it does is pinned in
        'test_collect.py'; this asks whether the endpoint creates the
        run, hands the work over, and answers with the job.
    """
    collected: List[str] = []

    def record(connection: Any, run_id: str, reporter: Any) -> None:
        """ Stand in for the collection, recording the run. """
        del connection, reporter
        collected.append(run_id)

    monkeypatch.setattr('star_pass_api._runs.collect', record)

    def ask(
        calendar: str = 'events',
        start: str = '2026-09-01',
        end: str = '2026-10-01'
    ) -> Any:
        """ Ask for a collection, and wait for the job it started. """
        response = started_client.post(
            RUNS_PATH,
            json={
                'calendar': calendar,
                'window': {'start': start, 'end': end}
            }
        )

        for future in started_client.app.state.runner.futures:
            future.result()

        return response, collected

    return ask


class TestCollectingARun:
    def test_a_collection_is_accepted_with_the_job_doing_it(
        self,
        collecting: Callable[..., Any]
    ) -> None:
        response, _ = collecting()

        assert response.status_code == 202
        assert response.json()['kind'] == 'collect'

    def test_the_run_exists_before_the_answer_comes_back(
        self,
        collecting: Callable[..., Any],
        started_client: TestClient
    ) -> None:
        # What makes a collection reattachable: somebody who closed
        # the page finds the run in the list rather than nothing.
        response, _ = collecting()
        run_id = response.json()['runId']

        listed = started_client.get(RUNS_PATH).json()

        assert [one['id'] for one in listed] == [run_id]

    def test_the_run_is_collected_into(
        self,
        collecting: Callable[..., Any]
    ) -> None:
        response, collected = collecting()

        assert collected == [response.json()['runId']]

    def test_the_run_records_what_was_asked_for(
        self,
        collecting: Callable[..., Any],
        started_client: TestClient
    ) -> None:
        response, _ = collecting()
        run_id = response.json()['runId']

        run = started_client.get(run_path(run_id=run_id)).json()

        assert run['calendar'] == 'events'
        assert run['window']['start'] == '2026-09-01'
        assert run['window']['end'] == '2026-10-01'

    def test_the_job_records_who_asked_for_it(
        self,
        collecting: Callable[..., Any],
        started_client: TestClient
    ) -> None:
        response, _ = collecting()
        run = started_client.get(
            run_path(run_id=response.json()['runId'])
        ).json()

        assert run['activeJobId'] is None or run['activeJobId']

    def test_a_run_whose_job_cannot_be_written_is_not_created(
        self,
        collecting: Callable[..., Any],
        started_client: TestClient,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A run with no job is one nothing is working on and nothing
        # will, so either both are written or neither is.
        def refuse(*_: Any, **__: Any) -> None:
            raise CoreValidationError('The job could not be written.')

        monkeypatch.setattr(JobRepository, 'create', refuse)
        collecting()

        assert started_client.get(RUNS_PATH).json() == []

    def test_a_calendar_the_service_does_not_read_is_refused(
        self,
        collecting: Callable[..., Any]
    ) -> None:
        # A 4xx carries its reason: the caller chose this and is the
        # one who can correct it.
        response, _ = collecting(calendar='knitting')

        assert response.status_code == 422
        assert 'knitting' in response.json()['detail']
        assert 'events' in response.json()['detail']

    def test_a_calendar_the_service_does_not_read_collects_nothing(
        self,
        collecting: Callable[..., Any],
        started_client: TestClient
    ) -> None:
        collecting(calendar='knitting')

        assert started_client.get(RUNS_PATH).json() == []

    @pytest.mark.parametrize(
        'start, end',
        [
            ('2026-10-01', '2026-09-01'),
            ('2026-09-01', '2026-09-01'),
            ('the first of September', '2026-10-01'),
            ('2026-09-01', '')
        ]
    )
    def test_a_window_selecting_no_days_is_refused(
        self,
        collecting: Callable[..., Any],
        start: str,
        end: str
    ) -> None:
        response, _ = collecting(start=start, end=end)

        assert response.status_code == 422

    def test_a_one_day_window_is_accepted(
        self,
        collecting: Callable[..., Any]
    ) -> None:
        # The end is exclusive, so one day is two consecutive dates.
        response, _ = collecting(start='2026-09-01', end='2026-09-02')

        assert response.status_code == 202

    def test_a_window_longer_than_sixty_days_is_accepted(
        self,
        collecting: Callable[..., Any]
    ) -> None:
        # An earlier design invented a cap; it is not real.
        response, _ = collecting(start='2026-01-01', end='2026-12-31')

        assert response.status_code == 202

    def test_the_contract_says_collecting_needs_the_write_scope(
        self,
        api: Any
    ) -> None:
        # Read from the published contract rather than from the
        # route's internals: what a client is told it needs is the
        # thing that has to be right.
        published = api.openapi()['paths'][RUNS_PATH]['post']

        assert [
            scope
            for requirement in published['security']
            for scope in requirement.values()
        ] == [['runs:write']]
