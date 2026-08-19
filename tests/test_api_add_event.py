#!/usr/bin/env python3
""" Asking the service to pull an event the search missed into a run.

    What pulling one in does is pinned in 'test_adding.py'.  These
    tests ask a narrower question: that the endpoint answers with the
    revision the event joined, refuses what may not be pulled in
    rather than raising, and that the list it was pulled from stops
    offering it.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

# Imports - Third-Party
import pytest
from fastapi.testclient import TestClient

# Imports - Local
from star_pass._records import (
    UncollectedEvent,
    UNCOLLECTED_ALL_DAY,
    UNCOLLECTED_EXCLUDED,
    UNCOLLECTED_SEARCH
)
from star_pass._repository import (
    RevisionRepository,
    UncollectedRepository
)
from star_pass_api import _defaults
from star_pass_api._problems import PROBLEM_MEDIA_TYPE

# Constants
RUNS_PATH = f'{_defaults.API_VERSION_PREFIX}/runs'

# The event nobody searched for, and a title the "practices" calendar's
# model matches, so the event that arrives is one with roles on it.
MISSED_ID = 'gcal-missed'
MISSED_TITLE = 'Adult Scrimmages'

# A title the stand-in model matches by keyword, for the test that
# replaces the model to say what an event's shift times should be.
MATCHED_TITLE = 'Wheels of Justice vs Rose City'


def events_path(run_id: str) -> str:
    """ Return the address a run's events are added to. """
    return f'{RUNS_PATH}/{run_id}/events'


def uncollected_path(run_id: str) -> str:
    """ Return the address of what one run's window left out. """
    return f'{RUNS_PATH}/{run_id}/uncollected'


@pytest.fixture(name='missed')
def fixture_missed(
    uncollected: UncollectedRepository
) -> Callable[..., str]:
    """ Return a way to record one thing a run's window left out. """

    def record(run_id: str, **overrides: Any) -> str:
        """ Store the row, replacing any overridden field. """
        fields: dict = {
            'id': MISSED_ID,
            'reason': UNCOLLECTED_SEARCH,
            'title': MISSED_TITLE,
            'date': '2026-09-11',
            'calendar_start': '18:00',
            'calendar_end': '20:00'
        }
        fields.update(overrides)
        uncollected.replace(
            run_id=run_id,
            uncollected=[UncollectedEvent(**fields)]
        )

        return fields['id']

    return record


@pytest.fixture(name='add')
def fixture_add(
    authenticated_client: TestClient,
    amplify_holds: Callable[..., list],
    service_database: Path
) -> Callable[..., Any]:
    """ Return a way to ask for one event to be pulled in.

        Amplify answers every opportunity read, because a pulled-in
        event may name one the run has never read.
    """
    del service_database
    amplify_holds()

    def send(run_id: str, uncollected_id: str = MISSED_ID) -> Any:
        """ Ask, and return what the service answered. """
        return authenticated_client.post(
            events_path(run_id=run_id),
            json={'uncollectedId': uncollected_id}
        )

    return send


@pytest.fixture(name='groups')
def fixture_groups(
    authenticated_client: TestClient
) -> Callable[[str], List[Dict[str, Any]]]:
    """ Return a way to read what a run's window left out. """

    def read(run_id: str) -> List[Dict[str, Any]]:
        """ Read the groups, failing the test if they were refused. """
        response = authenticated_client.get(uncollected_path(run_id=run_id))

        assert response.status_code == 200

        return response.json()

    return read


class TestWhatPullingOneInAnswers:
    def test_the_event_is_reported_as_created(
        self,
        add: Callable[..., Any],
        collected: str,
        missed: Callable[..., str]
    ) -> None:
        missed(run_id=collected)

        answer = add(run_id=collected)

        assert answer.status_code == 201

    def test_the_revision_comes_back_holding_it(
        self,
        add: Callable[..., Any],
        collected: str,
        missed: Callable[..., str]
    ) -> None:
        # The whole revision, because the screen that asked is redrawn
        # from it and the figures beside a row are answers about the
        # revision as a whole.
        missed(run_id=collected)

        events = add(run_id=collected).json()['events']

        assert [event['id'] for event in events] == ['event-1', MISSED_ID]

    def test_the_event_says_a_person_put_it_there(
        self,
        add: Callable[..., Any],
        collected: str,
        missed: Callable[..., str]
    ) -> None:
        missed(run_id=collected)

        added = add(run_id=collected).json()['events'][-1]

        assert added['addedByHand'] is True
        assert added['title'] == MISSED_TITLE

    def test_the_revision_says_which_rows_have_been_edited(
        self,
        add: Callable[..., Any],
        missed: Callable[..., str],
        moved_event: str
    ) -> None:
        # Read under this run's own calendar, which is the only thing
        # that says what its shift times should have been.  The event
        # that has just arrived was built by those same rules a moment
        # ago, so there is nothing to undo on it.
        missed(run_id=moved_event, title=MATCHED_TITLE)

        returned = add(run_id=moved_event).json()['events']

        assert [event['edited'] for event in returned] == [True, False]

    def test_the_change_log_entry_it_wrote_comes_back(
        self,
        add: Callable[..., Any],
        collected: str,
        missed: Callable[..., str]
    ) -> None:
        missed(run_id=collected)

        log = add(run_id=collected).json()['log']

        assert len(log) == 1
        assert MISSED_TITLE in log[0]['entry']

    def test_the_entry_records_who_pulled_it_in(
        self,
        add: Callable[..., Any],
        collected: str,
        missed: Callable[..., str]
    ) -> None:
        # Every write records the principal, even while there is one
        # of them and it is a static token (D13).
        missed(run_id=collected)

        log = add(run_id=collected).json()['log']

        assert log[0]['principalId'] == _defaults.API_PRINCIPAL_ID

    def test_the_event_joins_the_revision_being_edited_now(
        self,
        add: Callable[..., Any],
        collected: str,
        missed: Callable[..., str],
        revisions: RevisionRepository
    ) -> None:
        # Not the first revision. A run that has been revised is
        # working in the latest one, and an answer built from an
        # earlier one would show the reviewer a screen without the row
        # they just added.
        revisions.create(run_id=collected, label='After an edit')
        missed(run_id=collected)

        answer = add(run_id=collected).json()

        assert answer['log'][0]['revision'] == 2
        assert [event['id'] for event in answer['events']] == [
            'event-1',
            MISSED_ID
        ]


class TestTheListItWasPulledFrom:
    @pytest.fixture(name='around')
    def fixture_around(
        self,
        add: Callable[..., Any],
        collected: str,
        groups: Callable[[str], List[Dict[str, Any]]],
        missed: Callable[..., str]
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """ Return the list as it stood before the pull-in and after. """
        missed(run_id=collected)
        before = groups(collected)[0]['events']
        add(run_id=collected)

        return before, groups(collected)[0]['events']

    def test_the_event_stops_being_addable(
        self,
        around: Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]
    ) -> None:
        # Which is what takes it off the Not collected tab without
        # anything being deleted. Read on both sides of the pull-in,
        # because an answer that never offered it would pass a test
        # that only looked afterwards.
        before, after = around

        assert [before[0]['addable'], after[0]['addable']] == [True, False]

    def test_its_entry_is_still_published(
        self,
        around: Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]
    ) -> None:
        # The entry is what reverting to the first revision gives
        # back, so pulling one in does not delete it.
        _, after = around

        assert [event['id'] for event in after] == [MISSED_ID]


class TestWhatIsRefused:
    def test_an_event_that_cannot_become_a_shift_is_refused(
        self,
        add: Callable[..., Any],
        collected: str,
        missed: Callable[..., str]
    ) -> None:
        # Refused by the endpoint rather than by a disabled button.
        missed(run_id=collected, reason=UNCOLLECTED_EXCLUDED)

        answer = add(run_id=collected)

        assert answer.status_code == 422
        assert answer.headers['content-type'] == PROBLEM_MEDIA_TYPE
        assert UNCOLLECTED_EXCLUDED in answer.json()['detail']

    def test_an_all_day_event_is_refused_by_its_own_reason(
        self,
        add: Callable[..., Any],
        collected: str,
        missed: Callable[..., str]
    ) -> None:
        missed(run_id=collected, reason=UNCOLLECTED_ALL_DAY)

        assert UNCOLLECTED_ALL_DAY in add(
            run_id=collected
        ).json()['detail']

    def test_pulling_the_same_event_in_twice_is_refused(
        self,
        add: Callable[..., Any],
        collected: str,
        missed: Callable[..., str]
    ) -> None:
        # What makes a second arrival of one request a refusal rather
        # than a second row, and why no idempotency key is needed.
        missed(run_id=collected)
        add(run_id=collected)

        answer = add(run_id=collected)

        assert answer.status_code == 422
        assert 'already holds' in answer.json()['detail']

    def test_an_identifier_the_run_left_nothing_out_under_is_refused(
        self,
        add: Callable[..., Any],
        collected: str,
        missed: Callable[..., str]
    ) -> None:
        missed(run_id=collected)

        answer = add(run_id=collected, uncollected_id='gcal-nothing')

        assert answer.status_code == 422
        assert 'gcal-nothing' in answer.json()['detail']

    def test_an_unknown_run_is_not_found(
        self,
        add: Callable[..., Any]
    ) -> None:
        answer = add(run_id='no-such-run')

        assert answer.status_code == 404
        assert answer.headers['content-type'] == PROBLEM_MEDIA_TYPE
        assert 'no-such-run' in answer.json()['detail']

    def test_a_request_naming_nothing_is_refused(
        self,
        add: Callable[..., Any],
        collected: str
    ) -> None:
        answer = add(run_id=collected, uncollected_id='')

        assert answer.status_code == 422


class TestWhoMayPullOneIn:
    def test_a_caller_without_a_credential_is_refused(
        self,
        anonymous_client: TestClient,
        collected: str
    ) -> None:
        response = anonymous_client.post(
            events_path(run_id=collected),
            json={'uncollectedId': MISSED_ID}
        )

        assert response.status_code == 401

    def test_the_endpoint_declares_the_scope_it_needs(
        self,
        client: TestClient
    ) -> None:
        published = client.get(
            _defaults.API_OPENAPI_PATH
        ).json()['paths'][f'{RUNS_PATH}/{{run_id}}/events']['post']

        assert published['security'] == [{'Bearer token': ['runs:write']}]

    def test_no_idempotency_key_is_asked_for(
        self,
        client: TestClient
    ) -> None:
        # The revision holding the event is the guard, and it is
        # stronger than a key: a second arrival finds the run holding
        # what it asked for and says so.
        published = client.get(
            _defaults.API_OPENAPI_PATH
        ).json()['paths'][f'{RUNS_PATH}/{{run_id}}/events']['post']

        assert [
            parameter['name'] for parameter in published['parameters']
        ] == ['run_id']
