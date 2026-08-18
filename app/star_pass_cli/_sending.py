#!/usr/bin/env python3
""" Turning what a send would do, and how it went, into text.

    The other half of the rendering, and a module of its own because
    it is the other half of the work: '_render' shows what a run holds
    and this shows what would become of it -- the preview, the
    restatement the send is confirmed with (D11), and the job that
    does it as it reports itself.

    The same two shapes and the same primitives, which are imported
    from '_render' rather than written again: a table and a column of
    labelled values look the same whichever answer they are showing.

    Every renderer a command uses takes one argument, named 'answer',
    for the same reason the ones next door do: '_commands' holds which
    renderer belongs to which operation as data.
"""

# Imports - Python Standard Library
from typing import Any, Dict, List

# Imports - Local
from star_pass._preview import (
    BLOCKER_ENDS_BEFORE_START,
    BLOCKER_NO_OPPORTUNITY,
    BLOCKER_NO_SLOTS
)
from star_pass._reporting import (
    STEP_FILTER_EVENTS,
    STEP_MATCH_EVENTS,
    STEP_READ_CALENDAR,
    STEP_READ_OPPORTUNITIES,
    STEP_READ_OPPORTUNITY,
    STEP_STORE_EVENTS
)
from ._render import labelled, section, shown, window_text

# Constants
# What a previewed opportunity's row shows, in order.  'SHIFTS' is
# what would arrive and 'EXISTS' is what is already there, kept apart
# because a reader adding them together would be counting a send twice.
PREVIEW_HEADERS = (
    'NEED',
    'TITLE',
    'SHIFTS',
    'EXISTS',
    'SLOTS',
    'FIRST',
    'LAST'
)

# What a shift Amplify already has shows, in order.  Per shift rather
# than as a count, so a reader checking whether the right rows are
# being left out has the days and times to check (D16).
SKIPPED_HEADERS = (
    'NEED',
    'DATE',
    'START',
    'END'
)

# What a blocked event's row shows, in order.
BLOCKER_HEADERS = (
    'EVENT',
    'REASON'
)

# Said once, above the rows, when anything is blocked.  A preview whose
# totals a reader skims should not let them think the blocked events
# below cost them only those shifts.
NOTHING_SENDABLE = 'Nothing can be sent while an event is blocked.'

# How each reason an event cannot be sent is put to a reader.  The
# contract publishes the reasons as identifiers, which is right for
# something a program branches on and wrong for something a person
# reads, so they are worded here -- the module that decides how things
# are shown.  A reason with no wording shows as itself, and a test
# holds this to what the core publishes so that never happens quietly.
# How each thing a job reports is put to a reader, by the name of the
# reporting method that produced it.
EVENT_PHRASES = {
    'step_started': 'Started:',
    'step_finished': 'Done.',
    'step_failed': 'Failed.',
    'sending_started': 'Sending to Amplify.',
    'opportunity_sent': 'Sent to:',
    'job_finished': 'The job is over:'
}

# How each step the core reports is put to a reader.  The core
# publishes the step as an identifier, which is right for something a
# program branches on and wrong for something a person reads, so it is
# worded here -- and here rather than in each of the two places that
# show one, because the terminal reporter renders a local run's steps
# and this renders the same steps read back off a job.  Two copies
# would eventually call one step two things.  A test holds this to
# what the core publishes.
STEP_PHRASES = {
    STEP_READ_CALENDAR: 'Reading data from the Google Calendar service',
    STEP_FILTER_EVENTS: 'Filtering event data',
    STEP_MATCH_EVENTS: 'Matching events to opportunities',
    STEP_READ_OPPORTUNITIES: 'Reading the Amplify opportunities',
    STEP_STORE_EVENTS: 'Storing the collected events',
    STEP_READ_OPPORTUNITY: (
        'Reading what opportunity {subject} already holds'
    )
}

# Where the readable part of an event's payload is, in the order the
# first one found is used.  An event carrying none of them says only
# what it is, which is all several of them have to say.
EVENT_DETAIL_FIELDS = (
    'title',
    'status',
    'path',
    'detail'
)

BLOCKER_PHRASES = {
    BLOCKER_NO_OPPORTUNITY: 'No opportunity to create a shift under.',
    BLOCKER_ENDS_BEFORE_START: 'The shift ends before it starts.',
    BLOCKER_NO_SLOTS: 'No volunteers are wanted.'
}


def preview_row(
        row: Dict[str, Any]
) -> List[str]:
    """ Return what one opportunity would receive, as a row.

        Args:
            row (Dict[str, Any]):
                A preview row from an answer.

        Returns:
            row (List[str]):
                One value per column in 'PREVIEW_HEADERS'.
    """

    return [
        row['needId'],
        shown(row['title']),
        str(row['willCreate']),
        str(row['alreadyInAmplify']),
        str(row['slots']),
        shown(row['firstDate']),
        shown(row['lastDate'])
    ]


def skipped_row(
        shift: Dict[str, Any]
) -> List[str]:
    """ Return one shift Amplify already has, as a row.

        Args:
            shift (Dict[str, Any]):
                A skipped shift from an answer.

        Returns:
            row (List[str]):
                One value per column in 'SKIPPED_HEADERS'.
    """

    return [
        shift['needId'],
        shift['date'],
        shift['shiftStart'],
        shift['shiftEnd']
    ]


def blocker_row(
        blocker: Dict[str, Any]
) -> List[str]:
    """ Return one reason an event cannot be sent, as a row.

        The reason is worded rather than shown as the identifier the
        contract publishes, which is written for a program to branch
        on.

        Args:
            blocker (Dict[str, Any]):
                A blocker from an answer.

        Returns:
            row (List[str]):
                One value per column in 'BLOCKER_HEADERS'.
    """

    reason = blocker['reason']

    return [
        blocker['eventId'],
        BLOCKER_PHRASES.get(reason, reason)
    ]


def preview_totals(
        totals: Dict[str, Any]
) -> str:
    """ Return what a send would do, in numbers.

        Args:
            totals (Dict[str, Any]):
                The totals from a preview.

        Returns:
            text (str):
                The totals, one to a line.
    """

    return labelled(
        pairs=(
            ('Would create', str(totals['willCreate'])),
            ('Already in Amplify', str(totals['alreadyInAmplify'])),
            ('Repeated rows', str(totals['repeatedRows'])),
            ('Blocking events', str(totals['blockingEvents']))
        )
    )


def preview_text(
        answer: Dict[str, Any]
) -> str:
    """ Return what sending a run's current revision would create.

        Args:
            answer (Dict[str, Any]):
                The preview a client answered with.

        Returns:
            text (str):
                The totals, what each opportunity would receive, the
                shifts Amplify already has, and every reason an event
                cannot be sent.
    """

    parts = [preview_totals(totals=answer['totals'])]

    if answer['totals']['blockingEvents']:
        parts.append(NOTHING_SENDABLE)

    parts.append(
        section(
            heading='OPPORTUNITIES',
            headers=PREVIEW_HEADERS,
            rows=[preview_row(row=row) for row in answer['rows']],
            empty='Nothing would be created.'
        )
    )
    parts.append(
        section(
            heading='ALREADY IN AMPLIFY',
            headers=SKIPPED_HEADERS,
            rows=[
                skipped_row(shift=shift)
                for shift in answer['skipped']
            ],
            empty='Amplify has none of these shifts yet.'
        )
    )
    parts.append(
        section(
            heading='BLOCKED',
            headers=BLOCKER_HEADERS,
            rows=[
                blocker_row(blocker=blocker)
                for blocker in answer['blockers']
            ],
            empty='Nothing is blocked.'
        )
    )

    return '\n\n'.join(parts)


def job_text(
        answer: Dict[str, Any]
) -> str:
    """ Return where a job has got to.

        Args:
            answer (Dict[str, Any]):
                The job a client answered with.

        Returns:
            text (str):
                The job's values, one to a line.
    """

    return labelled(
        pairs=(
            ('Job', answer['id']),
            ('Run', answer['runId']),
            ('Kind', answer['kind']),
            ('Status', answer['status']),
            ('Created', answer['createdAt']),
            ('Started', shown(answer['startedAt'])),
            ('Finished', shown(answer['finishedAt'])),
            ('Detail', shown(answer['detail']))
        )
    )


def step_text(
        step: str,
        subject: str = ''
) -> str:
    """ Return what to call one step, in the present participle.

        Read by both things that show a step: the terminal reporter,
        which watches a run in this process, and 'event_line', which
        reads the same steps back off a job.  A step with no wording
        shows as its identifier, which is what a step added to the
        core and not to this map should do: name itself rather than
        vanish.

        Args:
            step (str):
                The identifier the core reported, from 'STEPS'.

            subject (str, optional):
                What the step is working on, where its wording asks
                for one.  Defaults to an empty string.

        Returns:
            text (str):
                What to call it.
    """

    return STEP_PHRASES.get(step, step).replace('{subject}', subject)


def event_detail(
        payload: Dict[str, Any]
) -> str:
    """ Return the readable part of one event's payload.

        Args:
            payload (Dict[str, Any]):
                What the event carried.

        Returns:
            detail (str):
                What it was about, or an empty string when it carried
                nothing a reader wants.
    """

    if 'step' in payload:
        return step_text(
            step=payload['step'],
            subject=str(payload.get('subject', ''))
        )

    return next(
        (
            str(payload[field])
            for field in EVENT_DETAIL_FIELDS
            if field in payload
        ),
        ''
    )


def event_line(
        answer: Any
) -> str:
    """ Return one thing a job reported, as a line to read.

        The kinds are named by the reporting methods that produced
        them, which is right for something a program branches on and
        wrong for something a person reads, so they are worded here --
        the module that decides how things are shown.  A kind with no
        wording shows as itself, which is what a kind added to the core
        and not to this list should do: name itself rather than vanish.

        Args:
            answer (Any):
                One 'StreamEvent' from a job's stream.

        Returns:
            line (str):
                What happened, and what it was about.
    """

    said = EVENT_PHRASES.get(answer.kind, answer.kind)

    return f'{said} {event_detail(payload=answer.payload)}'.rstrip()


def send_restatement(
        run: Dict[str, Any],
        preview: Dict[str, Any]
) -> str:
    """ Return what a send is about to do, for somebody to read.

        The three things D11 asks a confirmation to restate: how many
        shifts, over which days, and to which opportunities.  Built
        from the same row renderer 'runs preview' uses, so what
        somebody confirms is what they were shown.

        Args:
            run (Dict[str, Any]):
                The run, which names the calendar and the window.

            preview (Dict[str, Any]):
                What sending it would create.

        Returns:
            text (str):
                The restatement.
    """

    totals = preview['totals']

    return '\n\n'.join(
        (
            labelled(
                pairs=(
                    ('Run', run['id']),
                    ('Calendar', run['calendar']),
                    ('Window', window_text(window=run['window'])),
                    ('Would create', str(totals['willCreate'])),
                    (
                        'Already in Amplify',
                        str(totals['alreadyInAmplify'])
                    )
                )
            ),
            section(
                heading='OPPORTUNITIES',
                headers=PREVIEW_HEADERS,
                rows=[
                    preview_row(row=row) for row in preview['rows']
                ],
                empty='Nothing would be created.'
            )
        )
    )
