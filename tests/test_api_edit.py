#!/usr/bin/env python3
""" Asking the service to edit a run's current revision.

    What an edit does is pinned in 'test_editing.py'.  These tests ask
    a narrower question: that the endpoint claims the idempotency key
    before it writes, answers a request arriving on a used key from
    what the first one recorded, refuses one carrying different
    operations, and turns an operation the core will not apply into a
    refusal rather than a traceback.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
from pathlib import Path
from typing import Any, Callable, Dict, List

# Imports - Third-Party
import pytest
from fastapi.testclient import TestClient

# Imports - Local
from conftest import a_category, a_need
from star_pass._records import OPERATION_EDIT
from star_pass._repository import ChangeLogRepository, IdempotencyRepository
from star_pass_api import _defaults
from star_pass_contract import IDEMPOTENCY_KEY_HEADER

# Constants
RUNS_PATH = f'{_defaults.API_VERSION_PREFIX}/runs'
PROBLEM_MEDIA_TYPE = 'application/problem+json'

# What one action is claimed under.  Named rather than called a key: a
# constant whose name reads as a credential is one gitleaks stops on.
EDIT_ATTEMPT = 'edit-attempt-one'
SECOND_ATTEMPT = 'edit-attempt-two'


def events_path(run_id: str) -> str:
    """ Return the address a run's events are edited at. """
    return f'{RUNS_PATH}/{run_id}/events'


def a_nudge(minutes: int = -15) -> Dict[str, Any]:
    """ Return one operation moving the fixture's event. """
    return {
        'op': 'nudge',
        'eventIds': ['event-1'],
        'minutes': minutes
    }


def a_category_change(
    category: str = 'junior_scrimmage'
) -> Dict[str, Any]:
    """ Return one operation putting the fixture's event elsewhere. """
    return {
        'op': 'set_category',
        'eventIds': ['event-1'],
        'category': category
    }


@pytest.fixture(name='two_categories')
def fixture_two_categories(shift_model: Callable[..., None]) -> None:
    """ Install a model holding the collected category and another.

        A category change needs somewhere to change to, and the model
        the other tests arrange defines only the one the fixture event
        was collected under.
    """
    shift_model(
        categories={
            'scrimmage': a_category(
                need_ids=[a_need(identifier='905196', slots=4)]
            ),
            'junior_scrimmage': a_category(
                need_ids=[
                    a_need(
                        identifier='905197',
                        slots=6,
                        offset_start=0,
                        offset_end=0,
                        max_length=None
                    )
                ]
            )
        },
        calendars=('practices',)
    )

    return None


@pytest.fixture(name='edit')
def fixture_edit(
    authenticated_client: TestClient,
    service_database: Path
) -> Callable[..., Any]:
    """ Return a way to send one edit. """
    del service_database

    def send(
        run_id: str,
        operations: List[Dict[str, Any]],
        key: str = EDIT_ATTEMPT
    ) -> Any:
        return authenticated_client.patch(
            events_path(run_id=run_id),
            json={'operations': operations},
            headers={IDEMPOTENCY_KEY_HEADER: key}
        )

    return send


class TestWhatAnEditAnswers:
    def test_the_revision_comes_back_as_it_now_is(self, edit, collected):
        answer = edit(run_id=collected, operations=[a_nudge()])

        assert answer.status_code == 200
        assert answer.json()['events'][0]['shiftStart'] == '19:00'

    def test_the_entry_records_who_made_the_edit(self, edit, collected):
        # Every write records the principal, even while there is one
        # of them and it is a static token (D13).
        answer = edit(run_id=collected, operations=[a_nudge()])

        assert answer.json()['log'][0]['principalId'] == (
            _defaults.API_PRINCIPAL_ID
        )

    def test_every_event_comes_back_not_only_the_changed_ones(
        self, edit, collected, events, make_event
    ):
        # A reviewer's screen is redrawn from this, and the figures
        # beside a row are answers about the revision as a whole.
        events.add(
            run_id=collected,
            revision=1,
            event=make_event(id='event-2', title='Juniors Scrimmage')
        )

        answer = edit(run_id=collected, operations=[a_nudge()])

        assert len(answer.json()['events']) == 2

    def test_a_moved_event_comes_back_edited(
        self, edit, collected, matching_model
    ):
        # The screen is redrawn from this answer, so the undo it
        # offers on a row follows from what the edit produced rather
        # than from a reading of the run afterwards.
        del matching_model

        answer = edit(run_id=collected, operations=[a_nudge()])

        assert answer.json()['events'][0]['edited'] is True

    def test_an_undone_event_comes_back_not_edited(
        self, edit, collected, matching_model
    ):
        del matching_model
        edit(run_id=collected, operations=[a_nudge()])

        answer = edit(
            run_id=collected,
            operations=[{'op': 'undo', 'eventIds': ['event-1']}],
            key=SECOND_ATTEMPT
        )

        assert answer.json()['events'][0]['edited'] is False

    def test_a_changed_category_comes_back_edited(
        self, edit, collected, two_categories
    ):
        # The most common edit on the review screen, and the one the
        # screen could not offer an undo on while an event held only
        # the category it is under now.
        del two_categories

        answer = edit(
            run_id=collected,
            operations=[a_category_change()]
        )

        assert answer.json()['events'][0]['category'] == 'junior_scrimmage'
        assert answer.json()['events'][0]['edited'] is True

    def test_an_undone_category_comes_back_as_collected(
        self, edit, collected, two_categories
    ):
        del two_categories
        edit(run_id=collected, operations=[a_category_change()])

        answer = edit(
            run_id=collected,
            operations=[{'op': 'undo', 'eventIds': ['event-1']}],
            key=SECOND_ATTEMPT
        )

        assert answer.json()['events'][0]['category'] == 'scrimmage'
        assert answer.json()['events'][0]['edited'] is False

    def test_the_log_carries_one_entry_per_operation(
        self, edit, collected
    ):
        answer = edit(
            run_id=collected,
            operations=[a_nudge(), a_nudge(minutes=15)]
        )

        log = answer.json()['log']
        assert len(log) == 2
        assert log[0]['entry'] == (
            'Moved "Adult Scrimmages" 15 minutes earlier.'
        )

    def test_the_entries_reach_the_run_s_change_log(
        self, edit, collected, connection
    ):
        edit(run_id=collected, operations=[a_nudge()])

        stored = ChangeLogRepository(connection=connection).list_all(
            run_id=collected
        )

        assert len(stored) == 1

    def test_the_principal_is_recorded(
        self, edit, collected, connection
    ):
        # D13: every write records who asked, while there is still only
        # one principal, so the column is populated before it matters.
        edit(run_id=collected, operations=[a_nudge()])

        stored = ChangeLogRepository(connection=connection).list_all(
            run_id=collected
        )

        assert stored[0].principal_id


class TestTheIdempotencyKey:
    def test_the_same_key_and_request_is_answered_from_the_first(
        self, edit, collected
    ):
        first = edit(run_id=collected, operations=[a_nudge()])
        second = edit(run_id=collected, operations=[a_nudge()])

        assert second.status_code == 200
        assert second.json() == first.json()

    def test_a_replay_does_not_move_the_shift_again(
        self, edit, collected
    ):
        # The point of the key: a nudge applied twice moves a shift
        # twice, so a retry after a lost answer must not be carried out.
        edit(run_id=collected, operations=[a_nudge()])
        edit(run_id=collected, operations=[a_nudge()])

        answer = edit(
            run_id=collected,
            operations=[a_nudge(minutes=0)],
            key=SECOND_ATTEMPT
        )

        assert answer.json()['events'][0]['shiftStart'] == '19:00'

    def test_a_key_carrying_different_operations_is_refused(
        self, edit, collected
    ):
        edit(run_id=collected, operations=[a_nudge()])

        answer = edit(run_id=collected, operations=[a_nudge(minutes=30)])

        assert answer.status_code == 422
        assert answer.headers['content-type'].startswith(
            PROBLEM_MEDIA_TYPE
        )

    def test_a_new_key_edits_again(self, edit, collected):
        edit(run_id=collected, operations=[a_nudge()])

        answer = edit(
            run_id=collected,
            operations=[a_nudge()],
            key=SECOND_ATTEMPT
        )

        assert answer.json()['events'][0]['shiftStart'] == '18:45'

    def test_the_key_is_recorded_against_the_edit_operation(
        self, edit, collected, connection
    ):
        # Not against a job kind: an edit starts no job, which is why
        # the vocabulary a key is checked against is wider than
        # 'JOB_KINDS'.
        edit(run_id=collected, operations=[a_nudge()])

        record = IdempotencyRepository(connection=connection).get(
            operation=OPERATION_EDIT,
            key=EDIT_ATTEMPT
        )

        assert record is not None
        assert record.status_code == 200

    def test_a_request_with_no_key_is_refused(
        self, authenticated_client, collected, service_database
    ):
        del service_database
        answer = authenticated_client.patch(
            events_path(run_id=collected),
            json={'operations': [a_nudge()]}
        )

        assert answer.status_code == 422


class TestWhatIsRefused:
    def test_a_run_that_does_not_exist_is_not_found(self, edit):
        answer = edit(run_id='no-such-run', operations=[a_nudge()])

        assert answer.status_code == 404

    def test_an_operation_the_core_will_not_apply_is_a_conflict(
        self, edit, collected
    ):
        answer = edit(
            run_id=collected,
            operations=[a_nudge(minutes=1200)]
        )

        assert answer.status_code == 409
        assert 'leave its day' in answer.json()['detail']

    def test_a_refused_call_writes_nothing(
        self, edit, collected, connection
    ):
        edit(run_id=collected, operations=[a_nudge(minutes=1200)])

        stored = ChangeLogRepository(connection=connection).list_all(
            run_id=collected
        )

        assert stored == []

    def test_an_unknown_operation_is_a_conflict(self, edit, collected):
        answer = edit(
            run_id=collected,
            operations=[{'op': 'set_colour', 'eventIds': ['event-1']}]
        )

        assert answer.status_code == 409

    def test_an_empty_operation_list_is_refused_by_the_shape(
        self, edit, collected
    ):
        answer = edit(run_id=collected, operations=[])

        assert answer.status_code == 422

    def test_an_operation_naming_no_event_is_refused_by_the_shape(
        self, edit, collected
    ):
        answer = edit(
            run_id=collected,
            operations=[{'op': 'nudge', 'eventIds': [], 'minutes': -15}]
        )

        assert answer.status_code == 422
