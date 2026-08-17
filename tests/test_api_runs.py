#!/usr/bin/env python3
""" Tests for reading runs, and for reading one in full.

    What each derived figure means is pinned in 'test_derived.py' and
    'test_run_figures.py'.  These tests ask a narrower question: that
    the endpoint publishes the answer, under the name and in the shape
    the contract promises.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring
# pylint: disable=too-many-arguments,too-many-positional-arguments

# Imports - Python Standard Library
from typing import Any, Callable, Dict

# Imports - Third-Party
import pytest
from fastapi.testclient import TestClient

# Imports - Local
from star_pass._defaults import LOCAL_TIMEZONE
from star_pass._preview import (
    BLOCKER_ENDS_BEFORE_START,
    BLOCKER_NO_OPPORTUNITY,
    BLOCKER_NO_SLOTS
)
from star_pass._records import Event, EventRole, Match, Opportunity
from star_pass._repository import (
    ChangeLogRepository,
    EventRepository,
    RevisionRepository,
    RunRepository
)
from star_pass_api import _defaults
from star_pass_api._problems import PROBLEM_MEDIA_TYPE
from star_pass_api._security import SCOPE_RUNS_READ

# Constants
RUNS_PATH = f'{_defaults.API_VERSION_PREFIX}/runs'


def run_path(run_id: str) -> str:
    """ Return the address of one run. """
    return f'{RUNS_PATH}/{run_id}'


def revisions_path(run_id: str) -> str:
    """ Return the address of one run's revisions. """
    return f'{run_path(run_id=run_id)}/revisions'


def preview_path(run_id: str) -> str:
    """ Return the address of one run's preview. """
    return f'{run_path(run_id=run_id)}/preview'


@pytest.fixture(name='read_run')
def fixture_read_run(
    running_client: TestClient
) -> Callable[[str], Dict[str, Any]]:
    """ Return a way to read one run and get the document back. """

    def read(run_id: str) -> Dict[str, Any]:
        """ Read the run, failing the test if it was not found. """
        response = running_client.get(run_path(run_id=run_id))

        assert response.status_code == 200

        return response.json()

    return read


@pytest.fixture(name='first_event')
def fixture_first_event(
    read_run: Callable[[str], Dict[str, Any]]
) -> Callable[[str], Dict[str, Any]]:
    """ Return a way to read a run's first event. """

    def read(run_id: str) -> Dict[str, Any]:
        """ Read the run and return the first event it holds. """
        return read_run(run_id)['events'][0]

    return read


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


@pytest.fixture(name='labelled')
def fixture_labelled(
    runs: RunRepository,
    collected: str,
    make_opportunity: Callable[..., Opportunity]
) -> str:
    """ Return the collected run with its opportunity stored. """
    runs.set_opportunities(
        run_id=collected,
        opportunities=[make_opportunity()]
    )

    return collected


class TestListingRuns:
    def test_a_run_appears_in_the_list(
        self,
        running_client: TestClient,
        run_id: str
    ) -> None:
        response = running_client.get(RUNS_PATH)

        assert response.status_code == 200
        assert [run['id'] for run in response.json()] == [run_id]

    def test_no_runs_reads_as_an_empty_list(
        self,
        running_client: TestClient
    ) -> None:
        # An empty list, not a 404: the question "which runs are
        # there" has an answer even when the answer is none.
        response = running_client.get(RUNS_PATH)

        assert response.status_code == 200
        assert response.json() == []

    def test_the_list_carries_what_the_revision_holds(
        self,
        running_client: TestClient,
        collected: str
    ) -> None:
        # Enough to decide what to open without reading each run in
        # turn, which is what the list is for.
        listed = running_client.get(RUNS_PATH).json()[0]

        assert listed['id'] == collected
        assert listed['counts'] == {
            'events': 1,
            'shifts': 1,
            'unmatched': 0
        }

    def test_the_list_names_the_job_still_working_on_a_run(
        self,
        running_client: TestClient,
        run_id: str,
        job_id: str
    ) -> None:
        listed = running_client.get(RUNS_PATH).json()[0]

        assert listed['id'] == run_id
        assert listed['activeJobId'] == job_id

    def test_the_list_does_not_carry_a_runs_events(
        self,
        running_client: TestClient,
        collected: str
    ) -> None:
        # A list of runs is not a list of every event in every run,
        # even though this one has an event to leave out.
        listed = running_client.get(RUNS_PATH).json()[0]

        assert listed['id'] == collected
        assert listed['counts']['events'] == 1
        assert 'events' not in listed

    def test_listing_runs_needs_a_credential(
        self,
        anonymous_client: TestClient
    ) -> None:
        assert anonymous_client.get(RUNS_PATH).status_code == 401


class TestReadingOneRun:
    def test_a_run_reads_back(
        self,
        read_run: Callable[[str], Dict[str, Any]],
        run_id: str
    ) -> None:
        assert read_run(run_id)['id'] == run_id

    def test_an_unknown_run_is_not_found(
        self,
        running_client: TestClient
    ) -> None:
        # The repository reports a value it cannot use and a missing
        # run the same way, so the endpoint says which it asked for.
        response = running_client.get(run_path(run_id='no-such-run'))

        assert response.status_code == 404
        assert response.headers['content-type'] == PROBLEM_MEDIA_TYPE
        assert 'no-such-run' in response.json()['detail']

    def test_reading_a_run_needs_a_credential(
        self,
        anonymous_client: TestClient,
        run_id: str
    ) -> None:
        assert anonymous_client.get(
            run_path(run_id=run_id)
        ).status_code == 401

    def test_the_fields_are_camel_case(
        self,
        read_run: Callable[[str], Dict[str, Any]],
        run_id: str
    ) -> None:
        # The contract is read by a browser and by generated clients.
        document = read_run(run_id)

        assert 'collectedAt' in document
        assert 'currentRevision' in document
        assert 'collected_at' not in document

    def test_the_window_carries_the_zone_it_is_read_in(
        self,
        read_run: Callable[[str], Dict[str, Any]],
        run_id: str
    ) -> None:
        # The server's zone is the authoritative one, so a client is
        # told which it is rather than working the window out in the
        # zone of whoever is looking at it.
        assert read_run(run_id)['window'] == {
            'start': '2026-09-01',
            'end': '2026-10-01',
            'timezone': LOCAL_TIMEZONE
        }


class TestTheEventsOfARun:
    def test_a_run_before_its_first_revision_has_no_events(
        self,
        read_run: Callable[[str], Dict[str, Any]],
        run_id: str
    ) -> None:
        # A run before its first revision reports revision 0, which
        # holds nothing and reads back as nothing.
        document = read_run(run_id)

        assert document['currentRevision'] == 0
        assert document['events'] == []

    def test_only_the_current_revisions_events_are_returned(
        self,
        read_run: Callable[[str], Dict[str, Any]],
        edited: str
    ) -> None:
        # Revision 1 holds the event starting at 19:15; revision 2
        # moved it, and revision 2 is the one being edited.
        document = read_run(edited)

        assert document['currentRevision'] == 2
        assert [
            event['shiftStart'] for event in document['events']
        ] == ['19:45']

    def test_an_events_roles_are_returned_with_it(
        self,
        first_event: Callable[[str], Dict[str, Any]],
        collected: str
    ) -> None:
        assert first_event(collected)['roles'] == [
            {'needId': '905196', 'slots': 4, 'edited': False}
        ]

    def test_how_a_title_matched_is_returned(
        self,
        events: EventRepository,
        first_event: Callable[[str], Dict[str, Any]],
        run_id: str,
        revision: int,
        make_event: Callable[..., Event]
    ) -> None:
        events.add(
            run_id=run_id,
            revision=revision,
            event=make_event(
                match=Match(kind='fuzzy', keyword=None, score=88)
            )
        )

        assert first_event(run_id)['match'] == {
            'kind': 'fuzzy',
            'keyword': None,
            'score': 88
        }

    def test_an_event_that_matched_nothing_carries_no_match(
        self,
        first_event: Callable[[str], Dict[str, Any]],
        collected: str
    ) -> None:
        assert first_event(collected)['match'] is None


class TestWhatAnEventDoesNotStore:
    def test_the_shift_length_is_published(
        self,
        first_event: Callable[[str], Dict[str, Any]],
        collected: str
    ) -> None:
        # 19:15 to 21:30 is the duration Amplify is given.
        assert first_event(collected)['lengthMinutes'] == 135

    def test_a_shift_no_maximum_shortened_names_no_cap(
        self,
        first_event: Callable[[str], Dict[str, Any]],
        labelled: str
    ) -> None:
        assert first_event(labelled)['cappedAt'] is None

    def test_the_maximum_that_shortened_a_shift_is_named(
        self,
        events: EventRepository,
        runs: RunRepository,
        first_event: Callable[[str], Dict[str, Any]],
        run_id: str,
        revision: int,
        make_event: Callable[..., Event],
        make_opportunity: Callable[..., Opportunity]
    ) -> None:
        # Two calendar hours and a quarter of an hour of offsets would
        # run 135 minutes; the maximum allows 120, which is why the
        # stored shift ends at 21:15.
        runs.set_opportunities(
            run_id=run_id,
            opportunities=[make_opportunity(max_length=120)]
        )
        events.add(
            run_id=run_id,
            revision=revision,
            event=make_event(shift_end='21:15')
        )

        assert first_event(run_id)['cappedAt'] == 120

    def test_a_repeated_event_names_the_earlier_one(
        self,
        read_run: Callable[[str], Dict[str, Any]],
        collected: str,
        add_second_event: Callable[..., None]
    ) -> None:
        add_second_event()

        returned = read_run(collected)['events']

        assert [event['duplicateOf'] for event in returned] == [
            None,
            'event-1'
        ]

    def test_an_event_creating_no_shift_is_marked_blocking(
        self,
        read_run: Callable[[str], Dict[str, Any]],
        collected: str,
        add_second_event: Callable[..., None]
    ) -> None:
        add_second_event(category=None, roles=())

        blocking = {
            event['id']: event['blocking']
            for event in read_run(collected)['events']
        }

        assert blocking == {'event-1': False, 'event-2': True}


class TestWhatIsShownBesideARun:
    def test_the_opportunities_are_returned(
        self,
        read_run: Callable[[str], Dict[str, Any]],
        labelled: str
    ) -> None:
        # Every review row is labelled with an Amplify title, so they
        # are stored with the run rather than looked up at preview.
        returned = read_run(labelled)['opportunities']

        assert [
            (item['needId'], item['title']) for item in returned
        ] == [('905196', 'Adult Scrimmages: Skating Officials')]

    def test_a_run_that_resolved_nothing_has_no_opportunities(
        self,
        read_run: Callable[[str], Dict[str, Any]],
        run_id: str
    ) -> None:
        assert read_run(run_id)['opportunities'] == []

    def test_the_change_log_is_returned(
        self,
        add_log_entry: Callable[..., None],
        read_run: Callable[[str], Dict[str, Any]],
        run_id: str,
        revision: int
    ) -> None:
        add_log_entry(
            run_id=run_id,
            revision=revision,
            entry='Set slots to 6 on Adult Scrimmages'
        )

        returned = read_run(run_id)['log']

        assert [entry['entry'] for entry in returned] == [
            'Set slots to 6 on Adult Scrimmages'
        ]

    def test_the_change_log_records_who_made_the_change(
        self,
        change_log: ChangeLogRepository,
        read_run: Callable[[str], Dict[str, Any]],
        run_id: str,
        revision: int
    ) -> None:
        # Recorded from the first entry, while there is still one
        # principal, so the field is already populated when there is
        # more than one.
        change_log.add(
            run_id=run_id,
            revision=revision,
            principal_id=_defaults.API_PRINCIPAL_ID,
            entry='Removed Adult Scrimmages'
        )

        assert read_run(run_id)['log'][0]['principalId'] == (
            _defaults.API_PRINCIPAL_ID
        )

    def test_a_run_nothing_was_done_to_has_an_empty_log(
        self,
        read_run: Callable[[str], Dict[str, Any]],
        run_id: str
    ) -> None:
        assert read_run(run_id)['log'] == []


class TestWhatTheSpecificationSays:
    def test_both_endpoints_declare_the_scope_they_need(
        self,
        client: TestClient
    ) -> None:
        paths = client.get(_defaults.API_OPENAPI_PATH).json()['paths']

        for address in ('/v1/runs', '/v1/runs/{run_id}'):
            assert [SCOPE_RUNS_READ] in [
                scopes
                for requirement in paths[address]['get']['security']
                for scopes in requirement.values()
            ], address

    def test_the_run_shape_is_published_in_camel_case(
        self,
        client: TestClient
    ) -> None:
        properties = client.get(
            _defaults.API_OPENAPI_PATH
        ).json()['components']['schemas']['RunView']['properties']

        assert 'collectedAt' in properties
        assert 'activeJobId' in properties
        assert 'collected_at' not in properties

    def test_the_detail_shape_carries_what_a_run_alone_does_not(
        self,
        client: TestClient
    ) -> None:
        schemas = client.get(
            _defaults.API_OPENAPI_PATH
        ).json()['components']['schemas']
        detail = schemas['RunDetailView']['properties']

        assert 'events' in detail
        assert 'opportunities' in detail
        assert 'log' in detail
        assert 'events' not in schemas['RunView']['properties']


class TestListingRevisions:
    def test_a_revision_appears_in_the_list(
        self,
        running_client: TestClient,
        run_id: str,
        revision: int
    ) -> None:
        response = running_client.get(revisions_path(run_id=run_id))

        assert response.status_code == 200
        assert [item['number'] for item in response.json()] == [revision]

    def test_revisions_are_listed_oldest_first(
        self,
        running_client: TestClient,
        edited: str
    ) -> None:
        listed = running_client.get(revisions_path(run_id=edited)).json()

        assert [item['number'] for item in listed] == [1, 2]

    def test_the_last_revision_is_the_current_one(
        self,
        running_client: TestClient,
        edited: str
    ) -> None:
        # Everything below it is history and is never written to
        # again, which is what the flag tells a reader.
        listed = running_client.get(revisions_path(run_id=edited)).json()

        assert [item['current'] for item in listed] == [False, True]

    def test_a_revisions_label_is_returned(
        self,
        running_client: TestClient,
        edited: str
    ) -> None:
        listed = running_client.get(revisions_path(run_id=edited)).json()

        assert [item['label'] for item in listed] == [
            'As collected',
            'Edited'
        ]

    def test_a_run_with_no_revision_reads_as_an_empty_list(
        self,
        running_client: TestClient,
        run_id: str
    ) -> None:
        # A run that exists and has no revision is a different fact
        # from a run that does not exist, and reads differently.
        response = running_client.get(revisions_path(run_id=run_id))

        assert response.status_code == 200
        assert response.json() == []

    def test_an_unknown_run_is_not_found(
        self,
        running_client: TestClient
    ) -> None:
        response = running_client.get(revisions_path(run_id='no-such-run'))

        assert response.status_code == 404
        assert response.headers['content-type'] == PROBLEM_MEDIA_TYPE
        assert 'no-such-run' in response.json()['detail']

    def test_listing_revisions_needs_a_credential(
        self,
        anonymous_client: TestClient,
        run_id: str
    ) -> None:
        assert anonymous_client.get(
            revisions_path(run_id=run_id)
        ).status_code == 401


class TestWhatWasDoneInARevision:
    def test_a_revision_nothing_was_done_in_counts_nothing(
        self,
        running_client: TestClient,
        run_id: str,
        revision: int
    ) -> None:
        listed = running_client.get(revisions_path(run_id=run_id)).json()

        assert [
            (item['number'], item['changes']) for item in listed
        ] == [(revision, 0)]

    def test_the_changes_made_while_a_revision_was_current_are_counted(
        self,
        change_log: ChangeLogRepository,
        running_client: TestClient,
        run_id: str,
        revision: int
    ) -> None:
        for entry in ('Set slots to 6', 'Removed Adult Scrimmages'):
            change_log.add(
                run_id=run_id,
                revision=revision,
                principal_id=_defaults.API_PRINCIPAL_ID,
                entry=entry
            )

        listed = running_client.get(revisions_path(run_id=run_id)).json()

        assert [item['changes'] for item in listed] == [2]

    def test_a_change_counts_against_the_revision_it_was_made_in(
        self,
        change_log: ChangeLogRepository,
        running_client: TestClient,
        edited: str
    ) -> None:
        # The count says what was done while each revision was the
        # current one, so an edit made now belongs to the second and
        # leaves the first as it was.
        change_log.add(
            run_id=edited,
            revision=2,
            principal_id=_defaults.API_PRINCIPAL_ID,
            entry='Nudged Adult Scrimmages by 30 minutes'
        )

        listed = running_client.get(revisions_path(run_id=edited)).json()

        assert [item['changes'] for item in listed] == [0, 1]

    def test_another_runs_changes_are_not_counted(
        self,
        change_log: ChangeLogRepository,
        running_client: TestClient,
        runs: RunRepository,
        revisions: RevisionRepository,
        run_id: str,
        revision: int
    ) -> None:
        other = runs.create(
            calendar='events',
            window_start='2026-09-01',
            window_end='2026-10-01'
        )
        revisions.create(run_id=other.id, label='As collected')
        change_log.add(
            run_id=other.id,
            revision=revision,
            principal_id=_defaults.API_PRINCIPAL_ID,
            entry='Removed something from the other run'
        )

        listed = running_client.get(revisions_path(run_id=run_id)).json()

        assert [item['changes'] for item in listed] == [0]


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
