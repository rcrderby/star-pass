#!/usr/bin/env python3
""" The event a run stores, built once for both the things that store one.

    A collection builds one of these per event its window held, and
    pulling an event in by hand builds one from a stored row.  What
    each of those does with the result is pinned in 'tests/collecting'
    and 'test_adding.py'; these tests ask what the builder itself
    answers, including the two questions neither caller can put to it.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
from datetime import datetime
from typing import Any, Callable

# Imports - Third-Party
import pytest

# Imports - Local
from star_pass._building import event_from
from star_pass._helpers import CategoryMatch, Helpers

# Constants
# A title the "events" calendar's model matches, and one it does not.
MATCHED_TITLE = 'Petals Scrimmage'
UNMATCHED_TITLE = 'Quilting Circle Meetup'

# An evening event that runs into the following day, which only an
# event serving no opportunity can be: one that creates a shift is
# refused for crossing midnight.
LATE_START = datetime(2026, 9, 11, 23, 0)
LATE_END = datetime(2026, 9, 12, 1, 0)


@pytest.fixture(name='matched')
def fixture_matched() -> Callable[[str], CategoryMatch]:
    """ Return a way to match a title the way a collection does. """

    def match(title: str) -> CategoryMatch:
        """ Return the category the title reaches. """
        return Helpers().match_shift_info(
            gcal_name='events',
            need_name=title
        )

    return match


@pytest.fixture(name='built')
def fixture_built(
    matched: Callable[[str], CategoryMatch]
) -> Callable[..., Any]:
    """ Return a way to build one event from what a calendar said. """

    def build(
        title: str = MATCHED_TITLE,
        start: datetime = datetime(2026, 9, 11, 18, 0),
        end: datetime = datetime(2026, 9, 11, 19, 0),
        **overrides: Any
    ) -> Any:
        """ Build the event, overriding what the test cares about. """
        return event_from(
            identifier='gcal-1',
            title=title,
            start=start,
            end=end,
            matched=matched(title),
            **overrides
        )

    return build


class TestTheDayAnEventIsOn:
    def test_the_date_is_the_day_the_event_starts(
        self,
        built: Callable[..., Any]
    ) -> None:
        # Not the day it ends.  The two are the same for every event
        # that creates a shift, because one running past midnight is
        # refused -- so an event serving no opportunity is the only
        # thing that can tell these apart, and it is stored rather
        # than dropped.
        event = built(
            title=UNMATCHED_TITLE,
            start=LATE_START,
            end=LATE_END
        )

        assert event.date == '2026-09-11'


class TestAnEventServingNoOpportunity:
    def test_it_keeps_the_calendar_times_as_its_shift_times(
        self,
        built: Callable[..., Any]
    ) -> None:
        # There are no offsets to apply, and storing nothing would
        # leave a row the reviewer cannot read. It blocks the run for
        # having no role at all, which is what says it needs looking
        # at.
        event = built(title=UNMATCHED_TITLE)

        assert (event.shift_start, event.shift_end) == ('18:00', '19:00')
        assert event.roles == ()

    def test_it_records_that_nothing_matched(
        self,
        built: Callable[..., Any]
    ) -> None:
        event = built(title=UNMATCHED_TITLE)

        assert event.category is None
        assert event.collected_category is None
        assert event.match is None


class TestAnEventTheModelMatched:
    def test_the_offsets_move_the_shift_times(
        self,
        built: Callable[..., Any]
    ) -> None:
        event = built()

        assert (event.calendar_start, event.calendar_end) == (
            '18:00',
            '19:00'
        )
        assert (event.shift_start, event.shift_end) == ('17:45', '19:30')

    def test_it_records_which_category_it_reached_and_how(
        self,
        built: Callable[..., Any]
    ) -> None:
        # A run records the match it actually made, rather than the
        # one the data model would make today.
        event = built()

        assert event.category == 'junior_game_petals'
        assert event.match is not None

    def test_it_records_the_category_as_what_the_collection_matched(
        self,
        built: Callable[..., Any]
    ) -> None:
        # Where an undo puts the row back to, which is the one thing
        # about a collected event that cannot be worked out again:
        # the data model can change between the day a run is collected
        # and the day it is reviewed.
        event = built()

        assert event.collected_category == 'junior_game_petals'


class TestWhoPutItThere:
    def test_a_collected_event_is_not_marked_as_added_by_hand(
        self,
        built: Callable[..., Any]
    ) -> None:
        assert built().added_by_hand is False

    def test_an_event_pulled_in_by_hand_says_so(
        self,
        built: Callable[..., Any]
    ) -> None:
        assert built(added_by_hand=True).added_by_hand is True
