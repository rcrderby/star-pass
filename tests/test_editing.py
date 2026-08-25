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
from typing import Any, Callable, Dict, List, Optional

# Imports - Third-Party
import pytest

# Imports - Local
from conftest import (
    a_category,
    a_need,
    an_event as event_record,
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


def a_role(
    need_id: str = NEED_ID,
    slots: int = 12,
    edited: bool = False,
    default_slots: Optional[int] = None
) -> EventRole:
    # The timing every event in this file is written against: the
    # calendar times are 19:00 to 21:00 and the offsets reproduce the
    # 19:15 to 21:30 shift the default event carries.
    return EventRole(
        need_id=need_id,
        slots=slots,
        edited=edited,
        offset_start=15,
        offset_end=30,
        max_length=165,
        default_slots=slots if default_slots is None else default_slots
    )


def an_event(**overrides: Any) -> Event:
    """ Return the event these tests are written against.

        The day, the hours and the rule about what the collection
        matched come from the factory beside every other test's
        events; what is named here is what makes this file's event
        its own -- a title that matched a keyword, and the category
        and role the model these tests install asks for.

        The calendar times are 19:00 to 21:00, so the default offsets
        (+15, +30) reproduce shift times of 19:15 to 21:30.  A test
        that changes the times can therefore say what an undo must
        restore.
    """
    fields: dict = {
        'id': 'gcal-1',
        'title': 'Wheels of Justice vs Rose City',
        'category': 'adult_game',
        'match': Match(kind='MATCH_KIND_KEYWORD', keyword='wheels'),
        'roles': (a_role(),)
    }
    fields.update(overrides)

    return event_record(**fields)


def two_categories(
    offset_start: int = 15,
    offset_end: int = 30,
    max_length: Optional[int] = 165
) -> Dict[str, Any]:
    """ Return a model with the collected category and one more.

        A category change needs somewhere to change to, and every test
        of one wants the same pair: the category the file's event was
        collected under, and a second naming a different opportunity.
        The second's timing is what a test varies, because a category
        that times the event as the first one does cannot show that
        the times were worked out again.
    """
    return {
        'adult_game': a_category(need_ids=[a_need()]),
        'junior_game': a_category(
            need_ids=[
                a_need(
                    identifier=OTHER_NEED_ID,
                    slots=6,
                    offset_start=offset_start,
                    offset_end=offset_end,
                    max_length=max_length
                )
            ]
        )
    }


def an_opportunity(
    need_id: str = NEED_ID,
    title: str = 'Adult Games - NSOs'
) -> Opportunity:
    return Opportunity(
        need_id=need_id,
        title=title,
        url=f'https://example.test/needs/{need_id}'
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

        # The default stays what the event was collected with. Moving
        # it with the count would leave the reset nothing to go back
        # to.
        assert result.events[0].roles == (
            a_role(
                need_id=NEED_ID,
                slots=4,
                edited=True,
                default_slots=12
            ),
        )

    def test_the_other_roles_are_left_alone(self, edit):
        event = an_event(
            roles=(
                a_role(need_id=NEED_ID, slots=12),
                a_role(need_id=OTHER_NEED_ID, slots=8)
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

        assert result.events[0].roles[1] == a_role(
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
    def test_the_role_s_own_default_is_what_comes_back(self, edit):
        # What the role was collected with, not today's data model: an
        # event collected again can arrive asking for another number.
        edited = an_event(
            roles=(a_role(slots=4, edited=True, default_slots=9),)
        )

        result = edit(
            [Operation(op=OP_RESET_SLOTS, event_ids=('gcal-1',))],
            events=[edited]
        )

        assert result.events[0].roles == (
            a_role(slots=9, edited=False, default_slots=9),
        )

    def test_a_role_the_run_holds_no_opportunity_for_still_resets(
        self, edit
    ):
        # It used to be refused, because the number came from the
        # run's opportunity and a role naming one the run does not
        # hold had nowhere to read it. The role carries its own now
        # (D25), so there is nothing left to refuse.
        stray = an_event(
            roles=(
                a_role(
                    need_id='000000',
                    slots=4,
                    edited=True,
                    default_slots=7
                ),
            )
        )

        result = edit(
            [Operation(op=OP_RESET_SLOTS, event_ids=('gcal-1',))],
            events=[stray]
        )

        assert result.events[0].roles == (
            a_role(
                need_id='000000',
                slots=7,
                edited=False,
                default_slots=7
            ),
        )


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
            categories=two_categories()
        )

        assert result.events[0].category == 'junior_game'
        assert result.events[0].roles == (
            a_role(need_id=OTHER_NEED_ID, slots=6),
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
            categories=two_categories(
                offset_start=0,
                offset_end=0,
                max_length=None
            )
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
            categories=two_categories()
        )

        assert an_event().match is not None
        assert result.events[0].match is None

    def test_what_the_collection_matched_is_kept(self, edit):
        # The one thing a change of category cannot recompute.  Left
        # as it is, the row can say it was changed and an undo has
        # somewhere to put it back to.
        result = edit(
            [
                Operation(
                    op=OP_SET_CATEGORY,
                    event_ids=('gcal-1',),
                    category='junior_game'
                )
            ],
            categories=two_categories()
        )

        assert result.events[0].collected_category == 'adult_game'

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
            roles=(a_role(need_id=NEED_ID, slots=4, edited=True),)
        )

        result = edit(
            [Operation(op=OP_UNDO, event_ids=('gcal-1',))],
            events=[edited]
        )

        assert result.events[0].roles == (
            a_role(need_id=NEED_ID, slots=12, edited=False),
        )

    def test_the_category_goes_back_to_the_collected_one(self, edit):
        # With the times and the volunteers that category asks for:
        # putting the row back under it and leaving it timed by the
        # one somebody chose would be a row collection never produced.
        chosen = an_event(
            category='junior_game',
            collected_category='adult_game',
            roles=(a_role(need_id=OTHER_NEED_ID, slots=6),),
            shift_start='19:00',
            shift_end='21:00'
        )

        result = edit(
            [Operation(op=OP_UNDO, event_ids=('gcal-1',))],
            events=[chosen],
            categories=two_categories(
                offset_start=0,
                offset_end=0,
                max_length=None
            )
        )

        assert result.events[0].category == 'adult_game'
        assert result.events[0].roles == (a_role(),)
        assert result.events[0].shift_start == '19:15'
        assert result.events[0].shift_end == '21:30'

    def test_a_category_change_and_an_undo_in_one_call_come_back(
        self,
        edit
    ):
        # The round trip, through the operations a reviewer presses
        # rather than through an event written out by hand.
        result = edit(
            [
                Operation(
                    op=OP_SET_CATEGORY,
                    event_ids=('gcal-1',),
                    category='junior_game'
                ),
                Operation(op=OP_UNDO, event_ids=('gcal-1',))
            ],
            categories=two_categories()
        )

        assert result.events[0].category == 'adult_game'
        assert result.events[0].roles == (a_role(),)

    def test_an_assignment_made_where_nothing_matched_is_kept(self, edit):
        # A row given a category *because* its title matched nothing
        # has an assignment worth keeping: there is no collected
        # category to go back to, and throwing the assignment away
        # would leave the run blocked by the row somebody just fixed.
        assigned = an_event(
            category='adult_game',
            collected_category=None,
            shift_start='08:00',
            shift_end='09:00'
        )

        result = edit(
            [Operation(op=OP_UNDO, event_ids=('gcal-1',))],
            events=[assigned]
        )

        assert result.events[0].category == 'adult_game'
        assert result.events[0].shift_start == '19:15'
        assert result.events[0].shift_end == '21:30'

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
            an_event(id='gcal-1'),
            an_event(id='gcal-2', title='Axles of Evil'),
            an_event(id='gcal-3', title='Break Neck Betties')
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
            an_event(id='gcal-1'),
            an_event(id='gcal-2', title='Axles of Evil')
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
            an_event(id='gcal-1'),
            an_event(id='gcal-2', title='Axles of Evil')
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
            an_event(
                category='junior_game',
                collected_category='adult_game',
                roles=(a_role(need_id=OTHER_NEED_ID, slots=6),),
                shift_start='19:00',
                shift_end='21:00'
            ),
            categories=two_categories(
                offset_start=0,
                offset_end=0,
                max_length=None
            )
        ) is True

    def test_a_category_given_where_nothing_matched_is_not_edited(
        self,
        ask_if_edited
    ):
        # Undo keeps that assignment, so there is nothing it would
        # change and no undo to offer.
        assert ask_if_edited(
            an_event(collected_category=None)
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
