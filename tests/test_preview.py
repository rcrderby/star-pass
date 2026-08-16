#!/usr/bin/env python3
""" Tests for what sending a revision would create.

    These are the numbers a person decides on before writing to a live
    volunteer system, so each test says what one of them means rather
    than only that it is produced.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
from typing import Callable

# Imports - Local
from star_pass._preview import (
    BLOCKER_ENDS_BEFORE_START,
    BLOCKER_NO_OPPORTUNITY,
    BLOCKER_NO_SLOTS,
    blockers,
    preview
)
from star_pass._records import Event, EventRole, Opportunity


class TestBlockers:
    def test_an_event_that_can_be_sent_blocks_nothing(
        self,
        make_event: Callable[..., Event]
    ) -> None:
        assert blockers(event=make_event()) == ()

    def test_an_event_with_no_role_has_no_opportunity(
        self,
        make_event: Callable[..., Event]
    ) -> None:
        assert blockers(
            event=make_event(category=None, roles=())
        ) == (BLOCKER_NO_OPPORTUNITY,)

    def test_a_shift_ending_before_it_starts_blocks(
        self,
        make_event: Callable[..., Event]
    ) -> None:
        assert blockers(
            event=make_event(shift_start='21:30', shift_end='19:15')
        ) == (BLOCKER_ENDS_BEFORE_START,)

    def test_a_shift_ending_when_it_starts_blocks(
        self,
        make_event: Callable[..., Event]
    ) -> None:
        # Amplify is sent a start and a duration, and a duration of
        # zero is a row it would reject.
        assert blockers(
            event=make_event(shift_start='19:15', shift_end='19:15')
        ) == (BLOCKER_ENDS_BEFORE_START,)

    def test_a_role_wanting_nobody_blocks(
        self,
        make_event: Callable[..., Event]
    ) -> None:
        assert blockers(
            event=make_event(roles=(EventRole(need_id='905196', slots=0),))
        ) == (BLOCKER_NO_SLOTS,)

    def test_every_reason_is_reported_not_only_the_first(
        self,
        make_event: Callable[..., Event]
    ) -> None:
        # A person fixing one and finding another would be back where
        # they started.
        assert blockers(
            event=make_event(
                shift_start='21:30',
                shift_end='19:15',
                roles=(EventRole(need_id='905196', slots=0),)
            )
        ) == (BLOCKER_ENDS_BEFORE_START, BLOCKER_NO_SLOTS)


class TestWhatWouldBeCreated:
    def test_one_event_creates_one_shift(
        self,
        make_event: Callable[..., Event]
    ) -> None:
        assert preview(
            events=[make_event()],
            opportunities={}
        ).will_create == 1

    def test_an_event_creates_a_shift_per_role(
        self,
        make_event: Callable[..., Event]
    ) -> None:
        # A scrimmage wanting both skating and non-skating officials
        # creates two.
        event = make_event(
            roles=(
                EventRole(need_id='905196', slots=4),
                EventRole(need_id='905197', slots=2)
            )
        )

        assert preview(events=[event], opportunities={}).will_create == 2

    def test_two_events_sending_the_same_row_create_one_shift(
        self,
        make_event: Callable[..., Event]
    ) -> None:
        # Counted by identity, never by how many events there are.
        result = preview(
            events=[
                make_event(id='event-1'),
                make_event(id='event-2')
            ],
            opportunities={}
        )

        assert result.will_create == 1
        assert result.repeated_rows == 1

    def test_the_same_hour_under_another_opportunity_is_not_a_repeat(
        self,
        make_event: Callable[..., Event]
    ) -> None:
        result = preview(
            events=[
                make_event(id='event-1'),
                make_event(
                    id='event-2',
                    roles=(EventRole(need_id='905197', slots=2),)
                )
            ],
            opportunities={}
        )

        assert result.will_create == 2
        assert result.repeated_rows == 0

    def test_the_same_start_with_another_end_is_not_a_repeat(
        self,
        make_event: Callable[..., Event]
    ) -> None:
        # Amplify is sent a start and a duration, so two rows starting
        # together and running for different lengths are two shifts.
        result = preview(
            events=[
                make_event(id='event-1', shift_end='21:30'),
                make_event(id='event-2', shift_end='22:30')
            ],
            opportunities={}
        )

        assert result.will_create == 2
        assert result.repeated_rows == 0

    def test_an_event_repeating_on_one_role_still_creates_the_other(
        self,
        make_event: Callable[..., Event]
    ) -> None:
        # Event-level de-duplication would drop both of the second
        # event's shifts, and one of them is a row Amplify does not
        # have yet.
        result = preview(
            events=[
                make_event(id='event-1'),
                make_event(
                    id='event-2',
                    roles=(
                        EventRole(need_id='905196', slots=4),
                        EventRole(need_id='905197', slots=2)
                    )
                )
            ],
            opportunities={}
        )

        assert result.will_create == 2
        assert result.repeated_rows == 1

    def test_a_blocked_event_creates_nothing(
        self,
        make_event: Callable[..., Event]
    ) -> None:
        result = preview(
            events=[
                make_event(id='event-1'),
                make_event(
                    id='event-2',
                    roles=(EventRole(need_id='905197', slots=0),)
                )
            ],
            opportunities={}
        )

        assert result.will_create == 1
        assert result.blocking_events == 1

    def test_an_empty_revision_would_create_nothing(self) -> None:
        result = preview(events=[], opportunities={})

        assert result.will_create == 0
        assert result.rows == ()
        assert result.blockers == ()


class TestTheRowsAPreviewGroups:
    def test_rows_are_grouped_by_opportunity(
        self,
        make_event: Callable[..., Event]
    ) -> None:
        # Several categories share one Amplify listing, so grouping by
        # category would show the same listing twice under two names.
        events = [
            make_event(id='event-1', category='adult_game'),
            make_event(
                id='event-2',
                date='2026-09-04',
                category='junior_game'
            )
        ]

        rows = preview(events=events, opportunities={}).rows

        assert [row.need_id for row in rows] == ['905196']
        assert rows[0].will_create == 2

    def test_a_row_is_labelled_with_its_amplify_title(
        self,
        make_event: Callable[..., Event],
        make_opportunity: Callable[..., Opportunity]
    ) -> None:
        opportunity = make_opportunity()

        rows = preview(
            events=[make_event()],
            opportunities={opportunity.need_id: opportunity}
        ).rows

        assert rows[0].title == 'Adult Scrimmages: Skating Officials'

    def test_an_unresolved_opportunity_has_no_title(
        self,
        make_event: Callable[..., Event]
    ) -> None:
        # The shifts would still be created, so the row belongs; the
        # missing title is what says collection resolved nothing.
        rows = preview(events=[make_event()], opportunities={}).rows

        assert rows[0].need_id == '905196'
        assert rows[0].title is None

    def test_a_row_counts_the_volunteers_wanted(
        self,
        make_event: Callable[..., Event]
    ) -> None:
        events = [
            make_event(id='event-1'),
            make_event(
                id='event-2',
                date='2026-09-04',
                roles=(EventRole(need_id='905196', slots=6),)
            )
        ]

        rows = preview(events=events, opportunities={}).rows

        assert rows[0].slots == 10

    def test_a_row_names_the_days_its_shifts_fall_on(
        self,
        make_event: Callable[..., Event]
    ) -> None:
        events = [
            make_event(id='event-1', date='2026-09-10'),
            make_event(id='event-2', date='2026-09-03'),
            make_event(id='event-3', date='2026-09-07')
        ]

        rows = preview(events=events, opportunities={}).rows

        assert rows[0].first_date == '2026-09-03'
        assert rows[0].last_date == '2026-09-10'

    def test_the_dates_cover_what_would_be_created_only(
        self,
        make_event: Callable[..., Event]
    ) -> None:
        # The later event is blocked, so it is not what is about to
        # arrive and does not stretch the range a reader checks.
        events = [
            make_event(id='event-1', date='2026-09-03'),
            make_event(
                id='event-2',
                date='2026-09-30',
                roles=(EventRole(need_id='905196', slots=0),)
            )
        ]

        rows = preview(events=events, opportunities={}).rows

        assert rows[0].last_date == '2026-09-03'

    def test_an_opportunity_receiving_nothing_has_no_row(
        self,
        make_event: Callable[..., Event],
        make_opportunity: Callable[..., Opportunity]
    ) -> None:
        opportunities = {
            '905196': make_opportunity(need_id='905196'),
            '905197': make_opportunity(need_id='905197')
        }

        rows = preview(
            events=[make_event()],
            opportunities=opportunities
        ).rows

        assert [row.need_id for row in rows] == ['905196']


class TestWhatStopsASend:
    def test_a_blocked_event_is_named_with_its_reason(
        self,
        make_event: Callable[..., Event]
    ) -> None:
        result = preview(
            events=[make_event(id='event-2', category=None, roles=())],
            opportunities={}
        )

        assert [
            (item.event_id, item.reason) for item in result.blockers
        ] == [('event-2', BLOCKER_NO_OPPORTUNITY)]

    def test_an_event_with_two_things_wrong_is_named_twice(
        self,
        make_event: Callable[..., Event]
    ) -> None:
        result = preview(
            events=[
                make_event(
                    shift_start='21:30',
                    shift_end='19:15',
                    roles=(EventRole(need_id='905196', slots=0),)
                )
            ],
            opportunities={}
        )

        assert [item.reason for item in result.blockers] == [
            BLOCKER_ENDS_BEFORE_START,
            BLOCKER_NO_SLOTS
        ]
        assert result.blocking_events == 1

    def test_nothing_blocking_leaves_no_blockers(
        self,
        make_event: Callable[..., Event]
    ) -> None:
        result = preview(events=[make_event()], opportunities={})

        assert result.blockers == ()
        assert result.blocking_events == 0
