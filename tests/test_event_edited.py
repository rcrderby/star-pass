#!/usr/bin/env python3
""" Whether a person has changed an event.

    The same arithmetic 'undo' runs, asked as a question rather than
    applied, which is the 'edited' an event is published with and what
    the review screen offers an undo on.  Beside 'test_editing' rather
    than in it: that module is about what an operation does, this one
    is about a reading of an event, and together they are longer than
    pylint allows a module to be.

    The shift data model is replaced here too, because what a category
    asks for is the input the question is answered from.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
from typing import Any, Callable, Dict, Optional

# Imports - Third-Party
import pytest

# Imports - Local
# 'fixture_edit' is imported rather than defined here: pytest finds a
# fixture by its presence in this module's namespace, and the module
# beside this one applies operations the same way.
# pylint: disable-next=unused-import
from _editing_events import (  # noqa: F401
    a_role,
    a_row_under_another_category,
    an_event,
    fixture_edit,
    install_model,
    two_categories
)
from conftest import (
    a_category,
    a_need,
    OTHER_SHIFT_NEED_ID as OTHER_NEED_ID,
    SHIFT_CALENDAR as CALENDAR,
    SHIFT_NEED_ID as NEED_ID
)
from star_pass._editing import Operation
from star_pass._records import OP_NUDGE
from star_pass._event_edits import was_edited
from star_pass._helpers import Helpers
from star_pass._records import Event


@pytest.fixture(name='ask_if_edited')
def fixture_ask_if_edited(
    shift_model: Callable[..., None]
) -> Callable[..., bool]:
    """ Return a way to ask whether an event has been edited. """

    def ask(
        event: Event,
        categories: Optional[Dict[str, Any]] = None
    ) -> bool:
        install_model(shift_model=shift_model, categories=categories)

        return was_edited(
            event=event,
            calendar=CALENDAR,
            helpers=Helpers()
        )

    return ask


class TestWhetherAnEventHasBeenEdited:
    # The same arithmetic 'undo' runs, asked as a question.  Nothing
    # stored says whether a person changed an event, because the
    # calendar times never move: what says so is that the shift times
    # no longer follow from them.

    def test_an_event_as_collection_left_it_is_not_edited(
        self,
        ask_if_edited
    ):
        # 19:00 to 21:00 with offsets of 15 and 30 is 19:15 to 21:30,
        # which is what the event holds.
        assert ask_if_edited(an_event()) is False

    def test_a_note_the_calendar_wrote_is_not_an_edit(
        self,
        ask_if_edited
    ):
        # The note is truth about the calendar, in the same way and
        # for the same reason the calendar times are (D30).  A row
        # whose note counted as an edit would be a row a reviewer
        # could not have changed and could not put back.
        assert ask_if_edited(
            an_event(calendar_note='Doors at 6 PM, Game at 7 PM')
        ) is False

    def test_a_moved_start_is_edited(self, ask_if_edited):
        assert ask_if_edited(an_event(shift_start='18:45')) is True

    def test_a_moved_end_is_edited(self, ask_if_edited):
        assert ask_if_edited(an_event(shift_end='22:00')) is True

    def test_a_changed_number_of_volunteers_is_edited(
        self,
        ask_if_edited
    ):
        # Undo resets the volunteers as well as the times, so a row
        # whose count somebody set is a row undo would change.
        assert ask_if_edited(
            an_event(roles=(a_role(need_id=NEED_ID, slots=6),))
        ) is True

    def test_an_event_moved_and_moved_back_is_not_edited(
        self,
        edit,
        ask_if_edited
    ):
        # What makes this the right question to ask of the times
        # rather than of a stored flag: the event has been through two
        # operations and is what collection would produce.
        moved = edit([
            Operation(op=OP_NUDGE, event_ids=('gcal-1',), minutes=15),
            Operation(op=OP_NUDGE, event_ids=('gcal-1',), minutes=-15)
        ])

        assert moved.events[0].shift_start == '19:15'
        assert ask_if_edited(moved.events[0]) is False

    def test_an_event_under_no_category_holds_the_calendar_times(
        self,
        ask_if_edited
    ):
        # Nothing says what its shift times should be, so the calendar
        # times and no roles are what collection leaves it as.
        assert ask_if_edited(
            an_event(
                shift_start='19:00',
                shift_end='21:00',
                category=None,
                roles=()
            )
        ) is False

    def test_an_event_under_no_category_that_was_moved_is_edited(
        self,
        ask_if_edited
    ):
        assert ask_if_edited(
            an_event(
                shift_start='18:45',
                shift_end='21:00',
                category=None,
                roles=()
            )
        ) is True

    def test_roles_in_a_different_order_are_not_an_edit(
        self,
        ask_if_edited
    ):
        # Which order the roles are in follows the data model, so a
        # model whose need IDs were reordered after a run was
        # collected would otherwise put an undo on every row in it.
        both = [a_need(), a_need(identifier=OTHER_NEED_ID)]
        reversed_roles = (
            a_role(need_id=OTHER_NEED_ID, slots=12),
            a_role(need_id=NEED_ID, slots=12)
        )

        assert ask_if_edited(
            an_event(roles=reversed_roles),
            categories={'adult_game': a_category(need_ids=both)}
        ) is False

    def test_a_role_the_model_does_not_ask_for_is_edited(
        self,
        ask_if_edited
    ):
        # Sorting is how the order is set aside; it must not set aside
        # which opportunities the event serves.
        assert ask_if_edited(
            an_event(
                roles=(a_role(need_id=OTHER_NEED_ID, slots=12),)
            )
        ) is True

    def test_a_changed_category_is_edited(self, ask_if_edited):
        # The most common edit on the review screen, and the one that
        # said nothing about itself while an event held only the
        # category it is under now.  The times and the volunteers
        # agree with the category it is under, so nothing but the
        # collected category can say the row was changed.
        assert ask_if_edited(
            a_row_under_another_category(),
            categories=two_categories(
                offset_start=0,
                offset_end=0,
                max_length=None
            )
        ) is True

    def test_a_category_given_where_nothing_matched_is_edited(
        self,
        ask_if_edited
    ):
        # Undo would put the row back to unassigned, so it is a row
        # with something to put back and a row offered the control.
        assert ask_if_edited(
            an_event(collected_category=None)
        ) is True

    def test_a_row_still_unassigned_is_not_edited(self, ask_if_edited):
        # Nothing has been done to it: unassigned holding the
        # calendar's own times and no roles is what the collection
        # produced.
        assert ask_if_edited(
            an_event(
                category=None,
                shift_start='19:00',
                shift_end='21:00',
                roles=()
            )
        ) is False

    def test_a_category_the_model_no_longer_holds_is_not_edited(
        self,
        ask_if_edited
    ):
        # Undo would be refused for the same reason this cannot be
        # worked out, and a row said to be edited is a row offered a
        # control that fails.
        assert ask_if_edited(
            an_event(shift_start='18:45'),
            categories={'other_game': a_category(need_ids=[a_need()])}
        ) is False
