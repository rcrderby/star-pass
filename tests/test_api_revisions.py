#!/usr/bin/env python3
""" Asking the service to seal the revision a run is working in.

    What sealing does is pinned in 'test_revising.py'.  These tests
    ask a narrower question: that the endpoint claims its key before
    it writes, answers a second arrival from what the first one
    recorded, and refuses a run with nothing to seal rather than
    opening a revision the collection would replace.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
from pathlib import Path
from typing import Any, Callable, Dict, List

# Imports - Third-Party
import pytest
from fastapi.testclient import TestClient

# Imports - Local
from star_pass._records import OPERATION_SEAL
from star_pass._repository import IdempotencyRepository, RunRepository
from star_pass_api import _defaults
from star_pass_api._problems import PROBLEM_MEDIA_TYPE
from star_pass_contract import IDEMPOTENCY_KEY_HEADER

# Constants
RUNS_PATH = f'{_defaults.API_VERSION_PREFIX}/runs'

# What one action is claimed under.  Named rather than called a key: a
# constant whose name reads as a credential is one gitleaks stops on.
SEAL_ATTEMPT = 'seal-attempt-one'
SECOND_ATTEMPT = 'seal-attempt-two'


def revisions_path(run_id: str) -> str:
    """ Return the address a run's revisions are sealed at. """
    return f'{RUNS_PATH}/{run_id}/revisions'


@pytest.fixture(name='seal')
def fixture_seal(
    authenticated_client: TestClient,
    service_database: Path
) -> Callable[..., Any]:
    """ Return a way to ask for one revision to be sealed. """
    del service_database

    def send(run_id: str, key: str = SEAL_ATTEMPT) -> Any:
        """ Ask, and return what the service answered. """
        return authenticated_client.post(
            revisions_path(run_id=run_id),
            headers={IDEMPOTENCY_KEY_HEADER: key}
        )

    return send


@pytest.fixture(name='listed')
def fixture_listed(
    authenticated_client: TestClient
) -> Callable[[str], List[Dict[str, Any]]]:
    """ Return a way to read a run's revisions. """

    def read(run_id: str) -> List[Dict[str, Any]]:
        """ Read them, failing the test if they were refused. """
        response = authenticated_client.get(revisions_path(run_id=run_id))

        assert response.status_code == 200

        return response.json()

    return read


class TestWhatSealingAnswers:
    def test_the_revision_it_opened_is_reported_as_created(
        self,
        collected: str,
        seal: Callable[..., Any]
    ) -> None:
        answer = seal(run_id=collected)

        assert answer.status_code == 201
        assert answer.json()['number'] == 2

    def test_the_revision_it_opened_is_the_current_one(
        self,
        collected: str,
        seal: Callable[..., Any]
    ) -> None:
        # Which is what says where the work carries on.
        assert seal(run_id=collected).json()['current'] is True

    def test_the_revision_it_opened_says_what_it_continues_from(
        self,
        collected: str,
        seal: Callable[..., Any]
    ) -> None:
        # A label describing what happened, because what is in it is a
        # copy of the revision it names.
        assert '1' in seal(run_id=collected).json()['label']

    def test_the_new_revision_has_had_nothing_done_to_it(
        self,
        collected: str,
        seal: Callable[..., Any]
    ) -> None:
        # The change count is what was done while a revision was
        # current, so one just opened starts at nothing.
        assert seal(run_id=collected).json()['changes'] == 0


class TestWhatSealingLeavesBehind:
    def test_the_revision_that_was_current_is_still_readable(
        self,
        collected: str,
        listed: Callable[[str], List[Dict[str, Any]]],
        seal: Callable[..., Any]
    ) -> None:
        # Nothing is deleted, which is what reverting to it later
        # reads.
        seal(run_id=collected)

        assert [
            revision['number'] for revision in listed(collected)
        ] == [1, 2]

    def test_the_new_revision_holds_a_copy_of_what_was_sealed(
        self,
        authenticated_client: TestClient,
        collected: str,
        seal: Callable[..., Any]
    ) -> None:
        # Sealing marks where the work has got to; it does not empty
        # the run out.
        seal(run_id=collected)

        run = authenticated_client.get(f'{RUNS_PATH}/{collected}').json()

        assert run['currentRevision'] == 2
        assert [event['id'] for event in run['events']] == ['event-1']

    def test_sealing_twice_opens_two_revisions(
        self,
        collected: str,
        listed: Callable[[str], List[Dict[str, Any]]],
        seal: Callable[..., Any]
    ) -> None:
        # Which is why the key is worth having: two seals are two
        # actions, and a retry of one is neither.
        seal(run_id=collected)
        seal(run_id=collected, key=SECOND_ATTEMPT)

        assert [
            revision['number'] for revision in listed(collected)
        ] == [1, 2, 3]


class TestTheKeyItIsClaimedUnder:
    def test_a_second_arrival_is_answered_from_the_first(
        self,
        collected: str,
        listed: Callable[[str], List[Dict[str, Any]]],
        seal: Callable[..., Any]
    ) -> None:
        # A retry after a lost answer is given the first answer rather
        # than opening a second revision.
        first = seal(run_id=collected)

        second = seal(run_id=collected)

        assert second.status_code == first.status_code
        assert second.json() == first.json()
        assert [
            revision['number'] for revision in listed(collected)
        ] == [1, 2]

    def test_the_key_is_recorded_against_the_operation(
        self,
        collected: str,
        idempotency: IdempotencyRepository,
        seal: Callable[..., Any]
    ) -> None:
        # A key is per operation, so the same value used on a seal and
        # an edit is two reservations rather than one replaying the
        # other's answer.
        seal(run_id=collected)

        reserved = idempotency.get(
            operation=OPERATION_SEAL,
            key=SEAL_ATTEMPT
        )

        assert reserved is not None
        # What the first request answered, recorded against the key
        # rather than worked out again by whatever replays it.
        assert reserved.status_code == 201

    def test_a_key_naming_another_run_is_refused(
        self,
        collected: str,
        other_run_id: str,
        runs: RunRepository,
        seal: Callable[..., Any]
    ) -> None:
        # Without this a run would be reported as sealed when the
        # revision was opened on a different one.
        del runs
        seal(run_id=collected)

        answer = seal(run_id=other_run_id)

        assert answer.status_code == 422
        assert answer.headers['content-type'] == PROBLEM_MEDIA_TYPE

    def test_a_request_without_a_key_is_refused(
        self,
        authenticated_client: TestClient,
        collected: str,
        service_database: Path
    ) -> None:
        del service_database

        response = authenticated_client.post(
            revisions_path(run_id=collected)
        )

        assert response.status_code == 422


class TestWhatIsRefused:
    def test_a_run_with_nothing_collected_is_refused(
        self,
        run_id: str,
        seal: Callable[..., Any]
    ) -> None:
        # The first revision belongs to the collection, which labels
        # it for what filled it; one opened here would be an empty
        # revision the collection then replaced.
        answer = seal(run_id=run_id)

        assert answer.status_code == 409
        assert 'collected nothing' in answer.json()['detail']

    def test_an_unknown_run_is_not_found(
        self,
        seal: Callable[..., Any]
    ) -> None:
        answer = seal(run_id='no-such-run')

        assert answer.status_code == 404
        assert 'no-such-run' in answer.json()['detail']

    def test_a_refused_run_is_left_with_no_revision(
        self,
        listed: Callable[[str], List[Dict[str, Any]]],
        run_id: str,
        seal: Callable[..., Any]
    ) -> None:
        seal(run_id=run_id)

        assert listed(run_id) == []


class TestWhoMaySeal:
    def test_a_caller_without_a_credential_is_refused(
        self,
        anonymous_client: TestClient,
        collected: str
    ) -> None:
        response = anonymous_client.post(
            revisions_path(run_id=collected),
            headers={IDEMPOTENCY_KEY_HEADER: SEAL_ATTEMPT}
        )

        assert response.status_code == 401

    def test_the_endpoint_declares_the_scope_it_needs(
        self,
        client: TestClient
    ) -> None:
        published = client.get(
            _defaults.API_OPENAPI_PATH
        ).json()['paths'][f'{RUNS_PATH}/{{run_id}}/revisions']['post']

        assert published['security'] == [{'Bearer token': ['runs:write']}]
