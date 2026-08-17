#!/usr/bin/env python3
""" What a collected run holds.

    The events the calendar window became, the times they are stored
    with, the opportunities they name, and everything that stops a run
    rather than being quietly dropped.  What the window held and the
    run left out is asked in 'test_uncollected.py', off the same
    arrangement.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
import sqlite3
from typing import Any, Callable

# Imports - Third-Party
import pytest

# Imports - Local
from collecting._arranging import (
    an_item,
    NEED_ID,
    OTHER_NEED_ID,
    REPEATING_CALENDAR
)
from conftest import a_category, a_need
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
