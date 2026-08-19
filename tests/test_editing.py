#!/usr/bin/env python3
""" Editing the events in a run's current revision.

    Nothing here touches the database: 'apply' answers with the events
    as they would be and the lines to log, and a caller decides when
    that becomes durable.  The shift data model is replaced, because
    what a category asks for is an input to an edit and not something
    these tests are about.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
from typing import Any, Callable, Dict, List, Optional, Tuple

# Imports - Third-Party
import pytest

# Imports - Local
from conftest import (
    a_category,
    a_need,
    OTHER_SHIFT_NEED_ID as OTHER_NEED_ID,
    SHIFT_CALENDAR as CALENDAR,
    SHIFT_NEED_ID as NEED_ID
)
from star_pass._editing import (
    apply,
    OP_NUDGE,
    OP_REMOVE,
    OP_RESET_SLOTS,
    OP_SET_CATEGORY,
    OP_SET_END,
    OP_SET_SLOTS,
    OP_SET_START,
    OP_UNDO,
    OPERATIONS,
    Operation
)
from star_pass._event_edits import was_edited
from star_pass._exceptions import ValidationError
from star_pass._helpers import Helpers
from star_pass._records import Event, EventRole, Match, Opportunity


def an_event(
    *,
    identifier: str = 'gcal-1',
    title: str = 'Wheels of Justice vs Rose City',
    shift_start: str = '19:15',
    shift_end: str = '21:30',
    category: Optional[str] = 'adult_game',
    roles: Tuple[EventRole, ...] = (EventRole(need_id=NEED_ID, slots=12),)
) -> Event:
    # The calendar times are 19:00 to 21:00, so the default offsets
    # (+15, +30) reproduce the shift times above.  A test that changes
    # the times can therefore say what an undo must restore.
    return Event(
        id=identifier,
        title=title,
        date='2026-09-03',
        calendar_start='19:00',
        calendar_end='21:00',
        shift_start=shift_start,
        shift_end=shift_end,
        category=category,
        match=Match(kind='MATCH_KIND_KEYWORD', keyword='wheels'),
        roles=roles
    )


def an_opportunity(
    need_id: str = NEED_ID,
    default_slots: int = 12,
    title: str = 'Adult Games - NSOs'
) -> Opportunity:
    return Opportunity(
        need_id=need_id,
        title=title,
        url=f'https://example.test/needs/{need_id}',
        max_length=165,
        offset_start=15,
        offset_end=30,
        default_slots=default_slots
    )


@pytest.fixture(name='edit')
def fixture_edit(shift_model: Callable[..., None]) -> Callable[..., Any]:
    """ Return a way to apply operations to a set of events. """

    def run(
        operations: List[Operation],
        events: Optional[List[Event]] = None,
        opportunities: Optional[List[Opportunity]] = None,
        categories: Optional[Dict[str, Any]] = None
    ) -> Any:
        shift_model(
            categories=categories
            if categories is not None
            else {'adult_game': a_category(need_ids=[a_need()])},
            calendars=(CALENDAR,)
        )

        return apply(
            operations=operations,
            events=events if events is not None else [an_event()],
            opportunities=(
                opportunities
                if opportunities is not None
                else [an_opportunity()]
            ),
            calendar=CALENDAR
        )

    return run


@pytest.fixture(name='ask_if_edited')
def fixture_ask_if_edited(
    shift_model: Callable[..., None]
) -> Callable[..., bool]:
    """ Return a way to ask whether an event has been edited. """

    def ask(
        event: Event,
        categories: Optional[Dict[str, Any]] = None
    ) -> bool:
        shift_model(
            categories=categories
            if categories is not None
            else {'adult_game': a_category(need_ids=[a_need()])},
            calendars=(CALENDAR,)
        )

        return was_edited(
            event=event,
            calendar=CALENDAR,
            helpers=Helpers()
        )

    return ask


class TestSettingTheShiftTimes:
    def test_a_start_moves_only_the_start(self, edit):
        result = edit([
            Operation(op=OP_SET_START, event_ids=('gcal-1',), time='18:45')
        ])

        assert result.events[0].shift_start == '18:45'
        assert result.events[0].shift_end == '21:30'

    def test_an_end_moves_only_the_end(self, edit):
        result = edit([
            Operation(op=OP_SET_END, event_ids=('gcal-1',), time='22:00')
        ])

        assert result.events[0].shift_start == '19:15'
        assert result.events[0].shift_end == '22:00'

    def test_the_calendar_times_do_not_move(self, edit):
        # They are what the calendar said, which is what an undo reads.
        result = edit([
            Operation(op=OP_SET_START, event_ids=('gcal-1',), time='18:45')
        ])

        assert result.events[0].calendar_start == '19:00'
        assert result.events[0].calendar_end == '21:00'

    def test_a_maximum_does_not_pull_a_chosen_end_back(self, edit):
        # The maximum shortens what the offsets produced.  A person
        # setting a time has overridden that, and silently shortening
        # it would read as the edit not having worked.
        result = edit([
            Operation(op=OP_SET_END, event_ids=('gcal-1',), time='23:30')
        ])

        assert result.events[0].shift_end == '23:30'

    def test_an_end_no_later_than_the_start_is_refused(self, edit):
        with pytest.raises(ValidationError) as error:
            edit([
                Operation(
                    op=OP_SET_END,
                    event_ids=('gcal-1',),
                    time='19:15'
                )
            ])

        assert 'ends no later than it starts' in str(error.value)

    def test_a_time_that_is_not_a_time_is_refused(self, edit):
        with pytest.raises(ValidationError) as error:
            edit([
                Operation(
                    op=OP_SET_START,
                    event_ids=('gcal-1',),
                    time='half past six'
                )
            ])

        assert 'HH:MM' in str(error.value)

    def test_a_missing_time_names_the_field(self, edit):
        with pytest.raises(ValidationError) as error:
            edit([Operation(op=OP_SET_START, event_ids=('gcal-1',))])

        assert 'needs a "time"' in str(error.value)


class TestNudging:
    def test_both_times_move_together(self, edit):
        result = edit([
            Operation(op=OP_NUDGE, event_ids=('gcal-1',), minutes=-15)
        ])

        assert result.events[0].shift_start == '19:00'
        assert result.events[0].shift_end == '21:15'

    def test_a_nudge_later_moves_later(self, edit):
        result = edit([
            Operation(op=OP_NUDGE, event_ids=('gcal-1',), minutes=15)
        ])

        assert result.events[0].shift_start == '19:30'
        assert result.events[0].shift_end == '21:45'

    def test_a_nudge_out_of_the_day_is_refused(self, edit):
        with pytest.raises(ValidationError) as error:
            edit([
                Operation(
                    op=OP_NUDGE,
                    event_ids=('gcal-1',),
                    minutes=180
                )
            ])

        assert 'cannot cross midnight' in str(error.value)

    def test_a_nudge_before_the_start_of_the_day_is_refused(self, edit):
        with pytest.raises(ValidationError) as error:
            edit([
                Operation(
                    op=OP_NUDGE,
                    event_ids=('gcal-1',),
                    minutes=-1200
                )
            ])

        assert 'would leave its day' in str(error.value)


class TestSettingSlots:
    def test_the_named_role_changes_and_is_marked_edited(self, edit):
        result = edit([
            Operation(
                op=OP_SET_SLOTS,
                event_ids=('gcal-1',),
                need_id=NEED_ID,
                slots=4
            )
        ])

        assert result.events[0].roles == (
            EventRole(need_id=NEED_ID, slots=4, edited=True),
        )

    def test_the_other_roles_are_left_alone(self, edit):
        event = an_event(
            roles=(
                EventRole(need_id=NEED_ID, slots=12),
                EventRole(need_id=OTHER_NEED_ID, slots=8)
            )
        )

        result = edit(
            [
                Operation(
                    op=OP_SET_SLOTS,
                    event_ids=('gcal-1',),
                    need_id=NEED_ID,
                    slots=4
                )
            ],
            events=[event]
        )

        assert result.events[0].roles[1] == EventRole(
            need_id=OTHER_NEED_ID,
            slots=8
        )

    def test_a_role_the_event_does_not_serve_is_refused(self, edit):
        with pytest.raises(ValidationError) as error:
            edit([
                Operation(
                    op=OP_SET_SLOTS,
                    event_ids=('gcal-1',),
                    need_id='000000',
                    slots=4
                )
            ])

        assert 'does not create a shift under need 000000' in str(
            error.value
        )

    def test_a_negative_number_is_refused(self, edit):
        with pytest.raises(ValidationError) as error:
            edit([
                Operation(
                    op=OP_SET_SLOTS,
                    event_ids=('gcal-1',),
                    need_id=NEED_ID,
                    slots=-1
                )
            ])

        assert 'Ask for none or more' in str(error.value)

    def test_none_wanted_is_allowed(self, edit):
        # Zero is a real answer: a shift nobody is wanted for is one
        # the preview reports as blocked, not one an edit refuses.
        result = edit([
            Operation(
                op=OP_SET_SLOTS,
                event_ids=('gcal-1',),
                need_id=NEED_ID,
                slots=0
            )
        ])

        assert result.events[0].roles[0].slots == 0


class TestResettingSlots:
    def test_the_run_s_own_default_is_what_comes_back(self, edit):
        # The run's opportunity, not today's data model: a run records
        # what the opportunity wanted when it was collected.
        edited = an_event(
            roles=(EventRole(need_id=NEED_ID, slots=4, edited=True),)
        )

        result = edit(
            [Operation(op=OP_RESET_SLOTS, event_ids=('gcal-1',))],
            events=[edited],
            opportunities=[an_opportunity(default_slots=9)]
        )

        assert result.events[0].roles == (
            EventRole(need_id=NEED_ID, slots=9, edited=False),
        )

    def test_a_role_with_no_opportunity_is_refused(self, edit):
        stray = an_event(
            roles=(EventRole(need_id='000000', slots=4, edited=True),)
        )

        with pytest.raises(ValidationError) as error:
            edit(
                [Operation(op=OP_RESET_SLOTS, event_ids=('gcal-1',))],
                events=[stray]
            )

        assert 'no usual number of volunteers' in str(error.value)


class TestSettingTheCategory:
    def test_the_roles_come_from_the_new_category(self, edit):
        result = edit(
            [
                Operation(
                    op=OP_SET_CATEGORY,
                    event_ids=('gcal-1',),
                    category='junior_game'
                )
            ],
            categories={
                'adult_game': a_category(need_ids=[a_need()]),
                'junior_game': a_category(
                    need_ids=[a_need(identifier=OTHER_NEED_ID, slots=6)]
                )
            }
        )

        assert result.events[0].category == 'junior_game'
        assert result.events[0].roles == (
            EventRole(need_id=OTHER_NEED_ID, slots=6),
        )

    def test_the_times_are_worked_out_again(self, edit):
        # The new category's offsets apply to the calendar times, so a
        # category with no offsets leaves the shift on the calendar's
        # own hours.
        result = edit(
            [
                Operation(
                    op=OP_SET_CATEGORY,
                    event_ids=('gcal-1',),
                    category='junior_game'
                )
            ],
            categories={
                'adult_game': a_category(need_ids=[a_need()]),
                'junior_game': a_category(
                    need_ids=[
                        a_need(offset_start=0, offset_end=0, max_length=None)
                    ]
                )
            }
        )

        assert result.events[0].shift_start == '19:00'
        assert result.events[0].shift_end == '21:00'

    def test_the_match_is_dropped(self, edit):
        # Nothing matched: somebody decided.  A run that recorded a
        # match here would claim the model did work it did not do.
        result = edit(
            [
                Operation(
                    op=OP_SET_CATEGORY,
                    event_ids=('gcal-1',),
                    category='junior_game'
                )
            ],
            categories={
                'adult_game': a_category(need_ids=[a_need()]),
                'junior_game': a_category(need_ids=[a_need()])
            }
        )

        assert result.events[0].match is None

    def test_a_category_the_calendar_does_not_define_is_refused(self, edit):
        with pytest.raises(ValidationError) as error:
            edit([
                Operation(
                    op=OP_SET_CATEGORY,
                    event_ids=('gcal-1',),
                    category='not_a_category'
                )
            ])

        assert 'no "not_a_category" category' in str(error.value)


class TestUndo:
    def test_the_times_go_back_to_what_the_category_gives(self, edit):
        moved = an_event(shift_start='08:00', shift_end='09:00')

        result = edit(
            [Operation(op=OP_UNDO, event_ids=('gcal-1',))],
            events=[moved]
        )

        assert result.events[0].shift_start == '19:15'
        assert result.events[0].shift_end == '21:30'

    def test_the_slots_go_back_to_what_the_category_asks(self, edit):
        edited = an_event(
            roles=(EventRole(need_id=NEED_ID, slots=4, edited=True),)
        )

        result = edit(
            [Operation(op=OP_UNDO, event_ids=('gcal-1',))],
            events=[edited]
        )

        assert result.events[0].roles == (
            EventRole(need_id=NEED_ID, slots=12, edited=False),
        )

    def test_an_undo_after_an_edit_in_the_same_call_undoes_it(self, edit):
        # Operations are applied in order, each seeing what the one
        # before produced.
        result = edit([
            Operation(op=OP_SET_START, event_ids=('gcal-1',), time='08:00'),
            Operation(op=OP_UNDO, event_ids=('gcal-1',))
        ])

        assert result.events[0].shift_start == '19:15'


class TestRemoving:
    def test_the_event_leaves_the_revision(self, edit):
        result = edit([Operation(op=OP_REMOVE, event_ids=('gcal-1',))])

        assert result.events == ()
        assert result.removed == ('gcal-1',)

    def test_the_others_stay_in_their_order(self, edit):
        events = [
            an_event(identifier='gcal-1'),
            an_event(identifier='gcal-2', title='Axles of Evil'),
            an_event(identifier='gcal-3', title='Break Neck Betties')
        ]

        result = edit(
            [Operation(op=OP_REMOVE, event_ids=('gcal-2',))],
            events=events
        )

        assert [event.id for event in result.events] == [
            'gcal-1',
            'gcal-3'
        ]

    def test_an_operation_naming_a_removed_event_is_refused(self, edit):
        with pytest.raises(ValidationError) as error:
            edit([
                Operation(op=OP_REMOVE, event_ids=('gcal-1',)),
                Operation(
                    op=OP_SET_START,
                    event_ids=('gcal-1',),
                    time='18:00'
                )
            ])

        assert 'no longer holds gcal-1' in str(error.value)


class TestWhatIsRefused:
    def test_an_unknown_operation_names_the_ones_there_are(self, edit):
        with pytest.raises(ValidationError) as error:
            edit([Operation(op='set_colour', event_ids=('gcal-1',))])

        message = str(error.value)
        assert 'set_colour' in message
        for operation in OPERATIONS:
            assert operation in message

    def test_an_operation_naming_no_event_is_refused(self, edit):
        with pytest.raises(ValidationError) as error:
            edit([Operation(op=OP_UNDO, event_ids=())])

        assert 'at least one event' in str(error.value)

    def test_an_event_the_revision_never_held_is_refused(self, edit):
        with pytest.raises(ValidationError) as error:
            edit([Operation(op=OP_UNDO, event_ids=('gcal-9',))])

        assert 'gcal-9' in str(error.value)

    def test_a_call_with_no_operations_is_refused(self, edit):
        with pytest.raises(ValidationError) as error:
            edit([])

        assert 'at least one operation' in str(error.value)

    def test_a_refused_operation_leaves_the_earlier_ones_unapplied(
        self, edit
    ):
        # The call is applied whole or not at all: a bulk action that
        # would break one row of thirty leaves all thirty alone.
        events = [
            an_event(identifier='gcal-1'),
            an_event(identifier='gcal-2', title='Axles of Evil')
        ]

        with pytest.raises(ValidationError):
            edit(
                [
                    Operation(
                        op=OP_SET_START,
                        event_ids=('gcal-1',),
                        time='18:00'
                    ),
                    Operation(
                        op=OP_SET_END,
                        event_ids=('gcal-2',),
                        time='00:30'
                    )
                ],
                events=events
            )

        # Nothing was written, so the caller's own events are untouched.
        assert events[0].shift_start == '19:15'


class TestWhatIsLogged:
    def test_one_entry_per_operation(self, edit):
        result = edit([
            Operation(op=OP_SET_START, event_ids=('gcal-1',), time='18:45'),
            Operation(op=OP_NUDGE, event_ids=('gcal-1',), minutes=15)
        ])

        assert len(result.entries) == 2

    def test_one_event_is_named(self, edit):
        result = edit([
            Operation(op=OP_SET_START, event_ids=('gcal-1',), time='18:45')
        ])

        assert result.entries[0] == (
            'Set the shift start of "Wheels of Justice vs Rose City" '
            'to 18:45.'
        )

    def test_a_selection_is_counted(self, edit):
        events = [
            an_event(identifier='gcal-1'),
            an_event(identifier='gcal-2', title='Axles of Evil')
        ]

        result = edit(
            [
                Operation(
                    op=OP_NUDGE,
                    event_ids=('gcal-1', 'gcal-2'),
                    minutes=-15
                )
            ],
            events=events
        )

        assert result.entries[0] == 'Moved 2 events 15 minutes earlier.'

    def test_slots_are_logged_against_the_opportunity_title(self, edit):
        result = edit([
            Operation(
                op=OP_SET_SLOTS,
                event_ids=('gcal-1',),
                need_id=NEED_ID,
                slots=4
            )
        ])

        assert '"Adult Games - NSOs"' in result.entries[0]


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
            an_event(roles=(EventRole(need_id=NEED_ID, slots=6),))
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
