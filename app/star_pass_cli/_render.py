#!/usr/bin/env python3
""" Turning an answer into something to read in a terminal.

    Rendering only.  Everything here takes what a client answered --
    the same document in either mode -- and returns text, so what is
    shown cannot depend on which mode produced it.

    The window is the one place a value is converted rather than
    printed.  The contract carries an exclusive end, because that is
    what the server stores and what arithmetic wants; a person reading
    a run means the last day it covers.  Converting here is what
    CLAUDE.md asks for -- times and window bounds are converted for
    display -- and it keeps the authoritative value unconverted
    everywhere else.

    Two shapes, and the choice between them is the size of the answer.
    A list is a table, because a reader is comparing rows.  One thing
    is a column of labelled values, because a reader is looking a
    single fact up and a row that wide would wrap.  A document holding
    both -- a run, which arrives with its events, its opportunities and
    its change log -- is the labelled values followed by a table each.

    Every renderer a command uses takes one argument, named 'answer',
    so that '_commands' can hold which renderer belongs to which
    operation as data rather than as five near-identical functions.

    What a run holds is here; what would become of it is in
    '_sending' -- the preview, the restatement a send is confirmed
    with, and the job that does it.  The primitives are here, because
    a table looks the same whichever answer it is showing.
"""

# Imports - Python Standard Library
from datetime import date, timedelta
from typing import Any, Dict, List, Sequence, Tuple

# Imports - Local
from star_pass._records import (
    MATCH_KIND_FUZZY,
    REVISION_COLLECTED,
    REVISION_CONTINUED,
    REVISION_RECOLLECTED,
    REVISION_REVERTED,
    UNCOLLECTED_ALL_DAY,
    UNCOLLECTED_EXCLUDED,
    UNCOLLECTED_SEARCH,
    UNCOLLECTED_UNTITLED
)

# Constants
# Two spaces between columns: enough to separate them, little enough
# that a narrow terminal still fits a run's row.
COLUMN_GAP = '  '

# What a run's row shows, in order.
RUN_HEADERS = (
    'ID',
    'CALENDAR',
    'WINDOW',
    'STATUS',
    'EVENTS',
    'SHIFTS',
    'UNMATCHED',
    'REVISED'
)

# What an event's row shows, in order.  The notes column carries what
# a reader would otherwise have to work out; an ordinary keyword match
# is not in it, because a column that says something about every row
# says nothing about any of them.
EVENT_HEADERS = (
    'ID',
    'DATE',
    'SHIFT',
    'MINUTES',
    'TITLE',
    'CATEGORY',
    'ROLES',
    'NOTES'
)

# What an opportunity's row shows, in order.
OPPORTUNITY_HEADERS = (
    'NEED',
    'TITLE',
    'MAXIMUM',
    'OFFSETS',
    'SLOTS'
)

# What a change log entry shows, in order.
LOG_HEADERS = (
    'WHEN',
    'REVISION',
    'WHO',
    'ENTRY'
)

# What a revision's row shows, in order.
REVISION_HEADERS = (
    'NUMBER',
    'CREATED',
    'WHAT IT IS',
    'CHANGES',
    'CURRENT'
)

# What an uncollected event's row shows, in order.  'ADDABLE' is a
# column rather than something a reader works out from the group,
# because whether an event may be pulled in is the server's answer.
UNCOLLECTED_HEADERS = (
    'ID',
    'DATE',
    'WHEN',
    'TITLE',
    'ADDABLE'
)

# Shown in a column that has nothing to show, so a row keeps its shape.
NOTHING = '-'

# Said of the revision being edited now, in the column that marks it.
CURRENT = 'current'

# Said of an event that may be pulled into the run, in its column.
ADDABLE = 'yes'

# What each kind of revision is called.  Worded here for the reason
# the two maps below it are: the contract publishes an identifier and
# the revision it was made from, and each client says it in its own
# words.  It used to be a sentence the core wrote and stored on the
# row, which neither client could word and which a change of wording
# would have left inconsistent between the revisions already recorded
# and the next one.
REVISION_PHRASES = {
    REVISION_COLLECTED: 'As collected',
    REVISION_RECOLLECTED: 'As recollected',
    REVISION_CONTINUED: 'Continued from revision {number}',
    REVISION_REVERTED: 'Reverted to revision {number}'
}

# How each reason an event was left out of a run heads its group.
# Worded here for the same reason a blocker's is: the contract
# publishes identifiers, which is right for something a program
# branches on and wrong for something a person reads.  A reason with
# no wording heads its group as itself, and a test holds this to what
# the core publishes so that never happens quietly.
UNCOLLECTED_PHRASES = {
    UNCOLLECTED_SEARCH:
        'Nobody looked for these: no configured search term found them.',
    UNCOLLECTED_EXCLUDED:
        'Never collected: the title carries a term this deployment excludes.',
    UNCOLLECTED_ALL_DAY:
        'All-day events, which carry no times to build a shift from.',
    UNCOLLECTED_UNTITLED:
        'Untitled events, which cannot be matched to an opportunity.'
}


def last_day(
        window: Dict[str, Any]
) -> str:
    """ Return the last day a window covers, as a reader means it.

        Read from the answer rather than worked out here.  The
        contract publishes it because every client showing a window
        has to say it this way, and the subtraction that used to live
        here was the first of what would have been one per client --
        two of which can disagree about which days a run covers.
        'after' is still this module's, because that direction is a
        request: the command line takes the day it displays and hands
        the contract the day after.

        Args:
            window (Dict[str, Any]):
                A window from an answer.

        Returns:
            day (str):
                The last day covered, as an ISO date.
    """

    return window['lastDay']


def after(
        last_day_covered: str
) -> str:
    """ Return the exclusive end a window covering that last day has.

        The inverse of 'last_day', and here beside it for the same
        reason: the window is authoritative with an exclusive end
        everywhere it is stored, sent or compared, and the one place
        that converts is the one place a reader is spoken to.  A
        command line takes the day it displays and hands the contract
        the day after.

        Args:
            last_day_covered (str):
                The last day to cover, as an ISO date.

        Raises:
            ValueError:
                If the value is not a date.

        Returns:
            end (str):
                The day after it, as an ISO date.
    """

    return str(
        date.fromisoformat(last_day_covered) + timedelta(days=1)
    )


def window_text(
        window: Dict[str, Any]
) -> str:
    """ Return a window as a reader means it.

        Args:
            window (Dict[str, Any]):
                A window from an answer.

        Returns:
            text (str):
                The first and last days it covers.
    """

    return f'{window["start"]} to {last_day(window=window)}'


def shown(
        value: Any
) -> str:
    """ Return a value as it is displayed, or a dash when there is none.

        Args:
            value (Any):
                What an answer carried, which may be null.

        Returns:
            text (str):
                The value, or 'NOTHING' when there was none.
    """

    return NOTHING if value is None else str(value)


def table(
        headers: Sequence[str],
        rows: Sequence[Sequence[str]]
) -> str:
    """ Return rows as aligned columns under their headers.

        Args:
            headers (Sequence[str]):
                One name per column.

            rows (Sequence[Sequence[str]]):
                The rows, each as wide as the headers.

        Returns:
            text (str):
                The table, without a trailing newline.
    """

    widths = [
        max(
            len(str(header)),
            *(len(str(row[column])) for row in rows)
        ) if rows else len(str(header))
        for column, header in enumerate(headers)
    ]

    return '\n'.join(
        COLUMN_GAP.join(
            str(value).ljust(width)
            for value, width in zip(line, widths)
        ).rstrip()
        for line in (headers, *rows)
    )


def labelled(
        pairs: Sequence[Tuple[str, str]]
) -> str:
    """ Return named values, one to a line, aligned on their names.

        What a table is for a list, this is for one thing: a run and a
        job each carry more fields than a terminal row can hold, and a
        reader of one is looking a single value up rather than
        comparing it with the value beside it.

        Args:
            pairs (Sequence[Tuple[str, str]]):
                A name and its value, in the order to show them.

        Returns:
            text (str):
                The values, without a trailing newline.
    """

    width = max(len(name) for name, _ in pairs)

    return '\n'.join(
        f'{name.ljust(width)}{COLUMN_GAP}{value}'
        for name, value in pairs
    )


def section(
        heading: str,
        headers: Sequence[str],
        rows: Sequence[Sequence[str]],
        empty: str
) -> str:
    """ Return one headed table, or a sentence when it has no rows.

        A heading over a table of nothing but column names reads as an
        answer that failed rather than as one that is empty, so the
        sentence says which it is.

        Args:
            heading (str):
                What the section is called.

            headers (Sequence[str]):
                One name per column.

            rows (Sequence[Sequence[str]]):
                The rows, which may be none.

            empty (str):
                What to say instead when there are no rows.

        Returns:
            text (str):
                The heading and what belongs under it.
    """

    return '\n'.join(
        (
            heading,
            table(headers=headers, rows=rows) if rows else empty
        )
    )


def run_row(
        run: Dict[str, Any]
) -> List[str]:
    """ Return one run as a row.

        Args:
            run (Dict[str, Any]):
                A run from an answer.

        Returns:
            row (List[str]):
                One value per column in 'RUN_HEADERS'.
    """

    counts = run['counts']

    return [
        run['id'],
        run['calendar'],
        window_text(window=run['window']),
        run['status'],
        str(counts['events']),
        str(counts['shifts']),
        str(counts['unmatched']) if counts['unmatched'] else NOTHING,
        run['revisedAt']
    ]


def runs_table(
        answer: Sequence[Dict[str, Any]]
) -> str:
    """ Return every run as a table.

        Args:
            answer (Sequence[Dict[str, Any]]):
                The runs a client answered with.

        Returns:
            text (str):
                The table, or a sentence when there are no runs.
    """

    if not answer:
        return 'No runs yet.'

    return table(
        headers=RUN_HEADERS,
        rows=[run_row(run=run) for run in answer]
    )


def roles_text(
        event: Dict[str, Any]
) -> str:
    """ Return the opportunities an event creates shifts for.

        Args:
            event (Dict[str, Any]):
                An event from an answer.

        Returns:
            text (str):
                Each need ID with the volunteers it wants, or a dash
                for an event with no opportunity at all.
    """

    return ', '.join(
        f'{role["needId"]} ({role["slots"]})'
        for role in event['roles']
    ) or NOTHING


def event_notes(
        event: Dict[str, Any]
) -> str:
    """ Return what a reader has to be told about an event.

        Everything here is a reason to look at the row twice, which is
        why an ordinary keyword match is absent: it is how most events
        reach their category, and noting it on every row would bury the
        rows that need attention.

        Args:
            event (Dict[str, Any]):
                An event from an answer.

        Returns:
            text (str):
                The notes, or a dash when there are none.
    """

    match = event['match']
    notes = []

    if event['blocking']:
        notes.append('blocks the send')

    if event['duplicateOf'] is not None:
        notes.append(f'repeats {event["duplicateOf"]}')

    if event['cappedAt'] is not None:
        notes.append(f'capped at {event["cappedAt"]} minutes')

    if match is not None and match['kind'] == MATCH_KIND_FUZZY:
        notes.append(f'fuzzy match, scored {match["score"]}')

    if event['addedByHand']:
        notes.append('added by hand')

    return ', '.join(notes) or NOTHING


def event_row(
        event: Dict[str, Any]
) -> List[str]:
    """ Return one event as a row.

        Args:
            event (Dict[str, Any]):
                An event from an answer.

        Returns:
            row (List[str]):
                One value per column in 'EVENT_HEADERS'.
    """

    return [
        event['id'],
        event['date'],
        f'{event["shiftStart"]}-{event["shiftEnd"]}',
        str(event['lengthMinutes']),
        event['title'],
        shown(event['category']),
        roles_text(event=event),
        event_notes(event=event)
    ]


def opportunity_row(
        opportunity: Dict[str, Any]
) -> List[str]:
    """ Return one opportunity as a row.

        The offsets are signed rather than plain, because a reader
        wants to know which way the shift moved from the event and a
        bare number leaves them to guess.

        Args:
            opportunity (Dict[str, Any]):
                An opportunity from an answer.

        Returns:
            row (List[str]):
                One value per column in 'OPPORTUNITY_HEADERS'.
    """

    return [
        opportunity['needId'],
        opportunity['title'],
        shown(opportunity['maxLength']),
        (
            f'{opportunity["offsetStart"]:+d}'
            f'/{opportunity["offsetEnd"]:+d}'
        ),
        str(opportunity['defaultSlots'])
    ]


def log_row(
        entry: Dict[str, Any]
) -> List[str]:
    """ Return one change log entry as a row.

        Args:
            entry (Dict[str, Any]):
                A log entry from an answer.

        Returns:
            row (List[str]):
                One value per column in 'LOG_HEADERS'.
    """

    return [
        entry['loggedAt'],
        str(entry['revision']),
        entry['principalId'],
        entry['entry']
    ]


def run_summary(
        run: Dict[str, Any]
) -> str:
    """ Return what a run is, above what it holds.

        The zone is shown beside the window rather than folded into it.
        The server's zone is the authoritative one (D16), and a reader
        somewhere else is entitled to know which zone the dates they
        are looking at were read in.

        The interrupted job is here because this is where somebody
        finds the identifier 'jobs resume' takes.  Resuming is a
        deliberate act (D10), so nothing hands the identifier over on
        its own, and before it was published the only place to read
        one was the service's log.

        Args:
            run (Dict[str, Any]):
                A run from an answer.

        Returns:
            text (str):
                The run's own values, one to a line.
    """

    counts = run['counts']

    return labelled(
        pairs=(
            ('Run', run['id']),
            ('Calendar', run['calendar']),
            ('Window', window_text(window=run['window'])),
            ('Timezone', run['window']['timezone']),
            ('Status', run['status']),
            ('Collected', run['collectedAt']),
            ('Sent', shown(run['sentAt'])),
            ('Revised', run['revisedAt']),
            ('Revision', str(run['currentRevision'])),
            ('Events', str(counts['events'])),
            ('Shifts', str(counts['shifts'])),
            ('Unmatched', str(counts['unmatched'])),
            ('Not collected', str(counts['uncollected'])),
            ('Active job', shown(run['activeJobId'])),
            ('Interrupted job', shown(run['interruptedJobId']))
        )
    )


def run_detail(
        answer: Dict[str, Any]
) -> str:
    """ Return one run, everything in it and everything done to it.

        The three lists arrive in one answer because a reader looking
        at one is looking at all three, and reading them separately
        would let them disagree.  They are shown together for the same
        reason.

        Args:
            answer (Dict[str, Any]):
                The run a client answered with.

        Returns:
            text (str):
                The run in full.
    """

    return '\n\n'.join(
        (
            run_summary(run=answer),
            section(
                heading='EVENTS',
                headers=EVENT_HEADERS,
                rows=[
                    event_row(event=event)
                    for event in answer['events']
                ],
                empty='This revision holds no events.'
            ),
            section(
                heading='OPPORTUNITIES',
                headers=OPPORTUNITY_HEADERS,
                rows=[
                    opportunity_row(opportunity=opportunity)
                    for opportunity in answer['opportunities']
                ],
                empty='The run resolved no opportunities.'
            ),
            section(
                heading='CHANGE LOG',
                headers=LOG_HEADERS,
                rows=[
                    log_row(entry=entry)
                    for entry in answer['log']
                ],
                empty='Nothing has been changed.'
            )
        )
    )


def revision_words(
        revision: Dict[str, Any]
) -> str:
    """ Return what a revision is, in words.

        The two kinds a collection fills name no revision, so the
        wording for them holds no placeholder and formatting one with
        a number nobody asked for would be formatting a sentence that
        has no room for it.

        Args:
            revision (Dict[str, Any]):
                A revision from an answer.

        Returns:
            words (str):
                What kind of revision it is, naming the one it was
                made from where there is one.
    """

    wording = REVISION_PHRASES.get(revision['kind'], revision['kind'])

    return wording.format(number=revision['sourceRevision'])


def revision_row(
        revision: Dict[str, Any]
) -> List[str]:
    """ Return one revision as a row.

        The change count is shown as it is, including zero: a revision
        nothing was changed in was sealed and left, which is what tells
        a reader which one in a list is worth opening.

        Args:
            revision (Dict[str, Any]):
                A revision from an answer.

        Returns:
            row (List[str]):
                One value per column in 'REVISION_HEADERS'.
    """

    return [
        str(revision['number']),
        revision['createdAt'],
        revision_words(revision=revision),
        str(revision['changes']),
        CURRENT if revision['current'] else NOTHING
    ]


def revisions_table(
        answer: Sequence[Dict[str, Any]]
) -> str:
    """ Return a run's revisions as a table.

        Args:
            answer (Sequence[Dict[str, Any]]):
                The revisions a client answered with.

        Returns:
            text (str):
                The table, or a sentence when there are none.
    """

    if not answer:
        return 'This run has no revisions yet.'

    return table(
        headers=REVISION_HEADERS,
        rows=[revision_row(revision=revision) for revision in answer]
    )


def uncollected_row(
        event: Dict[str, Any]
) -> List[str]:
    """ Return one thing a run left out, as a row.

        Args:
            event (Dict[str, Any]):
                An uncollected event from an answer.

        Returns:
            row (List[str]):
                One value per column in 'UNCOLLECTED_HEADERS'.
    """

    times = (
        f'{event["calendarStart"]}-{event["calendarEnd"]}'
        if event['calendarStart'] and event['calendarEnd']
        else NOTHING
    )

    return [
        event['id'],
        shown(event['date']),
        times,
        shown(event['title']),
        ADDABLE if event['addable'] else NOTHING
    ]


def uncollected_text(
        answer: Sequence[Dict[str, Any]]
) -> str:
    """ Return what a run's window held and the run left out.

        A table per reason rather than one table with a reason column:
        the reason is what a reader came with -- "why is this event not
        here" -- and it is the same for every row under it.

        Args:
            answer (Sequence[Dict[str, Any]]):
                The groups a client answered with.

        Returns:
            text (str):
                A headed table per group, or a sentence when the run
                collected everything its window held.
    """

    if not answer:
        return 'Everything this run\'s window held was collected.'

    return '\n\n'.join(
        '\n'.join(
            (
                UNCOLLECTED_PHRASES.get(group['reason'], group['reason']),
                table(
                    headers=UNCOLLECTED_HEADERS,
                    rows=[
                        uncollected_row(event=event)
                        for event in group['events']
                    ]
                )
            )
        )
        for group in answer
    )
