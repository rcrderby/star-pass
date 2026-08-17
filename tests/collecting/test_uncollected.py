#!/usr/bin/env python3
""" What a run's window held and the run did not collect.

    Stored by the collection rather than worked out when somebody
    asks: the figure is shown on every reading of the run, and a live
    calendar read would cost a Google request per look and give the
    run a second opinion about its own window.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
from typing import Any, Callable

# Imports - Third-Party
import pytest

# Imports - Local
from collecting._arranging import an_item, REPEATING_CALENDAR
from conftest import a_category, a_need
from star_pass._exceptions import ValidationError
from star_pass._records import (
    UNCOLLECTED_ALL_DAY,
    UNCOLLECTED_EXCLUDED,
    UNCOLLECTED_SEARCH,
    UNCOLLECTED_UNTITLED
)
from star_pass._repository import (
    EventRepository,
    RunRepository,
    UncollectedRepository
)


class TestWhatTheWindowHeldAndTheRunLeftOut:
    # Stored by the collection rather than worked out when somebody
    # asks, because the figure is shown on every reading of the run
    # and a live read would cost a calendar request per look.

    def test_a_collected_event_is_not_among_them(
        self,
        collect_run: Callable[..., Any],
        collecting: str,
        uncollected: UncollectedRepository
    ) -> None:
        collect_run(items=[an_item()])

        assert uncollected.list_all(run_id=collecting) == []

    def test_an_excluded_title_is_recorded_as_excluded(
        self,
        collect_run: Callable[..., Any],
        collecting: str,
        uncollected: UncollectedRepository
    ) -> None:
        collect_run(
            items=[
                an_item(),
                an_item(
                    identifier='gcal-2',
                    summary='CANCELED: Wheels of Justice'
                )
            ]
        )

        stored = uncollected.list_all(run_id=collecting)

        assert [(row.id, row.reason) for row in stored] == [
            ('gcal-2', UNCOLLECTED_EXCLUDED)
        ]

    def test_an_all_day_event_keeps_its_day_and_no_times(
        self,
        collect_run: Callable[..., Any],
        collecting: str,
        uncollected: UncollectedRepository
    ) -> None:
        collect_run(
            items=[
                {
                    'id': 'gcal-2',
                    'summary': 'Board Retreat',
                    'start': {'date': '2026-09-12'},
                    'end': {'date': '2026-09-13'}
                }
            ]
        )

        stored = uncollected.list_all(run_id=collecting)[0]

        assert stored.reason == UNCOLLECTED_ALL_DAY
        assert stored.title == 'Board Retreat'
        assert stored.date == '2026-09-12'
        assert stored.calendar_start is None
        assert stored.calendar_end is None

    def test_an_untitled_event_is_recorded_with_no_title(
        self,
        collect_run: Callable[..., Any],
        collecting: str,
        uncollected: UncollectedRepository
    ) -> None:
        collect_run(
            items=[
                {
                    'id': 'gcal-2',
                    'start': {'dateTime': '2026-09-03T19:00:00-07:00'},
                    'end': {'dateTime': '2026-09-03T21:00:00-07:00'}
                }
            ]
        )

        stored = uncollected.list_all(run_id=collecting)[0]

        assert stored.reason == UNCOLLECTED_UNTITLED
        assert stored.title is None
        assert stored.date == '2026-09-03'

    def test_a_time_the_calendar_gave_badly_does_not_stop_the_run(
        self,
        collect_run: Callable[..., Any],
        collecting: str,
        uncollected: UncollectedRepository
    ) -> None:
        # This item was never going to become a shift, so refusing the
        # run for the shape of its start would leave nothing to
        # correct.
        collect_run(
            items=[
                an_item(),
                an_item(
                    identifier='gcal-2',
                    summary='CANCELLED: Wheels of Justice',
                    start='next Tuesday'
                )
            ]
        )

        stored = uncollected.list_all(run_id=collecting)[0]

        assert stored.reason == UNCOLLECTED_EXCLUDED
        assert stored.date is None
        assert stored.calendar_start is None

    def test_the_times_are_read_in_the_league_zone(
        self,
        collect_run: Callable[..., Any],
        collecting: str,
        uncollected: UncollectedRepository
    ) -> None:
        # The calendar answers in whatever offset it likes, and the
        # league reads a shift by its own clock.
        collect_run(
            items=[
                an_item(
                    identifier='gcal-2',
                    summary='CANCELED: Wheels of Justice',
                    start='2026-09-04T02:00:00+00:00',
                    end='2026-09-04T04:00:00+00:00'
                )
            ]
        )

        stored = uncollected.list_all(run_id=collecting)[0]

        assert stored.date == '2026-09-03'
        assert stored.calendar_start == '19:00'
        assert stored.calendar_end == '21:00'

    def test_a_second_collection_replaces_them(
        self,
        collect_run: Callable[..., Any],
        collecting: str,
        uncollected: UncollectedRepository
    ) -> None:
        collect_run(
            items=[an_item(identifier='gone', summary='CANCELED: Bout')]
        )
        collect_run(
            items=[an_item(identifier='still', summary='CANCELED: Bout')]
        )

        assert [
            row.id for row in uncollected.list_all(run_id=collecting)
        ] == ['still']

    def test_a_run_that_stopped_records_none_of_them(
        self,
        collect_run: Callable[..., Any],
        collecting: str,
        uncollected: UncollectedRepository
    ) -> None:
        # It is written in the same transaction as the events, so a
        # run with no revision has no answer about its window either.
        with pytest.raises(ValidationError):
            collect_run(
                items=[
                    an_item(),
                    an_item(identifier='gcal-2', summary='CANCELED: Bout')
                ],
                categories={
                    'adult_game': a_category(
                        need_ids=[
                            a_need(offset_start=0, offset_end=-180)
                        ]
                    )
                }
            )

        assert uncollected.list_all(run_id=collecting) == []


class TestAnEventNobodyLookedFor:
    # The one reason no calendar item can carry.  It is the difference
    # between what the configured query strings returned and what the
    # window holds, so only a second read without a query string finds
    # it -- and it is the only group a person may pull into a run.

    @pytest.fixture(name='searched_run')
    def fixture_searched_run(self, runs: RunRepository) -> str:
        """ Return a run on a calendar searched for terms.

            'practices' is searched for two of them, neither the empty
            string, so its window is read a third time and an event the
            searches missed can be told from one they found.
        """
        return runs.create(
            calendar=REPEATING_CALENDAR,
            window_start='2026-09-01',
            window_end='2026-10-01'
        ).id

    @pytest.fixture(name='missed')
    def fixture_missed(
        self,
        collect_run: Callable[..., Any],
        searched_run: str,
        uncollected: UncollectedRepository
    ) -> list:
        """ Return what a run recorded of an event no search found.

            One arrangement, because the two things worth asking about
            it -- that it is there, and that it is complete enough to
            be pulled in -- are two readings of one collection.
        """
        collect_run(
            items=[an_item()],
            run_id=searched_run,
            unsearched=[
                an_item(identifier='gcal-2', summary='Junior Bout')
            ]
        )

        return uncollected.list_all(run_id=searched_run)

    def test_an_event_the_searches_missed_is_recorded(
        self,
        missed: list
    ) -> None:
        assert [(row.id, row.reason) for row in missed] == [
            ('gcal-2', UNCOLLECTED_SEARCH)
        ]

    def test_it_keeps_everything_needed_to_pull_it_in(
        self,
        missed: list
    ) -> None:
        stored = missed[0]

        assert stored.title == 'Junior Bout'
        assert stored.date == '2026-09-03'
        assert stored.calendar_start == '19:00'
        assert stored.calendar_end == '21:00'

    def test_an_event_the_searches_found_is_collected_not_recorded(
        self,
        collect_run: Callable[..., Any],
        searched_run: str,
        events: EventRepository,
        uncollected: UncollectedRepository
    ) -> None:
        collect_run(items=[an_item()], run_id=searched_run, unsearched=[])

        assert len(events.list_all(run_id=searched_run, revision=1)) == 1
        assert uncollected.list_all(run_id=searched_run) == []

    def test_a_missed_event_that_cannot_become_a_shift_says_so_instead(
        self,
        collect_run: Callable[..., Any],
        searched_run: str,
        uncollected: UncollectedRepository
    ) -> None:
        # Nobody looked for it and it could not have been used anyway.
        # The reason a reviewer can act on is the second one, because
        # it is what says the event may not be pulled in.
        collect_run(
            items=[an_item()],
            run_id=searched_run,
            unsearched=[
                an_item(identifier='gcal-2', summary='CANCELED: Junior Bout')
            ]
        )

        stored = uncollected.list_all(run_id=searched_run)

        assert [(row.id, row.reason) for row in stored] == [
            ('gcal-2', UNCOLLECTED_EXCLUDED)
        ]

    def test_a_calendar_read_whole_already_misses_nothing(
        self,
        collect_run: Callable[..., Any],
        collecting: str,
        events: EventRepository,
        uncollected: UncollectedRepository
    ) -> None:
        # 'events' is configured with the empty query string, so its
        # search is the whole window: an event only the query-less read
        # answers with is one that search returned, and it is
        # collected rather than reported as missed.
        collect_run(
            items=[an_item()],
            unsearched=[
                an_item(identifier='gcal-2', summary='Junior Bout')
            ]
        )

        assert len(events.list_all(run_id=collecting, revision=1)) == 2
        assert uncollected.list_all(run_id=collecting) == []
