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
from documents import ROLE_DOCUMENT
from fastapi.testclient import TestClient

# Imports - Local
from star_pass._defaults import LOCAL_TIMEZONE
from star_pass._records import (
    Event,
    EventRole,
    LogEntry,
    Match,
    OP_NUDGE,
    OP_REMOVE,
    OP_SET_SLOTS
)
from star_pass._repository import (
    ChangeLogRepository,
    EventRepository,
    JobRepository,
    RevisionRepository,
    RunRepository
)
from star_pass_api import _defaults
from star_pass_api._problems import PROBLEM_MEDIA_TYPE
from star_pass_api._security import SCOPE_RUNS_READ

# Constants
RUNS_PATH = f'{_defaults.API_VERSION_PREFIX}/runs'

# Where the zone a run reports is read, so a test can separate the
# calendar's setting from the league's.
SETTINGS_READ_IN = 'star_pass_contract._views'


def run_path(run_id: str) -> str:
    """ Return the address of one run. """
    return f'{RUNS_PATH}/{run_id}'


def revisions_path(run_id: str) -> str:
    """ Return the address of one run's revisions. """
    return f'{run_path(run_id=run_id)}/revisions'


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
            'unmatched': 0,
            'uncollected': 0
        }

    def test_the_run_counts_what_its_window_left_out(
        self,
        running_client: TestClient,
        not_collected: Callable[[str], list],
        collected: str
    ) -> None:
        # The figure beside the run and the list behind it are one
        # answer, so a reader is never told to look at rows that are
        # not there.
        left_out = not_collected(collected)

        counts = running_client.get(
            run_path(run_id=collected)
        ).json()['counts']

        assert counts['uncollected'] == len(left_out)

    def test_the_list_names_the_job_still_working_on_a_run(
        self,
        running_client: TestClient,
        run_id: str,
        job_id: str
    ) -> None:
        listed = running_client.get(RUNS_PATH).json()[0]

        assert listed['id'] == run_id
        assert listed['activeJobId'] == job_id

    def test_a_run_names_the_job_a_stopped_service_left_behind(
        self,
        running_client: TestClient,
        jobs: JobRepository,
        run_id: str,
        job_id: str
    ) -> None:
        # An interrupted job is finished, so the run reports nothing
        # active -- and resuming one is a deliberate act (D10), which
        # a caller with no way to name it could not carry out.
        del run_id

        jobs.interrupt_unfinished()

        listed = running_client.get(RUNS_PATH).json()[0]

        assert listed['activeJobId'] is None
        assert listed['interruptedJobId'] == job_id

    def test_a_run_with_nothing_left_behind_names_no_such_job(
        self,
        running_client: TestClient,
        run_id: str,
        job_id: str
    ) -> None:
        del run_id, job_id

        listed = running_client.get(RUNS_PATH).json()[0]

        assert listed['interruptedJobId'] is None

    def test_one_run_names_it_the_way_the_list_does(
        self,
        running_client: TestClient,
        jobs: JobRepository,
        run_id: str,
        job_id: str
    ) -> None:
        # Both are the same statement, and a screen that opened a run
        # from the list would otherwise lose the offer to resume.
        jobs.interrupt_unfinished()

        assert running_client.get(
            run_path(run_id=run_id)
        ).json()['interruptedJobId'] == job_id

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

    def test_the_window_carries_the_days_it_covers(
        self,
        read_run: Callable[[str], Dict[str, Any]],
        run_id: str
    ) -> None:
        # Exclusive on the wire: a run covering September carries the
        # first of October, and whoever displays it says September.
        window = read_run(run_id)['window']

        assert window['start'] == '2026-09-01'
        assert window['end'] == '2026-10-01'

    def test_the_window_carries_the_last_day_as_a_reader_means_it(
        self,
        read_run: Callable[[str], Dict[str, Any]],
        run_id: str
    ) -> None:
        # Published rather than left to each client. Every client
        # showing a window has to say it this way, and the subtraction
        # written once per client is a client that can disagree with
        # the server about which days a run covers.
        window = read_run(run_id)['window']

        assert window['lastDay'] == '2026-09-30'

    def test_the_last_day_of_a_one_day_window_is_its_only_day(
        self,
        read_run: Callable[[str], Dict[str, Any]],
        runs: RunRepository
    ) -> None:
        # The edge the exclusive end is easiest to get wrong at: one
        # day covered is two consecutive dates on the wire.
        run_id = runs.create(
            calendar='practices',
            window_start='2026-09-01',
            window_end='2026-09-02'
        ).id
        window = read_run(run_id)['window']

        assert window['start'] == window['lastDay'] == '2026-09-01'
        assert window['end'] == '2026-09-02'

    def test_the_last_day_is_never_the_end(
        self,
        read_run: Callable[[str], Dict[str, Any]],
        run_id: str
    ) -> None:
        # What a client publishing the end under the other name would
        # produce, which reads as a run covering a day it does not.
        window = read_run(run_id)['window']

        assert window['lastDay'] != window['end']

    def test_the_window_carries_the_zone_the_calendar_was_read_in(
        self,
        monkeypatch: pytest.MonkeyPatch,
        read_run: Callable[[str], Dict[str, Any]],
        run_id: str
    ) -> None:
        # The zone a bound without a UTC offset is read in, which is
        # the calendar's rather than the league's.  A deployment whose
        # calendar keeps a different clock sets that one, and a run
        # naming the other would be reporting a zone its own dates
        # were not read in.
        monkeypatch.setattr(f'{SETTINGS_READ_IN}.GCAL_TIMEZONE', 'Asia/Tokyo')

        assert read_run(run_id)['window']['timezone'] == 'Asia/Tokyo'

    def test_the_zone_is_not_the_one_the_league_keeps_its_clock_by(
        self,
        monkeypatch: pytest.MonkeyPatch,
        read_run: Callable[[str], Dict[str, Any]],
        run_id: str
    ) -> None:
        # The two settings are the same until a deployment separates
        # them, so a test that never separates them would pass against
        # either.
        monkeypatch.setattr(f'{SETTINGS_READ_IN}.GCAL_TIMEZONE', 'Asia/Tokyo')

        assert LOCAL_TIMEZONE != 'Asia/Tokyo'
        assert read_run(run_id)['window']['timezone'] != LOCAL_TIMEZONE


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
        # The timing is the role's, so it is returned with the role
        # rather than with the run's opportunity (D25).
        assert first_event(collected)['roles'] == [ROLE_DOCUMENT]

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
        make_role: Callable[..., EventRole]
    ) -> None:
        # Two calendar hours and a quarter of an hour of offsets would
        # run 135 minutes; the maximum allows 120, which is why the
        # stored shift ends at 21:15.
        del runs
        events.add(
            run_id=run_id,
            revision=revision,
            event=make_event(
                shift_end='21:15',
                roles=(make_role(max_length=120),)
            )
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


class TestWhetherAnEventHasBeenEdited:
    # The review screen offers an undo per row, and this is what says
    # which rows have one.  Nothing stored answers it: the calendar
    # times never move, so what says a person changed an event is that
    # its shift times no longer follow from them.

    def test_an_event_as_collection_left_it_is_not_edited(
        self,
        first_event: Callable[[str], Dict[str, Any]],
        collected: str,
        matching_model: None
    ) -> None:
        del matching_model

        assert first_event(collected)['edited'] is False

    def test_an_event_whose_shift_was_moved_is_edited(
        self,
        first_event: Callable[[str], Dict[str, Any]],
        moved_event: str
    ) -> None:
        assert first_event(moved_event)['edited'] is True

    def test_an_event_the_model_can_no_longer_place_is_not_edited(
        self,
        events: EventRepository,
        first_event: Callable[[str], Dict[str, Any]],
        collected: str,
        revision: int,
        make_event: Callable[..., Event]
    ) -> None:
        # No model is installed, so the event's category is one this
        # deployment does not hold.  Undo would be refused for the same
        # reason the answer cannot be worked out, and a row said to be
        # edited is a row offered a control that fails.
        events.replace(
            run_id=collected,
            revision=revision,
            event=make_event(shift_start='18:45')
        )

        assert first_event(collected)['edited'] is False


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
            action=OP_SET_SLOTS,
            subject='Adult Scrimmages',
            slots=6,
            need_id='905196'
        )

        returned = read_run(run_id)['log']

        assert [
            (
                entry['action'],
                entry['subject'],
                entry['slots'],
                entry['needId']
            )
            for entry in returned
        ] == [(OP_SET_SLOTS, 'Adult Scrimmages', 6, '905196')]

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
            recorded=LogEntry(action=OP_REMOVE, subject='Adult Scrimmages')
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
        assert 'interruptedJobId' in properties
        assert 'collected_at' not in properties
        assert 'interrupted_job_id' not in properties

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

    def test_what_kind_of_revision_each_is_is_returned(
        self,
        running_client: TestClient,
        edited: str
    ) -> None:
        listed = running_client.get(revisions_path(run_id=edited)).json()

        assert [item['kind'] for item in listed] == [
            'collected',
            'continued'
        ]

    def test_a_revision_names_the_one_it_was_made_from(
        self,
        running_client: TestClient,
        edited: str
    ) -> None:
        # A value rather than part of a sentence, so a client can put
        # it into its own. Null for the one a collection filled, which
        # was made from a calendar and not from a revision.
        listed = running_client.get(revisions_path(run_id=edited)).json()

        assert [item['sourceRevision'] for item in listed] == [None, 1]

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
        for title in ('Adult Scrimmages', 'Junior Scrimmages'):
            change_log.add(
                run_id=run_id,
                revision=revision,
                principal_id=_defaults.API_PRINCIPAL_ID,
                recorded=LogEntry(action=OP_REMOVE, subject=title)
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
            recorded=LogEntry(
                action=OP_NUDGE,
                subject='Adult Scrimmages',
                minutes=30
            )
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
        revisions.create(run_id=other.id, replacing=True)
        change_log.add(
            run_id=other.id,
            revision=revision,
            principal_id=_defaults.API_PRINCIPAL_ID,
            recorded=LogEntry(action=OP_REMOVE, subject='Something Else')
        )

        listed = running_client.get(revisions_path(run_id=run_id)).json()

        assert [item['changes'] for item in listed] == [0]
