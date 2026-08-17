#!/usr/bin/env python3
""" Collecting a calendar window into a stored run.

    The calendar and Amplify are reached through
    'Helpers.send_api_request', which is replaced here: no test makes a
    live request.  What is not replaced is everything between that
    boundary and the database, which is what these tests are about.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
import json
import sqlite3
from typing import Any, Callable, Dict, List

# Imports - Third-Party
import pytest
from requests import Response

# Imports - Local
from star_pass import _models
from star_pass._collect import collect
from star_pass._exceptions import ValidationError
from star_pass._reading import changes_in_current, read_run_history
from star_pass._records import (
    MATCH_KIND_KEYWORD,
    RUN_STATUS_COLLECTING,
    RUN_STATUS_UNSENT
)
from star_pass._reporting import Reporter
from star_pass._repository import (
    EventRepository,
    RevisionRepository,
    RunRepository
)

# Constants
# A calendar with one query string, so the calendar is read once and a
# repeat in the results is one the test arranged.
CALENDAR = 'events'

# A calendar with two query strings, so it is read twice and an event
# matching both arrives twice.
REPEATING_CALENDAR = 'practices'
NEED_ID = '879609'
OTHER_NEED_ID = '879610'


def an_item(
    identifier: str = 'gcal-1',
    summary: str = 'Wheels of Justice vs Rose City',
    start: str = '2026-09-03T19:00:00-07:00',
    end: str = '2026-09-03T21:00:00-07:00'
) -> Dict[str, Any]:
    return {
        'id': identifier,
        'summary': summary,
        'start': {'dateTime': start},
        'end': {'dateTime': end}
    }


def a_category(
    need_ids: List[Dict[str, Any]],
    aliases: tuple = ('wheels',)
) -> Dict[str, Any]:
    return {
        'description': 'Adult Games',
        'aliases': list(aliases),
        'need_ids': need_ids
    }


def a_need(
    identifier: str = NEED_ID,
    offset_start: int = 15,
    offset_end: int = 30,
    max_length: Any = 165,
    slots: int = 12
) -> Dict[str, Any]:
    return {
        'id': identifier,
        'offset_start': offset_start,
        'offset_end': offset_end,
        'max_length': max_length,
        'slots': slots
    }


def a_model(categories: Dict[str, Any]) -> Dict[str, Any]:
    # Every configured calendar is given the same categories, so a
    # test can collect either one without arranging a second model.
    entry = {
        'categories': categories,
        'default': {
            'description': 'Unknown Game',
            'need_ids': [a_need(identifier='')]
        }
    }

    return {'calendar': {CALENDAR: entry, REPEATING_CALENDAR: entry}}


@pytest.fixture(name='answers')
def fixture_answers(monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    """ Return a way to script the calendar and Amplify answers. """

    def script(
        items: List[Dict[str, Any]],
        titled: bool = True
    ) -> None:
        """ Answer every calendar read with 'items', and name needs.

            'titled' is what Amplify answers about an opportunity: a
            title, or an answer carrying none.
        """

        def need_body(url: str) -> Dict[str, Any]:
            """ Return what Amplify says about one opportunity. """
            if not titled:
                return {'data': {}}

            return {
                'data': {'need_title': f'Need {url.rsplit("/", 1)[-1]}'}
            }

        def send(_self: Any, api_request_data: Dict[str, Any], **_: Any):
            url = api_request_data['url']
            body = (
                need_body(url=url)
                if '/needs/' in url
                else {'items': items}
            )
            response = Response()
            response.status_code = 200
            response.headers['Content-Type'] = 'application/json'
            # pylint: disable-next=protected-access
            response._content = json.dumps(body).encode('utf-8')

            return response

        monkeypatch.setattr(
            'star_pass._helpers.Helpers.send_api_request',
            send
        )

    return script


@pytest.fixture(name='model')
def fixture_model(monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    """ Return a way to replace the shift data model. """

    def replace(categories: Dict[str, Any]) -> None:
        monkeypatch.setattr(
            _models,
            'get_shifts_info',
            lambda: a_model(categories=categories)
        )

    return replace


@pytest.fixture(name='window')
def fixture_window(monkeypatch: pytest.MonkeyPatch) -> None:
    """ Read an offset-less window in a fixed zone. """
    monkeypatch.setenv('GCAL_TIMEZONE', 'America/Los_Angeles')

    return None


@pytest.fixture(name='collecting')
def fixture_collecting(runs: RunRepository) -> str:
    """ Return a run asked for and not yet collected into. """
    return runs.create(
        calendar=CALENDAR,
        window_start='2026-09-01',
        window_end='2026-10-01'
    ).id


# Every test arranges the same five things and then collects, so the
# arrangement is one fixture rather than five on each of them.  The
# count below is those five; a test that named them itself would carry
# the same disable and repeat the arrangement as well.
# pylint: disable-next=too-many-arguments,too-many-positional-arguments
@pytest.fixture(name='collect_run')
def fixture_collect_run(
    connection: sqlite3.Connection,
    collecting: str,
    answers: Callable[..., None],
    model: Callable[..., None],
    window: None
) -> Callable[..., Any]:
    """ Return a way to script the reads and collect a run. """
    del window

    def run(
        items: List[Dict[str, Any]],
        categories: Dict[str, Any] = None,
        run_id: str = None,
        titled: bool = True
    ):
        """ Collect, with the calendar and Amplify answering to plan. """
        model(
            categories=(
                categories
                if categories is not None
                else {'adult_game': a_category(need_ids=[a_need()])}
            )
        )
        answers(items=items, titled=titled)

        return collect(
            connection=connection,
            run_id=run_id if run_id is not None else collecting,
            reporter=Reporter()
        )

    return run


class TestWhatACollectedRunHolds:
    def test_a_calendar_item_becomes_an_event(
        self,
        collect_run: Callable[..., Any],
        collecting: str,
        events: EventRepository
    ) -> None:
        collect_run(
            items=[an_item()]
        )

        stored = events.list_all(run_id=collecting, revision=1)

        assert [event.title for event in stored] == [
            'Wheels of Justice vs Rose City'
        ]

    def test_the_run_is_no_longer_being_collected(
        self,
        collect_run: Callable[..., Any],
        collecting: str,
        runs: RunRepository
    ) -> None:
        assert runs.get(
            run_id=collecting
        ).status == RUN_STATUS_COLLECTING

        collected = collect_run(
            items=[an_item()]
        )

        assert collected.status == RUN_STATUS_UNSENT

    def test_the_events_land_in_a_first_revision(
        self,
        collect_run: Callable[..., Any],
        collecting: str,
        revisions: RevisionRepository
    ) -> None:
        collect_run(
            items=[an_item()]
        )

        stored = revisions.list_all(run_id=collecting)

        assert [revision.number for revision in stored] == [1]
        assert stored[0].label == 'As collected'

    def test_an_event_carries_a_role_for_every_need_it_serves(
        self,
        collect_run: Callable[..., Any],
        collecting: str,
        events: EventRepository
    ) -> None:
        collect_run(
            items=[an_item()],
            categories={
                'adult_game': a_category(
                    need_ids=[
                        a_need(),
                        a_need(identifier=OTHER_NEED_ID, slots=8)
                    ]
                )
            }
        )

        roles = events.list_all(run_id=collecting, revision=1)[0].roles

        assert [(role.need_id, role.slots) for role in roles] == [
            (NEED_ID, 12),
            (OTHER_NEED_ID, 8)
        ]

    def test_an_event_records_how_its_title_matched(
        self,
        collect_run: Callable[..., Any],
        collecting: str,
        events: EventRepository
    ) -> None:
        collect_run(
            items=[an_item()]
        )

        event = events.list_all(run_id=collecting, revision=1)[0]

        assert event.category == 'adult_game'
        assert event.match.kind == MATCH_KIND_KEYWORD
        assert event.match.keyword == 'wheels'


class TestTheTimesAnEventIsStoredWith:
    def test_the_calendar_times_are_read_in_the_league_zone(
        self,
        collect_run: Callable[..., Any],
        collecting: str,
        events: EventRepository
    ) -> None:
        # The same instant, written with a different offset, is the
        # same evening in the league's own zone.
        collect_run(
            items=[
                an_item(
                    start='2026-09-04T02:00:00+00:00',
                    end='2026-09-04T04:00:00+00:00'
                )
            ]
        )

        event = events.list_all(run_id=collecting, revision=1)[0]

        assert event.date == '2026-09-03'
        assert (event.calendar_start, event.calendar_end) == (
            '19:00',
            '21:00'
        )

    # The offsets move a 19:00-21:00 event to 19:15-21:30, which is
    # 135 minutes.  A maximum below that is what decides the end
    # instead, and one above it changes nothing.
    @pytest.mark.parametrize(
        'max_length, shift_end',
        [
            (None, '21:30'),
            (165, '21:30'),
            (60, '20:15')
        ]
    )
    def test_the_offsets_move_the_times_until_a_maximum_binds(
        self,
        collect_run: Callable[..., Any],
        collecting: str,
        events: EventRepository,
        max_length: Any,
        shift_end: str
    ) -> None:
        collect_run(
            items=[an_item()],
            categories={
                'adult_game': a_category(
                    need_ids=[a_need(max_length=max_length)]
                )
            }
        )

        event = events.list_all(run_id=collecting, revision=1)[0]

        assert (event.shift_start, event.shift_end) == (
            '19:15',
            shift_end
        )

    def test_the_smallest_maximum_is_the_one_that_binds(
        self,
        collect_run: Callable[..., Any],
        collecting: str,
        events: EventRepository
    ) -> None:
        collect_run(
            items=[an_item()],
            categories={
                'adult_game': a_category(
                    need_ids=[
                        a_need(max_length=90),
                        a_need(
                            identifier=OTHER_NEED_ID,
                            max_length=60
                        )
                    ]
                )
            }
        )

        event = events.list_all(run_id=collecting, revision=1)[0]

        assert event.shift_end == '20:15'


class TestTheOpportunitiesARunResolves:
    def test_an_opportunity_is_named_by_amplify(
        self,
        collect_run: Callable[..., Any],
        collecting: str,
        runs: RunRepository
    ) -> None:
        # Read while the run is collected, not when a preview is asked
        # for: every review row is labelled with one.
        collect_run(
            items=[an_item()]
        )

        stored = runs.get_opportunities(run_id=collecting)

        assert [(one.need_id, one.title) for one in stored] == [
            (NEED_ID, f'Need {NEED_ID}')
        ]

    def test_an_opportunity_amplify_does_not_name_says_so(
        self,
        collect_run: Callable[..., Any],
        collecting: str,
        runs: RunRepository
    ) -> None:
        # A row labelled with nothing reads as a rendering fault.
        collect_run(items=[an_item()], titled=False)

        assert runs.get_opportunities(
            run_id=collecting
        )[0].title == 'Unknown'

    def test_an_opportunity_carries_where_it_is_published(
        self,
        collect_run: Callable[..., Any],
        collecting: str,
        runs: RunRepository
    ) -> None:
        collect_run(
            items=[an_item()]
        )

        assert runs.get_opportunities(
            run_id=collecting
        )[0].url.endswith(NEED_ID)

    def test_an_opportunity_carries_the_timing_the_model_gives_it(
        self,
        collect_run: Callable[..., Any],
        collecting: str,
        runs: RunRepository
    ) -> None:
        collect_run(
            items=[an_item()]
        )

        stored = runs.get_opportunities(run_id=collecting)[0]

        assert (
            stored.offset_start,
            stored.offset_end,
            stored.max_length,
            stored.default_slots
        ) == (15, 30, 165, 12)

    def test_one_opportunity_is_stored_however_many_events_name_it(
        self,
        collect_run: Callable[..., Any],
        collecting: str,
        runs: RunRepository
    ) -> None:
        collect_run(
            items=[an_item(), an_item(identifier='gcal-2')]
        )

        assert len(runs.get_opportunities(run_id=collecting)) == 1


class TestAnEventThatCannotBecomeAShift:
    def test_an_unmatched_title_is_stored_with_no_role(
        self,
        collect_run: Callable[..., Any],
        collecting: str,
        events: EventRepository
    ) -> None:
        # Stored rather than dropped: a missing shift is invisible
        # until volunteers cannot sign up, and an event with no role
        # is what stops the run being sent.
        collect_run(
            items=[an_item(summary='Quilting Circle Meetup')]
        )

        event = events.list_all(run_id=collecting, revision=1)[0]

        assert event.roles == ()
        assert event.category is None
        assert event.match is None

    def test_an_unmatched_event_keeps_the_calendar_times(
        self,
        collect_run: Callable[..., Any],
        collecting: str,
        events: EventRepository
    ) -> None:
        # There is no opportunity to offset them by.
        collect_run(
            items=[an_item(summary='Quilting Circle Meetup')]
        )

        event = events.list_all(run_id=collecting, revision=1)[0]

        assert (event.shift_start, event.shift_end) == (
            event.calendar_start,
            event.calendar_end
        )


class TestWhatStopsTheRun:
    def test_a_shift_ending_before_it_starts_stops_the_run(
        self,
        collect_run: Callable[..., Any]
    ) -> None:
        with pytest.raises(ValidationError) as error:
            collect_run(
                items=[an_item()],
                categories={
                    'adult_game': a_category(
                        need_ids=[
                            a_need(offset_start=0, offset_end=-180)
                        ]
                    )
                }
            )

        assert 'Wheels of Justice' in str(error.value)

    def test_a_category_whose_needs_disagree_stops_the_run(
        self,
        collect_run: Callable[..., Any]
    ) -> None:
        # An event records one pair of shift times for every role it
        # serves, so these two describe shifts it cannot both hold.
        with pytest.raises(ValidationError) as error:
            collect_run(
                items=[an_item()],
                categories={
                    'adult_game': a_category(
                        need_ids=[
                            a_need(),
                            a_need(
                                identifier=OTHER_NEED_ID,
                                offset_start=45
                            )
                        ]
                    )
                }
            )

        assert 'adult_game' in str(error.value)

    def test_two_categories_timing_one_need_differently_stop_the_run(
        self,
        collect_run: Callable[..., Any]
    ) -> None:
        # A run records one set of offsets per opportunity.
        with pytest.raises(ValidationError) as error:
            collect_run(
                items=[
                    an_item(),
                    an_item(identifier='gcal-2', summary='Axles of Evil')
                ],
                categories={
                    'adult_game': a_category(need_ids=[a_need()]),
                    'other_game': a_category(
                        need_ids=[a_need(offset_start=45)],
                        aliases=('axles',)
                    )
                }
            )

        assert NEED_ID in str(error.value)

    def test_a_shift_crossing_midnight_stops_the_run(
        self,
        collect_run: Callable[..., Any]
    ) -> None:
        # An event stores its times as times of day, so a shift that
        # ran past midnight could not be read back as the one stored.
        with pytest.raises(ValidationError) as error:
            collect_run(
                items=[
                    an_item(
                        start='2026-09-03T22:00:00-07:00',
                        end='2026-09-03T23:30:00-07:00'
                    )
                ],
                categories={
                    'adult_game': a_category(
                        need_ids=[
                            a_need(offset_end=60, max_length=None)
                        ]
                    )
                }
            )

        assert 'midnight' in str(error.value)

    def test_a_run_that_stopped_stores_nothing(
        self,
        collect_run: Callable[..., Any],
        collecting: str,
        runs: RunRepository,
        revisions: RevisionRepository
    ) -> None:
        with pytest.raises(ValidationError):
            collect_run(
                items=[an_item()],
                categories={
                    'adult_game': a_category(
                        need_ids=[
                            a_need(offset_start=0, offset_end=-180)
                        ]
                    )
                }
            )

        assert revisions.list_all(run_id=collecting) == []
        assert runs.get(
            run_id=collecting
        ).status == RUN_STATUS_COLLECTING

    def test_a_failure_part_way_through_the_write_stores_nothing(
        self,
        collect_run: Callable[..., Any],
        collecting: str,
        revisions: RevisionRepository,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The revision and its events are written before the
        # opportunities.  A run left holding events that nothing
        # labels reads the same as one whose opportunities Amplify
        # forgot, so either all of it lands or none does.
        def refuse(*_: Any, **__: Any) -> None:
            raise ValidationError('Amplify went away mid-write.')

        monkeypatch.setattr(
            RunRepository,
            'set_opportunities',
            refuse
        )

        with pytest.raises(ValidationError):
            collect_run(items=[an_item()])

        assert revisions.list_all(run_id=collecting) == []

    def test_collecting_into_a_run_that_is_not_there_is_refused(
        self,
        connection: sqlite3.Connection
    ) -> None:
        with pytest.raises(ValidationError) as error:
            collect(
                connection=connection,
                run_id='no-such-run',
                reporter=Reporter()
            )

        assert 'no-such-run' in str(error.value)


class TestReadingTheCalendarTwice:
    def test_an_item_arriving_twice_is_stored_once(
        self,
        collect_run: Callable[..., Any],
        runs: RunRepository,
        events: EventRepository
    ) -> None:
        # The calendar is searched once per configured query string
        # and the results are concatenated, so an event matching two
        # of them arrives twice.  It is one event.
        run_id = runs.create(
            calendar=REPEATING_CALENDAR,
            window_start='2026-09-01',
            window_end='2026-10-01'
        ).id

        collect_run(items=[an_item()], run_id=run_id)

        assert len(events.list_all(run_id=run_id, revision=1)) == 1


class TestCollectingARunAgain:
    def test_a_second_collection_adds_a_revision(
        self,
        collect_run: Callable[..., Any],
        collecting: str,
        revisions: RevisionRepository
    ) -> None:
        collect_run(items=[an_item()])
        collect_run(items=[an_item()])

        assert [
            revision.number
            for revision in revisions.list_all(run_id=collecting)
        ] == [1, 2]

    def test_a_second_collection_is_labelled_as_one(
        self,
        collect_run: Callable[..., Any],
        collecting: str,
        revisions: RevisionRepository
    ) -> None:
        # Which of the two it is says whether anything was there
        # before, which is what a reader wants from the label.
        collect_run(items=[an_item()])
        collect_run(items=[an_item()])

        assert [
            revision.label
            for revision in revisions.list_all(run_id=collecting)
        ] == ['As collected', 'As recollected']

    def test_a_second_collection_holds_only_what_the_calendar_has_now(
        self,
        collect_run: Callable[..., Any],
        collecting: str,
        events: EventRepository
    ) -> None:
        # Replacing, not continuing: an event the calendar no longer
        # has must not be carried forward into the new revision.
        collect_run(
            items=[an_item(), an_item(identifier='gcal-2')]
        )
        collect_run(items=[an_item()])

        assert [
            event.id
            for event in events.list_all(run_id=collecting, revision=2)
        ] == ['gcal-1']

    def test_the_revision_that_was_replaced_is_still_readable(
        self,
        collect_run: Callable[..., Any],
        collecting: str,
        events: EventRepository
    ) -> None:
        collect_run(
            items=[an_item(), an_item(identifier='gcal-2')]
        )
        collect_run(items=[an_item()])

        assert len(
            events.list_all(run_id=collecting, revision=1)
        ) == 2

    def test_the_change_count_read_is_the_current_revision_s(
        self,
        collect_run: Callable[..., Any],
        collecting: str,
        connection: sqlite3.Connection,
        add_log_entry: Callable[..., Any]
    ) -> None:
        # Two revisions with different counts, so a reader taking the
        # first one it finds gets the wrong number.
        collect_run(items=[an_item()])
        add_log_entry(
            run_id=collecting,
            revision=1,
            entry='Nudged one event'
        )
        add_log_entry(
            run_id=collecting,
            revision=1,
            entry='Nudged another'
        )
        collect_run(items=[an_item()])
        add_log_entry(
            run_id=collecting,
            revision=2,
            entry='Nudged one more'
        )

        run, listed = read_run_history(
            connection=connection,
            run_id=collecting
        )

        assert changes_in_current(run=run, revisions=listed) == 1
