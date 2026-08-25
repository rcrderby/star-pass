#!/usr/bin/env python3
""" Answers as the contract carries them, for the tests that read one.

    Written out rather than read from a database, because what reads
    one is deciding how to show a field and wants to set that field.
    These hold the keys to the shape the contract publishes, so a
    rename cannot leave a test passing on its own.

    Beside 'conftest' rather than in it: they are one subject, and the
    module they came from is close to the length pylint allows.
    'conftest' imports the fixtures so pytest still finds them there.
"""

# pylint: disable=missing-function-docstring

# Imports - Python Standard Library
from typing import Any, Callable

# Imports - Third-Party
import pytest


@pytest.fixture(name='window_document')
def fixture_window_document() -> dict:
    """ Return a one-month window as an answer carries one.

        Shared by the fixtures standing in for a service, because a
        window is one fact: two copies of it can disagree about which
        day a run ends on, which is the disagreement 'lastDay' was
        published to stop.
    """
    return {
        'start': '2026-09-01',
        'end': '2026-10-01',
        'lastDay': '2026-09-30',
        'timezone': 'America/Los_Angeles'
    }


@pytest.fixture(name='make_run_document')
def fixture_make_run_document(
    window_document: dict
) -> Callable[..., dict]:
    """ Return a factory building a run as an answer carries one. """

    def build(**overrides: Any) -> dict:
        """ Return the document, replacing any overridden count. """
        return {
            'id': 'r-1',
            'calendar': 'practices',
            'window': dict(window_document),
            'status': 'unsent',
            'revisedAt': '2026-09-02T01:00:00+00:00',
            'counts': {
                'events': overrides.get('events', 1),
                'shifts': overrides.get('shifts', 1),
                'unmatched': overrides.get('unmatched', 0),
                'uncollected': overrides.get('uncollected', 0)
            }
        }

    return build


# One role as an answer carries one, named because two places assert
# it: the factory below and the test holding the shape the contract
# publishes.  Two copies would eventually disagree, and the one that
# was wrong would be the one nothing failed on.
ROLE_DOCUMENT = {
    'needId': '905196',
    'slots': 4,
    'edited': False,
    'offsetStart': 15,
    'offsetEnd': 30,
    'maxLength': 165,
    'defaultSlots': 4
}


@pytest.fixture(name='make_event_document')
def fixture_make_event_document() -> Callable[..., dict]:
    """ Return a factory building an event as an answer carries one.

        Written out rather than read from a database, because what
        reads one is deciding how to show a field and wants to set
        that field.  A test holds these keys to the shape the contract
        publishes, so a rename cannot leave this passing on its own.
    """

    def build(**overrides: Any) -> dict:
        """ Return the document, replacing any overridden field. """
        document: dict = {
            'id': 'event-1',
            'title': 'Adult Scrimmages',
            'date': '2026-09-03',
            'calendarStart': '19:00',
            'calendarEnd': '21:00',
            'calendarNote': None,
            'shiftStart': '19:15',
            'shiftEnd': '21:30',
            'lengthMinutes': 135,
            'cappedAt': None,
            'category': 'scrimmage',
            'match': None,
            'addedByHand': False,
            'edited': False,
            'roles': [dict(ROLE_DOCUMENT)],
            'duplicateOf': None,
            'blocking': False,
            'mayUnassign': False
        }
        document.update(overrides)

        return document

    return build
