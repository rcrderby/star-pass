#!/usr/bin/env python3
""" Asking the service to seal a run's revision, or to go back to one.

    What each does is pinned in 'test_revising.py'.  These tests ask a
    narrower question: that each endpoint claims its key before it
    writes, answers a second arrival from what the first one recorded,
    and refuses what it cannot carry out rather than raising.

    The two differ in what a key remembers, and it shows here: a seal
    carries nothing, so any second arrival on its key is a replay,
    while a revert carries the revision asked for and a key sent back
    naming a different one is refused.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
from pathlib import Path
from typing import Any, Callable, Dict, List

# Imports - Third-Party
import pytest
from fastapi.testclient import TestClient

# Imports - Local
from star_pass._records import Event, OPERATION_REVERT, OPERATION_SEAL
from star_pass._repository import (
    EventRepository,
    IdempotencyRepository,
    RunRepository
)
from star_pass_api import _defaults
from star_pass_api._problems import PROBLEM_MEDIA_TYPE
from star_pass_contract import IDEMPOTENCY_KEY_HEADER

# Constants
RUNS_PATH = f'{_defaults.API_VERSION_PREFIX}/runs'

# What one action is claimed under.  Named rather than called a key: a
# constant whose name reads as a credential is one gitleaks stops on.
SEAL_ATTEMPT = 'seal-attempt-one'
SECOND_ATTEMPT = 'seal-attempt-two'
REVERT_ATTEMPT = 'revert-attempt-one'

# The one thing the 'not_collected' arrangement leaves out that may be
# pulled in, which is what makes it the one a revert can offer again.
MISSED_ID = 'gcal-11'


def revisions_path(run_id: str) -> str:
    """ Return the address a run's revisions are sealed at. """
    return f'{RUNS_PATH}/{run_id}/revisions'


def revert_path(run_id: str, number: int) -> str:
    """ Return the address a run is taken back from one revision. """
    return f'{RUNS_PATH}/{run_id}/revisions/{number}/revert'


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
        # What is in it is a copy of the revision it names, so which
        # one that was is the fact worth publishing about it.
        opened = seal(run_id=collected).json()

        assert opened['kind'] == 'continued'
        assert opened['sourceRevision'] == 1

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


@pytest.fixture(name='revert')
def fixture_revert(
    authenticated_client: TestClient,
    service_database: Path
) -> Callable[..., Any]:
    """ Return a way to ask for a run to be taken back. """
    del service_database

    def send(
        run_id: str,
        number: int = 1,
        key: str = REVERT_ATTEMPT
    ) -> Any:
        """ Ask, and return what the service answered. """
        return authenticated_client.post(
            revert_path(run_id=run_id, number=number),
            headers={IDEMPOTENCY_KEY_HEADER: key}
        )

    return send


@pytest.fixture(name='was_pulled_in')
def fixture_was_pulled_in(
    events: EventRepository,
    make_event: Callable[..., Event],
    not_collected: Callable[[str], Any]
) -> Callable[[str], None]:
    """ Return a way to arrange a run holding a hand-added event.

        The event carries the identifier of a row the collection left
        out for want of a search that returned it, which is the pair
        that makes the row offerable again: what takes it off the list
        is the revision holding it, and nothing else.
    """

    def arrange(run_id: str) -> None:
        """ Record what was left out and hold one of it by hand. """
        not_collected(run_id)
        events.add(
            run_id=run_id,
            revision=1,
            event=make_event(id=MISSED_ID, added_by_hand=True)
        )

    return arrange


@pytest.fixture(name='offered')
def fixture_offered(
    authenticated_client: TestClient,
    service_database: Path
) -> Callable[[str], Any]:
    """ Return a way to ask which left-out events may be pulled in. """
    del service_database

    def read(run_id: str) -> Any:
        """ Return the identifiers the run offers, failing on a refusal. """
        response = authenticated_client.get(
            f'{RUNS_PATH}/{run_id}/uncollected'
        )

        assert response.status_code == 200

        return [
            event['id']
            for group in response.json()
            for event in group['events']
            if event['addable']
        ]

    return read


class TestWhatRevertingAnswers:
    def test_the_run_comes_back_in_full(
        self,
        collected: str,
        revert: Callable[..., Any],
        seal: Callable[..., Any]
    ) -> None:
        # Everything on the screen that asked has changed, so the
        # answer is the run rather than the revision it opened.
        seal(run_id=collected)

        answer = revert(run_id=collected)

        assert answer.status_code == 200
        assert answer.json()['id'] == collected
        assert [event['id'] for event in answer.json()['events']] == [
            'event-1'
        ]

    def test_the_run_is_working_in_the_revision_it_opened(
        self,
        collected: str,
        revert: Callable[..., Any],
        seal: Callable[..., Any]
    ) -> None:
        seal(run_id=collected)

        assert revert(run_id=collected).json()['currentRevision'] == 3


class TestHowManyRevisionsARevertAdds:
    def test_one(
        self,
        collected: str,
        listed: Callable[[str], List[Dict[str, Any]]],
        revert: Callable[..., Any],
        seal: Callable[..., Any]
    ) -> None:
        # Not two. Nothing a revert does is destructive, so there is
        # nothing to seal first, and sealing first would add a
        # revision holding an identical copy of the one before it.
        seal(run_id=collected)

        revert(run_id=collected)

        assert [
            revision['number'] for revision in listed(collected)
        ] == [1, 2, 3]

    def test_the_revision_it_left_is_still_readable(
        self,
        collected: str,
        listed: Callable[[str], List[Dict[str, Any]]],
        revert: Callable[..., Any]
    ) -> None:
        # Which is what lets a revert be reverted.
        revert(run_id=collected)

        assert [
            (revision['kind'], revision['sourceRevision'])
            for revision in listed(collected)
        ] == [('collected', None), ('reverted', 1)]


class TestWhatGoingBackToTheCollectionOffersAgain:
    def test_an_event_somebody_pulled_in_is_offered_once_more(
        self,
        collected: str,
        offered: Callable[[str], Any],
        revert: Callable[..., Any],
        was_pulled_in: Callable[[str], None]
    ) -> None:
        was_pulled_in(collected)

        revert(run_id=collected)

        assert offered(collected) == [MISSED_ID]

    def test_it_was_not_offered_while_the_run_held_it(
        self,
        collected: str,
        offered: Callable[[str], Any],
        was_pulled_in: Callable[[str], None]
    ) -> None:
        # Without this the test above would pass against a list that
        # offers everything it has a row for.
        was_pulled_in(collected)

        assert offered(collected) == []

    def test_the_run_no_longer_holds_it(
        self,
        collected: str,
        revert: Callable[..., Any],
        was_pulled_in: Callable[[str], None]
    ) -> None:
        was_pulled_in(collected)

        answer = revert(run_id=collected)

        assert [event['id'] for event in answer.json()['events']] == [
            'event-1'
        ]


class TestTheKeyARevertIsClaimedUnder:
    def test_a_second_arrival_is_answered_from_the_first(
        self,
        collected: str,
        listed: Callable[[str], List[Dict[str, Any]]],
        revert: Callable[..., Any]
    ) -> None:
        first = revert(run_id=collected)

        second = revert(run_id=collected)

        assert second.status_code == first.status_code
        assert second.json() == first.json()
        assert [
            revision['number'] for revision in listed(collected)
        ] == [1, 2]

    def test_the_same_key_naming_another_revision_is_refused(
        self,
        collected: str,
        revert: Callable[..., Any],
        seal: Callable[..., Any]
    ) -> None:
        # Two reverts are two actions and the number is the whole of
        # what tells them apart, so a key sent back naming a different
        # one is a different request rather than a retry.
        seal(run_id=collected)
        revert(run_id=collected, number=1)

        answer = revert(run_id=collected, number=2)

        assert answer.status_code == 422
        assert answer.headers['content-type'] == PROBLEM_MEDIA_TYPE

    def test_the_key_is_recorded_against_reverting(
        self,
        collected: str,
        idempotency: IdempotencyRepository,
        revert: Callable[..., Any]
    ) -> None:
        # A key is per operation, so the same value used on a seal and
        # a revert is two reservations rather than one replaying the
        # other's answer.
        revert(run_id=collected)

        reserved = idempotency.get(
            operation=OPERATION_REVERT,
            key=REVERT_ATTEMPT
        )

        assert reserved is not None
        assert reserved.status_code == 200

    def test_a_request_without_a_key_is_refused(
        self,
        authenticated_client: TestClient,
        collected: str,
        service_database: Path
    ) -> None:
        del service_database

        response = authenticated_client.post(
            revert_path(run_id=collected, number=1)
        )

        assert response.status_code == 422


class TestWhatCannotBeRevertedTo:
    def test_a_revision_the_run_has_never_had_is_refused(
        self,
        collected: str,
        revert: Callable[..., Any]
    ) -> None:
        answer = revert(run_id=collected, number=9)

        assert answer.status_code == 409
        assert 'no revision 9' in answer.json()['detail']

    def test_a_revision_number_below_the_first_is_malformed(
        self,
        collected: str,
        revert: Callable[..., Any]
    ) -> None:
        # Revisions are numbered from one, so a zero is a request that
        # could never name anything rather than one naming something
        # absent.
        assert revert(run_id=collected, number=0).status_code == 422

    def test_an_unknown_run_is_not_found(
        self,
        revert: Callable[..., Any]
    ) -> None:
        answer = revert(run_id='no-such-run')

        assert answer.status_code == 404
        assert 'no-such-run' in answer.json()['detail']

    def test_a_refused_run_gains_no_revision(
        self,
        collected: str,
        listed: Callable[[str], List[Dict[str, Any]]],
        revert: Callable[..., Any]
    ) -> None:
        revert(run_id=collected, number=9)

        assert [
            revision['number'] for revision in listed(collected)
        ] == [1]


class TestWhoMayRevert:
    def test_a_caller_without_a_credential_is_refused(
        self,
        anonymous_client: TestClient,
        collected: str
    ) -> None:
        response = anonymous_client.post(
            revert_path(run_id=collected, number=1),
            headers={IDEMPOTENCY_KEY_HEADER: REVERT_ATTEMPT}
        )

        assert response.status_code == 401

    def test_the_endpoint_declares_the_scope_it_needs(
        self,
        client: TestClient
    ) -> None:
        published = client.get(
            _defaults.API_OPENAPI_PATH
        ).json()['paths'][
            f'{RUNS_PATH}/{{run_id}}/revisions/{{number}}/revert'
        ]['post']

        assert published['security'] == [{'Bearer token': ['runs:write']}]
