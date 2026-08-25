#!/usr/bin/env python3
""" The event, the role and the model the editing tests are written against.

    Below both of them.  'test_editing' asks what an operation does to
    an event and 'test_event_edited' asks whether one has been
    changed, and the two have to be asking about the same event: a
    second copy of these would eventually differ in an offset, and the
    file that disagreed would be testing arithmetic nothing else does.

    Not in 'conftest' because these are one subject and that module is
    close to the length pylint allows -- the same reason
    'documents.py' sits beside it.  What is here is a builder rather
    than a fixture, because a test writes several events in one
    arrangement and a fixture answers once.
"""

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
from star_pass._editing import apply, Operation
from star_pass._records import Event, EventRole, Match


def a_role(
    need_id: str = NEED_ID,
    slots: int = 12,
    edited: bool = False,
    default_slots: Optional[int] = None
) -> EventRole:
    """ Return one role, with the timing every event here carries.

        The calendar times are 19:00 to 21:00 and these offsets
        reproduce the 19:15 to 21:30 shift the default event holds, so
        an event nothing has touched is one the model agrees with.
    """
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


def a_row_under_another_category(**overrides: Any) -> Event:
    """ Return a row somebody has put under a different opportunity.

        Under 'junior_game', collected under 'adult_game', and timed
        the way 'two_categories' times the second when it is asked for
        no offsets: the row a category change produces, which is the
        row an undo has to be able to put back.
    """
    return an_event(
        category='junior_game',
        collected_category='adult_game',
        roles=(a_role(need_id=OTHER_NEED_ID, slots=6),),
        shift_start='19:00',
        shift_end='21:00',
        **overrides
    )


def install_model(
    shift_model: Callable[..., None],
    categories: Optional[Dict[str, Any]] = None
) -> None:
    """ Put the model an operation is answered against in place.

        Its one category is the one 'an_event' is collected under, and
        its offsets reproduce that event's shift times, so an event
        nothing has touched is one the model agrees with.  A test
        wanting a second category names both.
    """
    shift_model(
        categories=categories
        if categories is not None
        else {'adult_game': a_category(need_ids=[a_need()])},
        calendars=(CALENDAR,)
    )


@pytest.fixture(name='edit')
def fixture_edit(shift_model: Callable[..., None]) -> Callable[..., Any]:
    """ Return a way to apply operations to a set of events. """

    def run(
        operations: List[Operation],
        events: Optional[List[Event]] = None,
        categories: Optional[Dict[str, Any]] = None
    ) -> Any:
        install_model(shift_model=shift_model, categories=categories)

        return apply(
            operations=operations,
            events=events if events is not None else [an_event()],
            calendar=CALENDAR
        )

    return run
