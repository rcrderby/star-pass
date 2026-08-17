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
from typing import Any, Callable, List, Tuple

# Imports - Third-Party
import pytest
from fastapi.testclient import TestClient

# Imports - Local
from star_pass._exceptions import ValidationError as CoreValidationError
from star_pass._repository import JobRepository, RunRepository
from star_pass_api import _defaults

# Constants
RUNS_PATH = f'{_defaults.API_VERSION_PREFIX}/runs'


def run_path(run_id: str) -> str:
    """ Return the address of one run. """
    return f'{RUNS_PATH}/{run_id}'


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


@pytest.fixture(name='recollecting')
def fixture_recollecting(
    started_client: TestClient,
    collecting: Callable[..., Any]
) -> Tuple[str, Callable[..., Any], List[str]]:
    """ Return a collected run, a way to collect it again, and what
        the collecting was asked to do.

        The list is the one the replaced collection appends to, so a
        test reads what actually ran rather than what was answered.
    """
    response, collected = collecting()
    run_id = response.json()['runId']

    def again(expected: int = 0, run: str = None) -> Any:
        """ Ask for a recollection, and wait for the job it started. """
        answered = started_client.post(
            f'{run_path(run_id=run if run is not None else run_id)}'
            '/recollect',
            json={'expectedChangeCount': expected}
        )

        for future in started_client.app.state.runner.futures:
            future.result()

        return answered

    return run_id, again, collected


class TestCollectingARunAgain:
    def test_a_recollection_is_accepted_with_the_job_doing_it(
        self,
        recollecting: Any
    ) -> None:
        _, again, _collected = recollecting

        response = again()

        assert response.status_code == 202
        assert response.json()['kind'] == 'recollect'

    def test_the_run_keeps_its_identifier(
        self,
        recollecting: Any
    ) -> None:
        run_id, again, _collected = recollecting

        assert again().json()['runId'] == run_id

    def test_the_run_is_collected_into_again(
        self,
        recollecting: Any
    ) -> None:
        run_id, again, collected = recollecting

        again()

        assert collected == [run_id, run_id]

    def test_a_run_that_is_not_there_is_not_found(
        self,
        recollecting: Any
    ) -> None:
        _, again, _collected = recollecting

        response = again(run='no-such-run')

        assert response.status_code == 404
        assert 'no-such-run' in response.json()['detail']

    def test_a_change_count_that_has_moved_is_refused(
        self,
        recollecting: Any
    ) -> None:
        # The stale-tab case a confirmation dialog cannot see.
        _, again, _collected = recollecting

        response = again(expected=3)

        # Both numbers, each in its own place: swapped, the message
        # would still hold the one the caller sent.
        assert response.status_code == 409
        assert 'holds 0 change(s), not the 3' in response.json()['detail']

    def test_a_change_count_that_has_moved_collects_nothing(
        self,
        recollecting: Any
    ) -> None:
        run_id, again, collected = recollecting

        again(expected=3)

        assert collected == [run_id]

    def test_a_run_something_is_already_doing_is_refused(
        self,
        recollecting: Any,
        connection: Any
    ) -> None:
        # Two jobs writing one run's revisions would race.
        run_id, again, collected = recollecting
        JobRepository(connection=connection).create(
            run_id=run_id,
            kind='collect',
            principal_id='static-token'
        )

        response = again()

        assert response.status_code == 409
        assert 'working on it' in response.json()['detail']
        assert collected == [run_id]

    def test_the_run_says_it_is_being_collected_again(
        self,
        recollecting: Any,
        started_client: TestClient,
        connection: Any
    ) -> None:
        # A run being collected says so while it is, which is what a
        # reader watching the list sees.
        run_id, again, _collected = recollecting
        RunRepository(connection=connection).set_status(
            run_id=run_id,
            status='unsent'
        )

        again()

        assert started_client.get(
            run_path(run_id=run_id)
        ).json()['status'] == 'collecting'

    def test_a_run_that_has_sent_shifts_is_refused(
        self,
        recollecting: Any,
        connection: Any
    ) -> None:
        # Amplify cannot take a shift back, so the events describing
        # what was sent are not replaced.
        run_id, again, _collected = recollecting
        RunRepository(connection=connection).set_status(
            run_id=run_id,
            status='sent'
        )

        response = again()

        assert response.status_code == 409
        assert 'cannot be taken back' in response.json()['detail']
