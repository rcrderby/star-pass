#!/usr/bin/env python3
""" Showing what the service was configured with.

    Its own module beside the two that show a run: '_render' shows
    what a run holds and '_sending' what would become of it, and a
    setting is neither.  The table and the labelled values come from
    '_render', because a table looks the same whichever answer it is
    showing.

    A calendar searched for nothing in particular carries one empty
    query string, which is a value and not an absence.  The contract
    publishes it as it is configured, so the wording that says what an
    empty one means is here, where wording belongs.
"""

# Imports - Python Standard Library
from typing import Any, Dict, List, Sequence

# Imports - Local
from ._render import labelled, NOTHING, table

# Constants
# What a calendar's row shows, in order.
CALENDAR_HEADERS = (
    'CALENDAR',
    'SEARCHED FOR'
)

# Said of a calendar whose window is read whole, in the column that
# would otherwise show what it is searched for.  A calendar configured
# with an empty query string searches for nothing in particular and
# therefore returns everything, so nothing in its window can be missed
# for want of a term -- which is what a reader of this column came to
# find out.
EVERYTHING = 'everything in the window'

# How the terms a calendar is searched for are joined.
TERM_GAP = ', '

# Headed rather than left to follow the values above it, because the
# two are different kinds of thing and a reader scanning for a
# calendar should not have to read the settings first.
CALENDARS_HEADING = 'CALENDARS'


def searched_for(
        calendar: Dict[str, Any]
) -> str:
    """ Return what a calendar's window is searched for.

        Args:
            calendar (Dict[str, Any]):
                A calendar from an answer.

        Returns:
            text (str):
                The terms, or what an empty one means.
    """

    terms = [term for term in calendar['searchTerms'] if term]

    if not terms:
        return EVERYTHING

    return TERM_GAP.join(terms)


def calendar_row(
        calendar: Dict[str, Any]
) -> List[str]:
    """ Return one calendar as a row.

        Args:
            calendar (Dict[str, Any]):
                A calendar from an answer.

        Returns:
            row (List[str]):
                One value per column in 'CALENDAR_HEADERS'.
    """

    return [
        calendar['key'],
        searched_for(calendar=calendar)
    ]


def excluded_text(
        terms: Sequence[str]
) -> str:
    """ Return the terms a title is never collected under.

        Args:
            terms (Sequence[str]):
                The terms, as the contract publishes them.

        Returns:
            text (str):
                The terms, or a dash when the deployment excludes
                none.
    """

    return TERM_GAP.join(terms) or NOTHING


def config_text(
        answer: Dict[str, Any]
) -> str:
    """ Return the settings the service is running on.

        Args:
            answer (Dict[str, Any]):
                The configuration a client answered with.

        Returns:
            text (str):
                The settings, and the calendars under a heading of
                their own.
    """

    return '\n\n'.join(
        (
            labelled(
                pairs=(
                    ('Timezone', answer['timezone']),
                    ('Match threshold', str(answer['matchThreshold'])),
                    (
                        'Never collected',
                        excluded_text(terms=answer['excludedTitleTerms'])
                    )
                )
            ),
            CALENDARS_HEADING,
            table(
                headers=CALENDAR_HEADERS,
                rows=[
                    calendar_row(calendar=calendar)
                    for calendar in answer['calendars']
                ]
            )
        )
    )
