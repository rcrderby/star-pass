#!/usr/bin/env python3
""" Reading what an Amplify opportunity already holds.

    This is the answer duplicate safety rests on (D16), so the tests
    are about what happens to a shift the read cannot make sense of as
    much as about the ones it can.  Amplify is reached through
    'Helpers.send_api_request', which the 'amplify_holds' fixture
    replaces: no test here makes a live request.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
from typing import Any, Callable

# Imports - Local
from star_pass._helpers import Helpers
from star_pass._opportunities import (
    need_ids_in,
    read_need,
    shifts_in,
    shifts_in_amplify,
    title_of,
    UNKNOWN_TITLE
)
from star_pass._records import Event, EventRole

# Constants
# The opportunity the default event sends to, and the row it would
# create there.
NEED_ID = '905196'
OTHER_NEED_ID = '905197'
IDENTITY = (NEED_ID, '2026-09-03', '19:15', '21:30')

# What the shared fixture calls an opportunity, so a test asserting a
# title asserts the answer rather than its own arrangement.
NEED_TITLE = f'Need {NEED_ID}'


def held_by(
    helpers: Helpers,
    need_id: str = NEED_ID
) -> set:
    """ Return the shifts one opportunity holds, read from Amplify. """
    return shifts_in(
        need_id=need_id,
        need=read_need(helpers=helpers, need_id=need_id)
    )


class TestReadingAnOpportunity:
    def test_the_title_is_what_amplify_calls_it(
        self,
        amplify_holds: Callable[..., None],
        helpers: Helpers
    ) -> None:
        amplify_holds()

        assert title_of(
            need=read_need(helpers=helpers, need_id=NEED_ID)
        ) == NEED_TITLE

    def test_an_answer_with_no_title_reads_as_unknown(
        self,
        amplify_holds: Callable[..., None],
        helpers: Helpers
    ) -> None:
        # A row labelled with nothing reads as a rendering fault.
        amplify_holds(titled=False)

        assert title_of(
            need=read_need(helpers=helpers, need_id=NEED_ID)
        ) == UNKNOWN_TITLE


class TestTheShiftsAnOpportunityHolds:
    def test_a_shift_is_read_as_the_row_it_is(
        self,
        amplify_holds: Callable[..., None],
        make_amplify_shift: Callable[..., dict],
        helpers: Helpers
    ) -> None:
        amplify_holds({NEED_ID: [make_amplify_shift()]})

        assert held_by(helpers=helpers) == {IDENTITY}

    def test_an_opportunity_holding_nothing_reads_as_empty(
        self,
        amplify_holds: Callable[..., None],
        helpers: Helpers
    ) -> None:
        amplify_holds({NEED_ID: []})

        assert held_by(helpers=helpers) == set()

    def test_an_answer_with_no_shifts_key_reads_as_empty(
        self,
        amplify_holds: Callable[..., None],
        helpers: Helpers
    ) -> None:
        amplify_holds()

        assert held_by(helpers=helpers) == set()

    def test_a_time_with_no_seconds_is_still_read(
        self,
        amplify_holds: Callable[..., None],
        make_amplify_shift: Callable[..., dict],
        helpers: Helpers
    ) -> None:
        # Amplify writes some datetimes without seconds, and a shift
        # this read failed to recognize would be created a second time.
        amplify_holds(
            {
                NEED_ID: [
                    make_amplify_shift(
                        start='2026-09-03 19:15',
                        end='2026-09-03 21:30'
                    )
                ]
            }
        )

        assert held_by(helpers=helpers) == {IDENTITY}

    def test_a_shift_with_no_end_is_read_from_its_duration(
        self,
        amplify_holds: Callable[..., None],
        make_amplify_shift: Callable[..., dict],
        helpers: Helpers
    ) -> None:
        # The duration is the field star-pass sends, so it is the one
        # certainly there.
        amplify_holds(
            {NEED_ID: [make_amplify_shift(end=None, duration=135)]}
        )

        assert held_by(helpers=helpers) == {IDENTITY}

    def test_a_shift_running_past_midnight_matches_nothing(
        self,
        amplify_holds: Callable[..., None],
        make_amplify_shift: Callable[..., dict],
        helpers: Helpers
    ) -> None:
        # Collection refuses to store one, so no run could have created
        # it and nothing this run sends can repeat it.
        amplify_holds(
            {
                NEED_ID: [
                    make_amplify_shift(
                        start='2026-09-03 23:30:00',
                        end='2026-09-04 00:30:00'
                    )
                ]
            }
        )

        assert held_by(helpers=helpers) == set()

    def test_a_shift_whose_times_cannot_be_read_is_reported(
        self,
        amplify_holds: Callable[..., None],
        make_amplify_shift: Callable[..., dict],
        helpers: Helpers,
        caplog: Any
    ) -> None:
        # The one case where a row that does exist is counted as
        # absent, so it is not allowed to pass in silence.
        amplify_holds(
            {
                NEED_ID: [
                    make_amplify_shift(
                        start='the third of September',
                        end=None,
                        duration='a while'
                    )
                ]
            }
        )

        assert held_by(helpers=helpers) == set()
        assert 'cannot' in caplog.text
        assert NEED_ID in caplog.text

    def test_one_unreadable_shift_does_not_hide_the_others(
        self,
        amplify_holds: Callable[..., None],
        make_amplify_shift: Callable[..., dict],
        helpers: Helpers
    ) -> None:
        amplify_holds(
            {
                NEED_ID: [
                    make_amplify_shift(start=None, end=None, duration=None),
                    make_amplify_shift()
                ]
            }
        )

        assert held_by(helpers=helpers) == {IDENTITY}


class TestWhichOpportunitiesAreAsked:
    def test_the_opportunities_the_events_name_are_asked(
        self,
        make_event: Callable[..., Event]
    ) -> None:
        events = [
            make_event(
                roles=(
                    EventRole(need_id=NEED_ID, slots=4),
                    EventRole(need_id=OTHER_NEED_ID, slots=2)
                )
            )
        ]

        assert need_ids_in(events=events) == (NEED_ID, OTHER_NEED_ID)

    def test_an_opportunity_named_twice_is_asked_once(
        self,
        make_event: Callable[..., Event]
    ) -> None:
        events = [
            make_event(id='event-1'),
            make_event(id='event-2', date='2026-09-10')
        ]

        assert need_ids_in(events=events) == (NEED_ID,)

    def test_an_event_with_no_role_names_no_opportunity(
        self,
        make_event: Callable[..., Event]
    ) -> None:
        assert need_ids_in(
            events=[make_event(category=None, roles=())]
        ) == ()

    def test_every_named_opportunity_is_read(
        self,
        amplify_holds: Callable[..., None],
        make_amplify_shift: Callable[..., dict],
        make_event: Callable[..., Event]
    ) -> None:
        # Reading only the first would leave the second's shifts
        # unknown, and a send would create them again.
        amplify_holds(
            {
                NEED_ID: [make_amplify_shift()],
                OTHER_NEED_ID: [make_amplify_shift()]
            }
        )
        events = [
            make_event(
                roles=(
                    EventRole(need_id=NEED_ID, slots=4),
                    EventRole(need_id=OTHER_NEED_ID, slots=2)
                )
            )
        ]

        assert shifts_in_amplify(events=events) == {
            IDENTITY,
            (OTHER_NEED_ID, '2026-09-03', '19:15', '21:30')
        }

    def test_a_revision_with_no_events_asks_nothing(
        self,
        amplify_holds: Callable[..., None]
    ) -> None:
        amplify_holds()

        assert shifts_in_amplify(events=[]) == set()
