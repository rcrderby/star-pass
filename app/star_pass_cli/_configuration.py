#!/usr/bin/env python3
""" What the deployment was configured with, and what it is missing.

    Its own module beside the two that show a run: '_render' shows
    what a run holds and '_sending' what would become of it, and a
    setting is neither.  The table and the labelled values come from
    '_render', because a table looks the same whichever answer it is
    showing.

    A calendar searched for nothing in particular carries one empty
    query string, which is a value and not an absence.  The contract
    publishes it as it is configured, so the wording that says what an
    empty one means is here, where wording belongs.

    The credential is shown beside the settings for the same reason it
    is read beside them: it is a fact about this deployment rather
    than about any run, and the four characters published of it are
    there to answer "which one is it running on".  The titles the data
    model has not matched are here on the same argument, and they are
    read by whoever is about to edit the model.
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

# What a tested credential is said to be.  A whole word each way: the
# line is read at a glance and a tick and a cross are not one.
WORKING = 'working'
NOT_WORKING = 'not working'

# How the four published characters are shown.  Said as an ending
# rather than printed alone, so nobody reads them as the credential.
ENDING = 'ending {last_four}'

# What an unmatched title's row shows, in order.  The count is the
# column the reader is scanning: a title seen every month is a
# category the model is missing, and one seen once is an event that
# happened once.
UNMATCHED_HEADERS = (
    'CALENDAR',
    'TITLE',
    'SEEN',
    'LAST SEEN'
)

# Said when the log holds nothing, which is a finding rather than an
# empty screen: every title anybody recorded matched a category.
NOTHING_UNMATCHED = (
    'No unmatched titles have been recorded. Every title anybody has '
    'recorded matched a category.'
)


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


def credential_text(
        answer: Dict[str, Any]
) -> str:
    """ Return whether the Amplify credential works.

        Args:
            answer (Dict[str, Any]):
                What a credential test answered.

        Returns:
            text (str):
                Whether it works and which one it is, with the reason
                below when it does not.
    """

    lines = labelled(
        pairs=(
            (
                'Amplify credential',
                WORKING if answer['working'] else NOT_WORKING
            ),
            (
                'Ends with',
                answer['lastFour'] or NOTHING
            )
        )
    )

    if answer['reason'] is None:
        return lines

    return f'{lines}\n\n{answer["reason"]}'


def unmatched_row(
        unmatched: Dict[str, Any]
) -> List[str]:
    """ Return one unmatched title as a row.

        Args:
            unmatched (Dict[str, Any]):
                An entry from an answer.

        Returns:
            row (List[str]):
                One value per column in 'UNMATCHED_HEADERS'.
    """

    return [
        unmatched['calendar'],
        unmatched['title'],
        str(unmatched['timesSeen']),
        unmatched['lastSeen']
    ]


def unmatched_text(
        answer: Sequence[Dict[str, Any]]
) -> str:
    """ Return the titles the data model has not matched.

        Args:
            answer (Sequence[Dict[str, Any]]):
                The entries a client answered with.

        Returns:
            text (str):
                A table, or a sentence when nothing has been recorded.
    """

    if not answer:
        return NOTHING_UNMATCHED

    return table(
        headers=UNMATCHED_HEADERS,
        rows=[
            unmatched_row(unmatched=unmatched)
            for unmatched in answer
        ]
    )
