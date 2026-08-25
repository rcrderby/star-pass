#!/usr/bin/env python3
""" Editing the events in a run's current revision.

    Nothing here touches the database: 'apply' answers with the events
    as they would be and the lines to log, and a caller decides when
    that becomes durable.  The shift data model is replaced, because
    what a category asks for is an input to an edit and not something
    these tests are about.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Third-Party
import pytest

# Imports - Local
# 'fixture_edit' is imported rather than defined here: pytest finds a
# fixture by its presence in this module's namespace, and the reading
# beside this one applies operations the same way.
# pylint: disable-next=unused-import
from _editing_events import (  # noqa: F401
    a_role,
    a_row_under_another_category,
    an_event,
    fixture_edit,
    two_categories
)
from conftest import (
    OTHER_SHIFT_NEED_ID as OTHER_NEED_ID,
    SHIFT_NEED_ID as NEED_ID
)
from star_pass._editing import HANDLERS, Operation
from star_pass._records import (
    EDIT_OPERATIONS,
    OP_NUDGE,
    OP_REMOVE,
    OP_RESET_SLOTS,
    OP_SET_CATEGORY,
    OP_SET_END,
    OP_SET_SLOTS,
    OP_SET_START,
    OP_UNASSIGN,
    OP_UNDO
)
from star_pass._exceptions import ValidationError


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


class TestUnassigning:
    # Unassigned is where a row starts when the collection matched
    # nothing, and the only row it is a state of.

    def a_row_that_matched_nothing(self, **overrides):
        return an_event(
            category='adult_game',
            collected_category=None,
            **overrides
        )

    def test_the_row_goes_back_to_serving_nothing(self, edit):
        result = edit(
            [Operation(op=OP_UNASSIGN, event_ids=('gcal-1',))],
            events=[self.a_row_that_matched_nothing()]
        )

        assert result.events[0].category is None
        assert result.events[0].roles == ()

    def test_the_calendar_times_become_the_shift_times(self, edit):
        # There are no offsets left to apply, which is what an event
        # serving no opportunity is stored with.
        result = edit(
            [Operation(op=OP_UNASSIGN, event_ids=('gcal-1',))],
            events=[self.a_row_that_matched_nothing()]
        )

        assert result.events[0].shift_start == '19:00'
        assert result.events[0].shift_end == '21:00'

    def test_what_the_collection_matched_is_still_nothing(self, edit):
        # It has to stay empty, or the row would lose the one thing
        # that says it may be unassigned again.
        result = edit(
            [Operation(op=OP_UNASSIGN, event_ids=('gcal-1',))],
            events=[self.a_row_that_matched_nothing()]
        )

        assert result.events[0].collected_category is None

    def test_the_match_is_dropped(self, edit):
        result = edit(
            [Operation(op=OP_UNASSIGN, event_ids=('gcal-1',))],
            events=[self.a_row_that_matched_nothing()]
        )

        assert result.events[0].match is None

    def test_a_row_the_collection_matched_is_refused(self, edit):
        # What such a row wants when it should create no shift is to
        # be removed; unassigning it would leave a row behind that
        # blocks the whole run.
        with pytest.raises(ValidationError) as error:
            edit([Operation(op=OP_UNASSIGN, event_ids=('gcal-1',))])

        assert 'cannot be unassigned' in str(error.value)
        assert 'Remove the event' in str(error.value)

    def test_one_matched_row_refuses_the_whole_selection(self, edit):
        # A call is applied whole or not at all, and a bulk unassign
        # that took the rows it could would leave a selection the
        # reviewer cannot see the shape of.
        with pytest.raises(ValidationError) as error:
            edit(
                [Operation(
                    op=OP_UNASSIGN,
                    event_ids=('gcal-1', 'gcal-2')
                )],
                events=[
                    self.a_row_that_matched_nothing(),
                    an_event(id='gcal-2', title='Axles of Evil')
                ]
            )

        assert '"Axles of Evil"' in str(error.value)


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
        chosen = a_row_under_another_category()

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

    def test_a_row_the_collection_matched_nothing_for_goes_back_to_none(
        self,
        edit
    ):
        # Where the collection matched nothing, that is what an undo
        # goes back to: unassigned, on the calendar's own times and
        # serving nothing.  It is a state a person can see and choose
        # their way out of again, so landing there is putting the row
        # back rather than stranding it.
        assigned = an_event(category='adult_game', collected_category=None)

        result = edit(
            [Operation(op=OP_UNDO, event_ids=('gcal-1',))],
            events=[assigned]
        )

        assert result.events[0].category is None
        assert result.events[0].roles == ()
        assert result.events[0].shift_start == '19:00'
        assert result.events[0].shift_end == '21:00'

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
        for operation in EDIT_OPERATIONS:
            assert operation in message

    def test_every_operation_offered_has_something_that_does_it(self):
        # The published list and the table that answers it are two
        # halves of one fact.  An operation added to the list and not
        # to the table is refused as unknown while the message beside
        # the refusal lists it, which is a contradiction nothing else
        # would notice.
        assert set(HANDLERS) == set(EDIT_OPERATIONS)

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

    def test_the_action_is_recorded_and_not_a_sentence(self, edit):
        # An entry the clients word.  Nothing here reads as English,
        # which is what lets the wording change without every entry
        # already written still saying the old thing.
        result = edit([
            Operation(op=OP_SET_START, event_ids=('gcal-1',), time='18:45')
        ])

        assert result.entries[0].action == OP_SET_START
        assert result.entries[0].shift_time == '18:45'

    def test_one_event_is_named(self, edit):
        result = edit([
            Operation(op=OP_SET_START, event_ids=('gcal-1',), time='18:45')
        ])

        assert result.entries[0].subject == 'Wheels of Justice vs Rose City'
        assert result.entries[0].subject_count == 1

    def test_a_selection_is_counted_and_not_named(self, edit):
        # A line listing thirty titles is one nobody reads, so a
        # selection carries how many rather than which.
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

        assert result.entries[0].subject is None
        assert result.entries[0].subject_count == 2

    def test_a_nudge_records_signed_minutes(self, edit):
        # A size and a direction is a sentence; the value is one
        # number and each client says which way it went.
        result = edit([
            Operation(
                op=OP_NUDGE,
                event_ids=('gcal-1',),
                minutes=-15
            )
        ])

        assert result.entries[0].minutes == -15

    def test_a_category_is_recorded_as_the_model_names_it(self, edit):
        # The key, not the label.  What a category is called belongs
        # to whoever is showing it.
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

        assert result.entries[0].category == 'junior_game'

    def test_slots_are_recorded_against_the_need_id(self, edit):
        # The identifier rather than the Amplify title, which a reader
        # of the run already holds beside it.
        result = edit([
            Operation(
                op=OP_SET_SLOTS,
                event_ids=('gcal-1',),
                need_id=NEED_ID,
                slots=4
            )
        ])

        assert result.entries[0].slots == 4
        assert result.entries[0].need_id == NEED_ID
