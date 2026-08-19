#!/usr/bin/env python3
""" Asking the service what sending a run would create.

    What a preview holds is pinned in 'test_preview.py'.  These tests
    ask the narrower question this endpoint raises: that it reads the
    current revision, that its rows are grouped by Amplify
    opportunity, that a shift Amplify already holds is reported as
    skipped rather than counted, and that a caller with no credential
    is refused.

    Its own module rather than a class in 'test_api_runs.py', which
    the thousand-line cap the linter holds a module to had run out of
    room in.  The preview is the one to move: it is a different
    endpoint answering a different shape, and the only fixture it
    shares with the rest is the run it reads.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring
# pylint: disable=too-many-arguments,too-many-positional-arguments

# Imports - Python Standard Library
from typing import Any, Callable, Dict

# Imports - Third-Party
import pytest
from fastapi.testclient import TestClient

# Imports - Local
from star_pass._preview import (
    BLOCKER_ENDS_BEFORE_START,
    BLOCKER_NO_OPPORTUNITY,
    BLOCKER_NO_SLOTS
)
from star_pass._records import Event, EventRole
from star_pass._repository import EventRepository
from star_pass_api import _defaults
from star_pass_api._problems import PROBLEM_MEDIA_TYPE

# Constants
RUNS_PATH = f'{_defaults.API_VERSION_PREFIX}/runs'


def preview_path(run_id: str) -> str:
    """ Return the address of one run's preview. """
    return f'{RUNS_PATH}/{run_id}/preview'


@pytest.fixture(name='read_preview')
def fixture_read_preview(
    running_client: TestClient,
    amplify_holds: Callable[..., None]
) -> Callable[[str], Dict[str, Any]]:
    """ Return a way to read one run's preview.

        Amplify answers that its opportunities hold nothing unless the
        test says otherwise.  A preview reads every one of them live,
        so a test that arranged nothing would be making a request.
    """
    amplify_holds()

    def read(run_id: str) -> Dict[str, Any]:
        """ Read the preview, failing the test if it was not found. """
        response = running_client.get(preview_path(run_id=run_id))

        assert response.status_code == 200

        return response.json()

    return read


class TestPreviewingASend:
    def test_a_preview_reports_what_would_be_created(
        self,
        read_preview: Callable[[str], Dict[str, Any]],
        collected: str
    ) -> None:
        assert read_preview(collected)['totals'] == {
            'willCreate': 1,
            'alreadyInAmplify': 0,
            'repeatedRows': 0,
            'blockingEvents': 0
        }

    def test_a_preview_groups_its_rows_by_opportunity(
        self,
        read_preview: Callable[[str], Dict[str, Any]],
        labelled: str,
        add_second_event: Callable[..., None]
    ) -> None:
        # Several categories share one Amplify listing, so grouping by
        # category would show that listing twice under two names.
        add_second_event(date='2026-09-10', category='junior_game')

        rows = read_preview(labelled)['rows']

        assert [
            (row['needId'], row['title'], row['willCreate'])
            for row in rows
        ] == [
            ('905196', 'Adult Scrimmages: Skating Officials', 2)
        ]

    def test_a_row_names_the_days_its_shifts_fall_on(
        self,
        read_preview: Callable[[str], Dict[str, Any]],
        collected: str,
        add_second_event: Callable[..., None]
    ) -> None:
        add_second_event(date='2026-09-10')

        row = read_preview(collected)['rows'][0]

        assert row['firstDate'] == '2026-09-03'
        assert row['lastDate'] == '2026-09-10'

    def test_two_events_sending_the_same_row_count_once(
        self,
        read_preview: Callable[[str], Dict[str, Any]],
        collected: str,
        add_second_event: Callable[..., None]
    ) -> None:
        # Counted by identity, never by how many events there are.
        add_second_event()

        assert read_preview(collected)['totals'] == {
            'willCreate': 1,
            'alreadyInAmplify': 0,
            'repeatedRows': 1,
            'blockingEvents': 0
        }

    def test_an_event_that_cannot_be_sent_is_named(
        self,
        read_preview: Callable[[str], Dict[str, Any]],
        collected: str,
        add_second_event: Callable[..., None]
    ) -> None:
        add_second_event(category=None, roles=())

        document = read_preview(collected)

        assert document['blockers'] == [
            {'eventId': 'event-2', 'reason': BLOCKER_NO_OPPORTUNITY}
        ]
        assert document['totals']['blockingEvents'] == 1

    def test_an_event_with_two_things_wrong_is_named_twice(
        self,
        read_preview: Callable[[str], Dict[str, Any]],
        collected: str,
        add_second_event: Callable[..., None]
    ) -> None:
        # Fixing one should not reveal another.
        add_second_event(
            shift_start='21:30',
            shift_end='19:15',
            roles=(EventRole(need_id='905196', slots=0),)
        )

        reasons = [
            item['reason']
            for item in read_preview(collected)['blockers']
        ]

        assert reasons == [
            BLOCKER_ENDS_BEFORE_START,
            BLOCKER_NO_SLOTS
        ]

    def test_a_run_with_no_events_would_create_nothing(
        self,
        read_preview: Callable[[str], Dict[str, Any]],
        run_id: str
    ) -> None:
        document = read_preview(run_id)

        assert document['totals']['willCreate'] == 0
        assert document['rows'] == []
        assert document['blockers'] == []

    def test_a_preview_reads_the_current_revision(
        self,
        read_preview: Callable[[str], Dict[str, Any]],
        events: EventRepository,
        edited: str,
        make_event: Callable[..., Event]
    ) -> None:
        # Revision 2 moved the event and holds one more; revision 1 is
        # history and is not what a send would work from.
        events.add(
            run_id=edited,
            revision=2,
            event=make_event(id='event-2', date='2026-09-10')
        )

        assert read_preview(edited)['totals']['willCreate'] == 2

    def test_a_shift_amplify_already_has_is_skipped(
        self,
        read_preview: Callable[[str], Dict[str, Any]],
        amplify_holds: Callable[..., None],
        make_amplify_shift: Callable[..., dict],
        collected: str
    ) -> None:
        # Read from the opportunity itself, not from any record of what
        # this run sent: a shift somebody created by hand is in neither.
        amplify_holds({'905196': [make_amplify_shift()]})

        document = read_preview(collected)

        assert document['totals']['willCreate'] == 0
        assert document['totals']['alreadyInAmplify'] == 1
        assert document['skipped'] == [
            {
                'needId': '905196',
                'date': '2026-09-03',
                'shiftStart': '19:15',
                'shiftEnd': '21:30'
            }
        ]

    def test_an_opportunity_holding_the_shift_says_so_in_its_row(
        self,
        read_preview: Callable[[str], Dict[str, Any]],
        amplify_holds: Callable[..., None],
        make_amplify_shift: Callable[..., dict],
        collected: str,
        add_second_event: Callable[..., None]
    ) -> None:
        add_second_event(date='2026-09-10')
        amplify_holds({'905196': [make_amplify_shift()]})

        row = read_preview(collected)['rows'][0]

        assert row['willCreate'] == 1
        assert row['alreadyInAmplify'] == 1
        assert row['firstDate'] == '2026-09-10'

    def test_an_unknown_run_is_not_found(
        self,
        running_client: TestClient
    ) -> None:
        response = running_client.get(preview_path(run_id='no-such-run'))

        assert response.status_code == 404
        assert response.headers['content-type'] == PROBLEM_MEDIA_TYPE

    def test_previewing_needs_a_credential(
        self,
        anonymous_client: TestClient,
        run_id: str
    ) -> None:
        assert anonymous_client.get(
            preview_path(run_id=run_id)
        ).status_code == 401
