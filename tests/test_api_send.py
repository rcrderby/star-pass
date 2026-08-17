#!/usr/bin/env python3
""" Asking the service to put a run's shifts into Amplify.

    What a send does is pinned in 'test_send.py', and it is replaced
    here.  These tests ask a narrower question: that the endpoint
    refuses what it cannot carry out before anything is written, claims
    the idempotency key before it hands the work over, and answers a
    request arriving on a used key from what the first one recorded.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
from typing import Any, Callable, Dict, List, Tuple

# Imports - Third-Party
import pytest
from fastapi.testclient import TestClient

# Imports - Local
from star_pass._records import (
    JOB_KIND_SEND,
    JOB_STATUS_RUNNING,
    RUN_STATUS_COLLECTING,
    RUN_STATUS_UNSENT
)
from star_pass._records import Event
from star_pass._repository import (
    EventRepository,
    IdempotencyRepository,
    JobRepository,
    RevisionRepository,
    RunRepository
)
from star_pass_api import _defaults
from star_pass_contract import IDEMPOTENCY_KEY_HEADER

# Constants
RUNS_PATH = f'{_defaults.API_VERSION_PREFIX}/runs'
PROBLEM_MEDIA_TYPE = 'application/problem+json'

# The opportunity the fixtures' events send to, and what one attempt
# to send is named.  Named rather than called a key: a constant whose
# name reads as a credential is one the secret scanner stops on.
NEED_ID = '905196'
SEND_ATTEMPT = 'send-attempt-one'


def send_path(run_id: str) -> str:
    """ Return the address a run is sent from. """
    return f'{RUNS_PATH}/{run_id}/send'


@pytest.fixture(name='sending')
def fixture_sending(
    started_client: TestClient,
    finish_jobs: Callable[[], None],
    amplify_holds: Callable[..., list],
    monkeypatch: pytest.MonkeyPatch
) -> Callable[..., Any]:
    """ Return a way to ask for a send and wait for it.

        The sending itself is replaced.  What it does is pinned in
        'test_send.py'; this asks whether the endpoint refuses, claims
        the key and hands the work over.  Amplify still answers the
        read the endpoint makes before deciding, because that read is
        what the expected count is checked against.
    """
    amplify_holds()
    asked: List[Tuple[str, str]] = []

    def record(
        connection: Any,
        run_id: str,
        reporter: Any,
        principal_id: str,
        idempotency_key: str
    ) -> None:
        """ Stand in for the send, recording what it was given. """
        del connection, reporter, principal_id
        asked.append((run_id, idempotency_key))

    monkeypatch.setattr('star_pass_api._sending.send', record)

    def ask(
        run_id: str,
        expected: int = 1,
        key: str = SEND_ATTEMPT
    ) -> Any:
        """ Ask for a send, and wait for the job it started. """
        response = started_client.post(
            send_path(run_id=run_id),
            json={'expectedShiftCount': expected},
            headers={IDEMPOTENCY_KEY_HEADER: key}
        )
        finish_jobs()

        return response, asked

    return ask


@pytest.fixture(name='another_sendable_run')
def fixture_another_sendable_run(
    events: EventRepository,
    revisions: RevisionRepository,
    runs: RunRepository,
    other_run_id: str,
    make_event: Callable[..., Event]
) -> str:
    """ Return a second run asking for as many shifts as the first. """
    revision = revisions.create(run_id=other_run_id, label='As collected')
    events.add(
        run_id=other_run_id,
        revision=revision.number,
        event=make_event()
    )
    runs.set_status(run_id=other_run_id, status=RUN_STATUS_UNSENT)

    return other_run_id


class TestStartingASend:
    def test_a_send_answers_with_the_job_doing_it(
        self,
        sending: Callable[..., Any],
        collected: str
    ) -> None:
        response, _asked = sending(collected)

        assert response.status_code == 202
        assert response.json()['runId'] == collected
        assert response.json()['kind'] == JOB_KIND_SEND

    def test_the_work_is_handed_over_with_the_key_it_was_asked_under(
        self,
        sending: Callable[..., Any],
        collected: str
    ) -> None:
        # The key reaches the record of every row the send creates
        # (D13), so a send given the wrong one would record the wrong
        # attempt.
        _response, asked = sending(collected)

        assert asked == [(collected, SEND_ATTEMPT)]

    def test_the_job_is_recorded_against_the_run(
        self,
        sending: Callable[..., Any],
        jobs: JobRepository,
        collected: str
    ) -> None:
        response, _asked = sending(collected)

        job = jobs.get(job_id=response.json()['id'])

        assert job.run_id == collected
        assert job.kind == JOB_KIND_SEND


class TestWhatIsRefused:
    def test_an_unknown_run_is_not_found(
        self,
        sending: Callable[..., Any]
    ) -> None:
        response, _asked = sending('no-such-run')

        assert response.status_code == 404
        assert response.headers['content-type'] == PROBLEM_MEDIA_TYPE

    def test_a_count_that_has_moved_is_refused(
        self,
        sending: Callable[..., Any],
        collected: str
    ) -> None:
        # The stale-tab case: a number read from a page somebody left
        # open describes a moment that has passed.
        response, asked = sending(collected, expected=7)

        assert response.status_code == 409
        assert '7' in response.json()['detail']
        assert asked == []

    def test_a_run_already_being_worked_on_is_refused(
        self,
        sending: Callable[..., Any],
        working_on: Callable[..., Any],
        collected: str
    ) -> None:
        # Two sends of one run would both write into Amplify.
        working = working_on(collected)

        response, asked = sending(collected)

        assert response.status_code == 409
        assert working.id in response.json()['detail']
        assert asked == []

    def test_a_run_still_being_collected_is_refused(
        self,
        sending: Callable[..., Any],
        runs: RunRepository,
        collected: str
    ) -> None:
        runs.set_status(run_id=collected, status=RUN_STATUS_COLLECTING)

        response, asked = sending(collected)

        assert response.status_code == 409
        assert 'collected' in response.json()['detail']
        assert asked == []

    def test_a_blocked_event_stops_the_send(
        self,
        sending: Callable[..., Any],
        collected: str,
        add_second_event: Callable[..., None]
    ) -> None:
        add_second_event(category=None, roles=())

        response, asked = sending(collected)

        assert response.status_code == 409
        assert '1 event(s)' in response.json()['detail']
        assert asked == []

    def test_a_send_with_no_key_is_refused(
        self,
        started_client: TestClient,
        amplify_holds: Callable[..., list],
        collected: str
    ) -> None:
        amplify_holds()

        response = started_client.post(
            send_path(run_id=collected),
            json={'expectedShiftCount': 1}
        )

        assert response.status_code == 422
        assert response.headers['content-type'] == PROBLEM_MEDIA_TYPE

    def test_sending_needs_a_credential(
        self,
        anonymous_client: TestClient,
        run_id: str
    ) -> None:
        assert anonymous_client.post(
            send_path(run_id=run_id),
            json={'expectedShiftCount': 0},
            headers={IDEMPOTENCY_KEY_HEADER: SEND_ATTEMPT}
        ).status_code == 401


class TestAKeyThatIsAlreadyInUse:
    def test_the_first_answer_is_given_again(
        self,
        sending: Callable[..., Any],
        collected: str
    ) -> None:
        first, _asked = sending(collected)

        second, asked = sending(collected)

        assert second.status_code == 202
        assert second.json() == first.json()
        # The work happened once, however many times it was asked for.
        assert len(asked) == 1

    def test_a_key_carrying_another_request_is_refused(
        self,
        sending: Callable[..., Any],
        collected: str,
        add_second_event: Callable[..., None]
    ) -> None:
        # A key is a promise that the request is the one already made.
        sending(collected)
        add_second_event(date='2026-09-10')

        response, asked = sending(collected, expected=2)

        assert response.status_code == 422
        assert 'different' in response.json()['detail']
        assert len(asked) == 1

    def test_a_send_still_running_is_not_answered_from(
        self,
        started_client: TestClient,
        amplify_holds: Callable[..., list],
        idempotency: IdempotencyRepository,
        collected: str
    ) -> None:
        # A reservation with no answer yet is a request still in hand,
        # and answering it with anything would be inventing a result.
        amplify_holds()
        idempotency.reserve(
            operation=JOB_KIND_SEND,
            key=SEND_ATTEMPT,
            run_id=collected,
            fingerprint='expected_shift_count=1',
            principal_id='someone-else'
        )

        response = started_client.post(
            send_path(run_id=collected),
            json={'expectedShiftCount': 1},
            headers={IDEMPOTENCY_KEY_HEADER: SEND_ATTEMPT}
        )

        assert response.status_code == 409
        assert 'not answered yet' in response.json()['detail']

    def test_the_answer_is_recorded_against_the_key(
        self,
        sending: Callable[..., Any],
        idempotency: IdempotencyRepository,
        collected: str
    ) -> None:
        response, _asked = sending(collected)

        recorded = idempotency.get(operation=JOB_KIND_SEND, key=SEND_ATTEMPT)

        assert recorded.status_code == 202
        assert recorded.response == response.json()

    def test_a_key_that_claimed_another_run_is_refused(
        self,
        sending: Callable[..., Any],
        another_sendable_run: str,
        collected: str
    ) -> None:
        # A key claims one operation, not one run.  Answered from the
        # first reservation, a second run would be reported as sending
        # when nothing was sent for it at all.  Both runs ask for the
        # same number of shifts, so the run is the only thing telling
        # the two requests apart.
        sending(collected)

        response, asked = sending(another_sendable_run, expected=1)

        assert response.status_code == 422
        assert collected in response.json()['detail']
        assert len(asked) == 1


class TestWhatAJobReports:
    def test_a_queued_job_is_answered_before_it_finishes(
        self,
        started_client: TestClient,
        amplify_holds: Callable[..., list],
        collected: str,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The caller is given an identifier rather than made to wait,
        # which is the whole reason a send is a job.
        amplify_holds()
        seen: Dict[str, Any] = {}

        def record(**parameters: Any) -> None:
            """ Stand in for the send, reading the job as it runs. """
            seen['status'] = JobRepository(
                connection=parameters['connection']
            ).get(job_id=seen['id']).status

        monkeypatch.setattr('star_pass_api._sending.send', record)

        response = started_client.post(
            send_path(run_id=collected),
            json={'expectedShiftCount': 1},
            headers={IDEMPOTENCY_KEY_HEADER: SEND_ATTEMPT}
        )
        seen['id'] = response.json()['id']

        assert response.status_code == 202
        assert response.json()['status'] in ('queued', JOB_STATUS_RUNNING)
