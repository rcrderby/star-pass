#!/usr/bin/env python3
""" Tests for what a stored event does not say.

    Nothing here touches a database.  These are pure functions over
    records, so a test builds the records it needs and reads the answer
    back, which is what keeps them usable by the command line client as
    well as by the service.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
from typing import Callable

# Imports - Third-Party
import pytest

# Imports - Local
from star_pass._derived import (
    blocks_the_run,
    capping_maximum,
    repeated,
    shift_length
)
from star_pass._records import Event, EventRole, Opportunity


class TestShiftLength:
    def test_a_shift_is_measured_in_minutes(
        self,
        make_event: Callable[..., Event]
    ) -> None:
        event = make_event(shift_start='19:15', shift_end='21:30')

        assert shift_length(event=event) == 135

    def test_a_shift_within_the_hour_is_measured(
        self,
        make_event: Callable[..., Event]
    ) -> None:
        event = make_event(shift_start='19:15', shift_end='19:45')

        assert shift_length(event=event) == 30

    def test_a_shift_ending_when_it_starts_measures_nothing(
        self,
        make_event: Callable[..., Event]
    ) -> None:
        event = make_event(shift_start='19:15', shift_end='19:15')

        assert shift_length(event=event) == 0

    def test_a_shift_ending_before_it_starts_measures_below_zero(
        self,
        make_event: Callable[..., Event]
    ) -> None:
        # Collection refuses to produce one, but an edit can, and a
        # reader is better served by the number than by an exception
        # raised while a list was being drawn.
        event = make_event(shift_start='21:30', shift_end='19:15')

        assert shift_length(event=event) == -135

    def test_a_time_that_is_not_a_time_is_refused(
        self,
        make_event: Callable[..., Event]
    ) -> None:
        event = make_event(shift_end='half past nine')

        with pytest.raises(ValueError):
            shift_length(event=event)


class TestCappingMaximum:
    def test_a_shift_the_maximum_shortened_names_it(
        self,
        make_event: Callable[..., Event],
        make_opportunity: Callable[..., Opportunity]
    ) -> None:
        # Two calendar hours, and offsets adding a quarter of an hour
        # in total, so an uncapped shift would run 135 minutes. The
        # maximum allows 120, which is why the stored shift ends at
        # 21:15 rather than at the 21:30 the calendar and the offsets
        # would have given it.
        event = make_event(
            calendar_start='19:00',
            calendar_end='21:00',
            shift_start='19:15',
            shift_end='21:15'
        )
        opportunity = make_opportunity(
            max_length=120,
            offset_start=15,
            offset_end=30
        )

        assert capping_maximum(
            event=event,
            opportunities={opportunity.need_id: opportunity}
        ) == 120

    def test_a_shift_inside_the_maximum_was_not_capped(
        self,
        make_event: Callable[..., Event],
        make_opportunity: Callable[..., Opportunity]
    ) -> None:
        event = make_event(
            calendar_start='19:00',
            calendar_end='21:00'
        )
        opportunity = make_opportunity(
            max_length=240,
            offset_start=15,
            offset_end=30
        )

        assert capping_maximum(
            event=event,
            opportunities={opportunity.need_id: opportunity}
        ) is None

    def test_a_shift_exactly_at_the_maximum_was_not_capped(
        self,
        make_event: Callable[..., Event],
        make_opportunity: Callable[..., Opportunity]
    ) -> None:
        # 120 calendar minutes and 15 more from the offsets is 135,
        # which the maximum allows in full, so nothing was taken off
        # it and there is no cap to name.
        event = make_event(
            calendar_start='19:00',
            calendar_end='21:00'
        )
        opportunity = make_opportunity(
            max_length=135,
            offset_start=15,
            offset_end=30
        )

        assert capping_maximum(
            event=event,
            opportunities={opportunity.need_id: opportunity}
        ) is None

    def test_an_opportunity_with_no_maximum_caps_nothing(
        self,
        make_event: Callable[..., Event],
        make_opportunity: Callable[..., Opportunity]
    ) -> None:
        opportunity = make_opportunity(max_length=None)

        assert capping_maximum(
            event=make_event(),
            opportunities={opportunity.need_id: opportunity}
        ) is None

    def test_the_smallest_maximum_that_applied_is_the_binding_one(
        self,
        make_event: Callable[..., Event],
        make_opportunity: Callable[..., Opportunity]
    ) -> None:
        # Two roles whose opportunities cap differently.  The data
        # model gives a category's need IDs the same timing today, but
        # nothing enforces it, so the shorter is the one reported.
        event = make_event(
            calendar_start='19:00',
            calendar_end='21:00',
            roles=(
                EventRole(need_id='905196', slots=4),
                EventRole(need_id='905197', slots=2)
            )
        )
        opportunities = {
            '905196': make_opportunity(need_id='905196', max_length=120),
            '905197': make_opportunity(need_id='905197', max_length=90)
        }

        assert capping_maximum(
            event=event,
            opportunities=opportunities
        ) == 90

    def test_only_the_maxima_that_applied_are_considered(
        self,
        make_event: Callable[..., Event],
        make_opportunity: Callable[..., Opportunity]
    ) -> None:
        # The smaller maximum belongs to an opportunity this event has
        # no role under, so it decided nothing about this shift.
        event = make_event(calendar_start='19:00', calendar_end='21:00')
        opportunities = {
            '905196': make_opportunity(need_id='905196', max_length=120),
            '905197': make_opportunity(need_id='905197', max_length=30)
        }

        assert capping_maximum(
            event=event,
            opportunities=opportunities
        ) == 120

    def test_an_unreadable_opportunity_caps_nothing(
        self,
        make_event: Callable[..., Event]
    ) -> None:
        # An opportunity that is not stored cannot be shown to have
        # capped anything, so its role is passed over rather than
        # raising while a list was being drawn.
        assert capping_maximum(
            event=make_event(),
            opportunities={}
        ) is None

    def test_an_event_with_no_role_was_capped_by_nothing(
        self,
        make_event: Callable[..., Event],
        make_opportunity: Callable[..., Opportunity]
    ) -> None:
        opportunity = make_opportunity(max_length=30)

        assert capping_maximum(
            event=make_event(roles=()),
            opportunities={opportunity.need_id: opportunity}
        ) is None


class TestRepeated:
    def test_two_events_creating_the_same_shift_repeat(
        self,
        make_event: Callable[..., Event]
    ) -> None:
        first = make_event(id='event-1')
        second = make_event(id='event-2')

        assert repeated(events=[first, second]) == {'event-2': 'event-1'}

    def test_the_earlier_event_is_the_one_named(
        self,
        make_event: Callable[..., Event]
    ) -> None:
        # A reader is pointed at the one already in the list, not at
        # the one they are looking at.
        events = [
            make_event(id='event-1'),
            make_event(id='event-2'),
            make_event(id='event-3')
        ]

        assert repeated(events=events) == {
            'event-2': 'event-1',
            'event-3': 'event-1'
        }

    def test_an_event_repeating_nothing_is_absent(
        self,
        make_event: Callable[..., Event]
    ) -> None:
        assert repeated(events=[make_event()]) == {}

    def test_the_same_time_under_another_opportunity_is_not_a_repeat(
        self,
        make_event: Callable[..., Event]
    ) -> None:
        # Two shifts at one hour under different needs are two
        # different Amplify rows, and both belong.
        first = make_event(id='event-1')
        second = make_event(
            id='event-2',
            roles=(EventRole(need_id='905197', slots=2),)
        )

        assert repeated(events=[first, second]) == {}

    def test_another_date_is_not_a_repeat(
        self,
        make_event: Callable[..., Event]
    ) -> None:
        first = make_event(id='event-1', date='2026-09-03')
        second = make_event(id='event-2', date='2026-09-04')

        assert repeated(events=[first, second]) == {}

    def test_another_start_is_not_a_repeat(
        self,
        make_event: Callable[..., Event]
    ) -> None:
        first = make_event(id='event-1', shift_start='19:15')
        second = make_event(id='event-2', shift_start='19:45')

        assert repeated(events=[first, second]) == {}

    def test_another_end_is_not_a_repeat(
        self,
        make_event: Callable[..., Event]
    ) -> None:
        first = make_event(id='event-1', shift_end='21:30')
        second = make_event(id='event-2', shift_end='22:30')

        assert repeated(events=[first, second]) == {}

    def test_a_different_title_still_repeats(
        self,
        make_event: Callable[..., Event]
    ) -> None:
        # What reaches Amplify is the need, the date and the times.
        # Two events named differently still send the same row.
        first = make_event(id='event-1', title='Adult Scrimmages')
        second = make_event(id='event-2', title='Adult Practice')

        assert repeated(events=[first, second]) == {'event-2': 'event-1'}

    def test_a_different_slot_count_still_repeats(
        self,
        make_event: Callable[..., Event]
    ) -> None:
        first = make_event(
            id='event-1',
            roles=(EventRole(need_id='905196', slots=4),)
        )
        second = make_event(
            id='event-2',
            roles=(EventRole(need_id='905196', slots=8),)
        )

        assert repeated(events=[first, second]) == {'event-2': 'event-1'}

    def test_an_event_repeating_on_two_roles_names_the_first(
        self,
        make_event: Callable[..., Event]
    ) -> None:
        both = (
            EventRole(need_id='905196', slots=4),
            EventRole(need_id='905197', slots=2)
        )
        first = make_event(id='event-1', roles=both)
        second = make_event(id='event-2', roles=both)

        assert repeated(events=[first, second]) == {'event-2': 'event-1'}

    def test_an_event_repeating_two_others_names_the_earlier(
        self,
        make_event: Callable[..., Event]
    ) -> None:
        # The third event collides with the first on one role and with
        # the second on the other, so which of them it is said to
        # repeat is a choice, and the earlier one is the answer.
        first = make_event(
            id='event-1',
            roles=(EventRole(need_id='905196', slots=4),)
        )
        second = make_event(
            id='event-2',
            roles=(EventRole(need_id='905197', slots=2),)
        )
        third = make_event(
            id='event-3',
            roles=(
                EventRole(need_id='905196', slots=4),
                EventRole(need_id='905197', slots=2)
            )
        )

        assert repeated(events=[first, second, third]) == {
            'event-3': 'event-1'
        }

    def test_nothing_repeats_in_an_empty_revision(self) -> None:
        assert repeated(events=[]) == {}


class TestBlocksTheRun:
    def test_an_event_with_no_role_blocks_the_run(
        self,
        make_event: Callable[..., Event]
    ) -> None:
        assert blocks_the_run(event=make_event(category=None, roles=()))

    def test_a_matched_event_with_no_need_id_still_blocks(
        self,
        make_event: Callable[..., Event]
    ) -> None:
        # A category that resolved to no need ID leaves the same
        # absence as a title that matched nothing.
        assert blocks_the_run(event=make_event(category='default', roles=()))

    def test_an_event_with_a_role_does_not_block(
        self,
        make_event: Callable[..., Event]
    ) -> None:
        assert not blocks_the_run(event=make_event())
