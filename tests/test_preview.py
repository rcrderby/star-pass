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

# Constants
# The row the default event would create, which is what a test saying
# "Amplify already has it" arranges.
IDENTITY = ('905196', '2026-09-03', '19:15', '21:30')


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
            opportunities={},
            existing=set()
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

        assert preview(
            events=[event],
            opportunities={},
            existing=set()
        ).will_create == 2

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
            opportunities={},
            existing=set()
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
            opportunities={},
            existing=set()
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
            opportunities={},
            existing=set()
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
            opportunities={},
            existing=set()
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
            opportunities={},
            existing=set()
        )

        assert result.will_create == 1
        assert result.blocking_events == 1

    def test_an_empty_revision_would_create_nothing(self) -> None:
        result = preview(events=[], opportunities={}, existing=set())

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

        rows = preview(
            events=events,
            opportunities={},
            existing=set()
        ).rows

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
            opportunities={opportunity.need_id: opportunity},
            existing=set()
        ).rows

        assert rows[0].title == 'Adult Scrimmages: Skating Officials'

    def test_rows_come_back_in_the_order_a_reader_reads_them(
        self,
        make_event: Callable[..., Event],
        make_opportunity: Callable[..., Opportunity]
    ) -> None:
        # The two orders disagree for the real pair: 607934 sorts
        # before 628861, and "Non-Skating Officials" sorts before
        # "Skating Officials".  A row order taken from the need ID
        # would come back the other way round.
        skating = make_opportunity(
            need_id='607934',
            title='Adult Scrimmages: Skating Officials'
        )
        non_skating = make_opportunity(
            need_id='628861',
            title='Adult Scrimmages: Non-Skating Officials'
        )

        rows = preview(
            events=[
                make_event(
                    roles=(
                        EventRole(need_id='607934', slots=4),
                        EventRole(need_id='628861', slots=6)
                    )
                )
            ],
            opportunities={
                skating.need_id: skating,
                non_skating.need_id: non_skating
            },
            existing=set()
        ).rows

        assert [row.title for row in rows] == [
            'Adult Scrimmages: Non-Skating Officials',
            'Adult Scrimmages: Skating Officials'
        ]

    def test_a_row_with_no_title_is_ordered_by_its_need_id(
        self,
        make_event: Callable[..., Event],
        make_opportunity: Callable[..., Opportunity]
    ) -> None:
        # The need ID stands in for the title a client would draw, and
        # the title here is chosen to sort *before* it: an untitled row
        # ordered as an empty string would come first instead, which is
        # what every other pairing of a number and a word would hide.
        titled = make_opportunity(
            need_id='628861',
            title='2026 Playoffs: Non-Skating Officials'
        )

        rows = preview(
            events=[
                make_event(
                    roles=(
                        EventRole(need_id='607934', slots=4),
                        EventRole(need_id='628861', slots=6)
                    )
                )
            ],
            opportunities={titled.need_id: titled},
            existing=set()
        ).rows

        assert [row.need_id for row in rows] == ['628861', '607934']
        assert rows[1].title is None

    def test_two_titles_are_ordered_regardless_of_their_capitals(
        self,
        make_event: Callable[..., Event],
        make_opportunity: Callable[..., Opportunity]
    ) -> None:
        # Unfolded, every capital sorts before every lower case letter,
        # so "Zebra" would come before "adult" and a reader scanning
        # the column would find two alphabets in it.
        upper = make_opportunity(need_id='607934', title='Zebra Duty')
        lower = make_opportunity(need_id='628861', title='adult warmup')

        rows = preview(
            events=[
                make_event(
                    roles=(
                        EventRole(need_id='607934', slots=4),
                        EventRole(need_id='628861', slots=6)
                    )
                )
            ],
            opportunities={
                upper.need_id: upper,
                lower.need_id: lower
            },
            existing=set()
        ).rows

        assert [row.title for row in rows] == ['adult warmup', 'Zebra Duty']

    def test_an_unresolved_opportunity_has_no_title(
        self,
        make_event: Callable[..., Event]
    ) -> None:
        # The shifts would still be created, so the row belongs; the
        # missing title is what says collection resolved nothing.
        rows = preview(
            events=[make_event()],
            opportunities={},
            existing=set()
        ).rows

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

        rows = preview(
            events=events,
            opportunities={},
            existing=set()
        ).rows

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

        rows = preview(
            events=events,
            opportunities={},
            existing=set()
        ).rows

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

        rows = preview(
            events=events,
            opportunities={},
            existing=set()
        ).rows

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
            opportunities=opportunities,
            existing=set()
        ).rows

        assert [row.need_id for row in rows] == ['905196']


class TestWhatStopsASend:
    def test_a_blocked_event_is_named_with_its_reason(
        self,
        make_event: Callable[..., Event]
    ) -> None:
        result = preview(
            events=[make_event(id='event-2', category=None, roles=())],
            opportunities={},
            existing=set()
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
            opportunities={},
            existing=set()
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
        result = preview(
            events=[make_event()],
            opportunities={},
            existing=set()
        )

        assert result.blockers == ()
        assert result.blocking_events == 0


class TestWhatAmplifyAlreadyHas:
    def test_a_shift_amplify_has_is_not_counted_as_arriving(
        self,
        make_event: Callable[..., Event]
    ) -> None:
        # The total is what the confirmation restates (D11), so it has
        # to be the number of rows that will arrive.
        result = preview(
            events=[make_event()],
            opportunities={},
            existing={IDENTITY}
        )

        assert result.will_create == 0
        assert result.already_in_amplify == 1

    def test_a_shift_amplify_does_not_have_still_arrives(
        self,
        make_event: Callable[..., Event]
    ) -> None:
        result = preview(
            events=[
                make_event(id='event-1'),
                make_event(id='event-2', date='2026-09-10')
            ],
            opportunities={},
            existing={IDENTITY}
        )

        assert result.will_create == 1
        assert result.already_in_amplify == 1

    def test_a_shift_amplify_has_is_named_not_only_counted(
        self,
        make_event: Callable[..., Event]
    ) -> None:
        # A count says how many rows will not arrive; the reader
        # deciding whether that is right is deciding about days and
        # times (D16).
        result = preview(
            events=[make_event()],
            opportunities={},
            existing={IDENTITY}
        )

        assert [
            (
                shift.need_id,
                shift.date,
                shift.shift_start,
                shift.shift_end
            )
            for shift in result.skipped
        ] == [IDENTITY]

    def test_the_skipped_shifts_are_in_a_settled_order(
        self,
        make_event: Callable[..., Event]
    ) -> None:
        # A list that reordered itself between two readings of one run
        # would look like a change.
        later = ('905196', '2026-09-10', '19:15', '21:30')
        result = preview(
            events=[
                make_event(id='event-1', date='2026-09-10'),
                make_event(id='event-2')
            ],
            opportunities={},
            existing={later, IDENTITY}
        )

        assert [shift.date for shift in result.skipped] == [
            '2026-09-03',
            '2026-09-10'
        ]

    def test_an_existing_shift_of_another_opportunity_is_no_match(
        self,
        make_event: Callable[..., Event]
    ) -> None:
        result = preview(
            events=[make_event()],
            opportunities={},
            existing={('905197', '2026-09-03', '19:15', '21:30')}
        )

        assert result.will_create == 1
        assert result.already_in_amplify == 0

    def test_a_row_reports_what_it_would_create_and_what_exists(
        self,
        make_event: Callable[..., Event]
    ) -> None:
        rows = preview(
            events=[
                make_event(id='event-1'),
                make_event(id='event-2', date='2026-09-10')
            ],
            opportunities={},
            existing={IDENTITY}
        ).rows

        assert rows[0].will_create == 1
        assert rows[0].already_in_amplify == 1

    def test_a_row_counts_only_the_volunteers_it_would_ask_for(
        self,
        make_event: Callable[..., Event]
    ) -> None:
        # A skipped shift exists already, wanting whatever it was
        # created wanting.
        rows = preview(
            events=[
                make_event(id='event-1'),
                make_event(
                    id='event-2',
                    date='2026-09-10',
                    roles=(EventRole(need_id='905196', slots=6),)
                )
            ],
            opportunities={},
            existing={IDENTITY}
        ).rows

        assert rows[0].slots == 6

    def test_an_opportunity_with_nothing_left_to_do_keeps_its_row(
        self,
        make_event: Callable[..., Event]
    ) -> None:
        # The row is what says a send has nothing left to do for this
        # opportunity, which an absent row could not.
        rows = preview(
            events=[make_event()],
            opportunities={},
            existing={IDENTITY}
        ).rows

        assert [row.need_id for row in rows] == ['905196']
        assert rows[0].will_create == 0
        assert rows[0].already_in_amplify == 1

    def test_a_row_creating_nothing_names_no_days(
        self,
        make_event: Callable[..., Event]
    ) -> None:
        # The dates are the days about to arrive in Amplify, and none
        # are.
        rows = preview(
            events=[make_event()],
            opportunities={},
            existing={IDENTITY}
        ).rows

        assert rows[0].first_date is None
        assert rows[0].last_date is None

    def test_a_repeat_of_a_shift_amplify_has_is_still_a_repeat(
        self,
        make_event: Callable[..., Event]
    ) -> None:
        result = preview(
            events=[
                make_event(id='event-1'),
                make_event(id='event-2')
            ],
            opportunities={},
            existing={IDENTITY}
        )

        assert result.repeated_rows == 1
        assert result.already_in_amplify == 1
        assert result.will_create == 0
