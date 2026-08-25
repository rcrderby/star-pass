#!/usr/bin/env python3
""" What a collection is arranged from.

    The calendars, the need IDs and the calendar item every test in
    this directory starts from.  Here rather than in either module,
    because a second copy would let two tests believe they were
    collecting the same window while collecting different ones.
"""

# Imports - Python Standard Library
from typing import Any, Callable, Dict

# Constants
# A calendar with one query string, and that string empty, so it is
# read once, the whole window is what the search returned, and a repeat
# in the results is one the test arranged.
CALENDAR = 'events'

# A calendar with two query strings, neither of them empty, so it is
# read twice over, an event matching both arrives twice, and the whole
# window is a third read.
REPEATING_CALENDAR = 'practices'
NEED_ID = '879609'
OTHER_NEED_ID = '879610'

# What a scripted answer is: the request in, the body out.
Script = Callable[[Dict[str, Any]], Dict[str, Any]]


def an_item(
    identifier: str = 'gcal-1',
    summary: str = 'Wheels of Justice vs Rose City',
    start: str = '2026-09-03T19:00:00-07:00',
    end: str = '2026-09-03T21:00:00-07:00',
    description: str | None = None
) -> Dict[str, Any]:
    """ Return one calendar item, as the calendar answers with one.

        The description is left out unless a test asks for one,
        because a calendar item carries the key only when somebody
        wrote something in it.
    """
    item: Dict[str, Any] = {
        'id': identifier,
        'summary': summary,
        'start': {'dateTime': start},
        'end': {'dateTime': end}
    }

    if description is not None:
        item['description'] = description

    return item
