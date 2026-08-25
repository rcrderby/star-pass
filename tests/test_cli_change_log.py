#!/usr/bin/env python3
""" The command line client's reading of a run's change log.

    Its own module rather than a class in 'test_cli_commands.py',
    which is near the thousand-line cap the linter holds a module to.

    What it is mostly about is the wording: the contract publishes
    what was done and the values it carried, and this client puts them
    into a sentence.  A test binding that map to the core's own tuple
    is what stops an action reaching a table as 'set_category'.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
from re import findall
from typing import Any, Callable, Dict

# Imports - Local
from star_pass._records import (
    LOG_ACTIONS,
    OP_NUDGE,
    OP_REMOVE,
    OP_SET_CATEGORY,
    OP_SET_SLOTS,
    OP_SET_START
)
from star_pass_cli import _render

# What each action carries beyond the events it was done to.  A
# wording asking for a value its action never has leaves the
# placeholder in the line; one that does not ask for the value its
# action does have throws it away.
CARRIED = {
    OP_SET_CATEGORY: {'category'},
    OP_SET_START: {'time'},
    'set_end': {'time'},
    OP_SET_SLOTS: {'slots', 'needId'},
    OP_NUDGE: {'minutes', 'direction'}
}


def an_entry(**values: Any) -> Dict[str, Any]:
    """ Return one entry as an answer carries it. """
    entry: Dict[str, Any] = {
        'id': 1,
        'revision': 1,
        'loggedAt': '2026-09-01T00:00:00+00:00',
        'principalId': 'static-token',
        'action': OP_REMOVE,
        'subject': 'Adult Scrimmages',
        'subjectCount': 1,
        'category': None,
        'shiftTime': None,
        'minutes': None,
        'slots': None,
        'needId': None
    }
    entry.update(values)

    return entry


class TestTheWordings:
    def test_every_action_the_core_publishes_is_worded(self) -> None:
        # An action with no wording reaches the table as its
        # identifier, which is written for a program to branch on.
        assert set(_render.LOG_ACTION_PHRASES) == set(LOG_ACTIONS)

    def test_no_wording_is_for_an_action_that_does_not_exist(
        self
    ) -> None:
        # The direction that catches an action being renamed rather
        # than added: the wording would survive and nothing would say
        # it is now unreachable.
        for action in _render.LOG_ACTION_PHRASES:
            assert action in LOG_ACTIONS

    def test_no_action_is_worded_as_itself(self) -> None:
        for action, wording in _render.LOG_ACTION_PHRASES.items():
            assert wording != action

    def test_every_wording_names_what_it_was_done_to(self) -> None:
        # Every action is done to an event, and a line that did not
        # say which reads as a change to nothing in particular.
        for wording in _render.LOG_ACTION_PHRASES.values():
            assert '{subject}' in wording

    def test_only_the_actions_carrying_a_value_ask_for_one(self) -> None:
        for action, wording in _render.LOG_ACTION_PHRASES.items():
            named = set(findall(r'\{(\w+)\}', wording)) - {'subject'}

            assert named == CARRIED.get(action, set())


class TestWhatALineSays:
    def test_one_event_is_named(self) -> None:
        line = _render.log_words(entry=an_entry())

        assert line == 'Removed "Adult Scrimmages".'

    def test_a_selection_is_counted(self) -> None:
        # A line listing thirty titles is one nobody reads.
        line = _render.log_words(
            entry=an_entry(subject=None, subjectCount=30)
        )

        assert line == 'Removed 30 events.'

    def test_a_nudge_later_says_later(self) -> None:
        # The entry carries signed minutes, and the direction is a
        # word this client chooses.
        line = _render.log_words(
            entry=an_entry(action=OP_NUDGE, minutes=30)
        )

        assert line == 'Moved "Adult Scrimmages" 30 minutes later.'

    def test_a_nudge_earlier_says_earlier_and_drops_the_sign(
        self
    ) -> None:
        line = _render.log_words(
            entry=an_entry(action=OP_NUDGE, minutes=-15)
        )

        assert line == 'Moved "Adult Scrimmages" 15 minutes earlier.'

    def test_a_category_is_shown_by_the_key_the_run_names_it_by(
        self
    ) -> None:
        # The same identifier the EVENTS table shows in its own
        # category column, so a reader matches the two by eye.
        line = _render.log_words(
            entry=an_entry(
                action=OP_SET_CATEGORY,
                category='junior_scrimmage'
            )
        )

        assert 'junior_scrimmage' in line

    def test_slots_are_shown_against_the_need_id(self) -> None:
        # The identifier the OPPORTUNITIES table lists beside its
        # title, for the same reason.
        line = _render.log_words(
            entry=an_entry(
                action=OP_SET_SLOTS,
                slots=4,
                needId='905196'
            )
        )

        assert line == (
            'Set 4 volunteers wanted on "Adult Scrimmages" for '
            'need 905196.'
        )

    def test_an_action_with_no_wording_is_shown_as_itself(self) -> None:
        # A line with a gap in it is more use than a line that cannot
        # be written, which is what an entry from before the actions
        # were recorded would otherwise produce.
        line = _render.log_words(entry=an_entry(action=''))

        assert line == ''


class TestARunShowsItsLog:
    def test_the_log_is_shown_under_its_own_heading(
        self,
        capsys: Any,
        cli: Callable[..., int],
        populated: str
    ) -> None:
        cli('runs', 'show', populated)
        shown = capsys.readouterr().out

        assert 'CHANGE LOG' in shown
        assert 'Moved "Adult Scrimmages" 30 minutes later.' in shown
