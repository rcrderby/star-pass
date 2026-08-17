#!/usr/bin/env python3
""" What a caller is told when what they asked for is not there.

    Here rather than in the routes because both things that speak the
    contract have to say it the same way.  The service answers a
    missing run with a problem document and the command line client
    answers it from the same database in the same process (D2); a
    caller reading one message in one mode and another in the other
    would be reading a difference between the modes, which is the
    thing Step 5 exists to rule out.

    Written for a person and safe to show: an identifier the caller
    supplied, and nothing else.

    Choosing between them lives here too, for the same reason.  Two
    halves that each decided which refusal applied could refuse
    different things about one run, which is a difference between the
    modes that no comparison of messages would find.
"""

# Imports - Python Standard Library
from typing import Optional, Tuple

# Imports - Local
from star_pass._records import (
    IdempotencyRecord,
    Run,
    RUN_STATUS_COLLECTING,
    RUN_STATUSES_SENT
)
from star_pass._send import blocked_message  # noqa: F401

# Constants
# What a request arriving on an idempotency key that is already in use
# turns out to be.  Named rather than described, because each half
# answers a different one differently and a comparison of messages
# would not catch a half that classified one wrongly.
REPLAY_ANSWERED = 'answered'
REPLAY_DIFFERENT = 'different'
REPLAY_RUNNING = 'running'
REPLAY_KINDS = (
    REPLAY_ANSWERED,
    REPLAY_DIFFERENT,
    REPLAY_RUNNING
)


def no_such_run(
        run_id: str
) -> str:
    """ Return what to say when a run was asked for by an unused ID.

        Args:
            run_id (str):
                What the caller asked for.

        Returns:
            message (str):
                What to tell them.
    """

    return f'There is no run with the ID "{run_id}".'


def no_such_job(
        job_id: str
) -> str:
    """ Return what to say when a job was asked for by an unused ID.

        Args:
            job_id (str):
                What the caller asked for.

        Returns:
            message (str):
                What to tell them.
    """

    return f'There is no job with the ID "{job_id}".'


def already_working(
        run_id: str,
        job_id: str
) -> str:
    """ Return what to say when a run already has a job on it.

        Args:
            run_id (str):
                Run the caller asked about.

            job_id (str):
                What is already working on it.

        Returns:
            message (str):
                What to tell them.
    """

    return (
        f'Run "{run_id}" already has job "{job_id}" working on it. '
        'Wait for it to finish, or read the job to see how far it '
        'has got.'
    )


def already_sent(
        run_id: str
) -> str:
    """ Return what to say when a run has put shifts into Amplify.

        Args:
            run_id (str):
                Run the caller asked about.

        Returns:
            message (str):
                What to tell them.
    """

    return (
        f'Run "{run_id}" has already sent shifts to Amplify, which '
        'cannot be taken back. Collecting it again would replace the '
        'events that describe what was sent. Collect a new run '
        'instead.'
    )


def has_moved(
        run_id: str,
        changed: int,
        expected: int
) -> str:
    """ Return what to say when a run changed since the caller read it.

        Args:
            run_id (str):
                Run the caller asked about.

            changed (int):
                How many changes it holds.

            expected (int):
                How many the caller was shown.

        Returns:
            message (str):
                What to tell them.
    """

    return (
        f'Run "{run_id}" holds {changed} change(s), not the '
        f'{expected} this request expected. It has been edited since '
        'the number you were shown was read. Read the run again and '
        'confirm against what it says now.'
    )


def still_collecting(
        run_id: str
) -> str:
    """ Return what to say when a run has not finished being collected.

        Args:
            run_id (str):
                Run the caller asked about.

        Returns:
            message (str):
                What to tell them.
    """

    return (
        f'Run "{run_id}" is still being collected, so what it holds is '
        'not yet what it will hold. Wait for the collection to finish '
        'and read the run again. A run left this way by a service that '
        'stopped has an interrupted job to resume.'
    )


def shift_count_moved(
        run_id: str,
        will_create: int,
        expected: int
) -> str:
    """ Return what to say when a send would not create what was shown.

        Args:
            run_id (str):
                Run the caller asked about.

            will_create (int):
                How many shifts a send would create now.

            expected (int):
                How many the caller was shown.

        Returns:
            message (str):
                What to tell them.
    """

    return (
        f'Sending run "{run_id}" would create {will_create} shift(s), '
        f'not the {expected} this request expected. Either the run has '
        'been edited or Amplify has changed since the number you were '
        'shown was worked out. Read the preview again and confirm '
        'against what it says now.'
    )


def why_not_send(
        run: Run,
        blocking: int,
        will_create: int,
        expected: int
) -> Optional[str]:
    """ Return why a run cannot be sent, if it cannot.

        Four refusals, each a different thing being wrong.  A run
        something is already working on would have two sends writing
        into Amplify at once, which no amount of care afterwards can
        take back.  A run still being collected has no settled revision
        to send.  A run holding an event that cannot become a shift
        sends nothing at all, because a missing shift is invisible
        until volunteers cannot sign up.  And a count that has moved
        says the caller confirmed against a page describing a run, or
        an Amplify, that has since changed.

        In that order, because each earlier one makes the next
        meaningless: the count of what a collecting run would create is
        a count of a revision being replaced, and the count of what a
        blocked run would create is a count of a send that will not
        happen.

        Here rather than in the route for the reason 'why_not_recollect'
        is: both halves refuse, and two halves that each decided could
        refuse different things about one run.

        Args:
            run (Run):
                The run being sent.

            blocking (int):
                How many of its events cannot become shifts.

            will_create (int):
                How many shifts a send would create now, net of what
                Amplify already holds.

            expected (int):
                How many the caller was shown.

        Returns:
            reason (str | None):
                What to tell them, or None when the run may be sent.
    """

    if run.active_job_id is not None:
        return already_working(
            run_id=run.id,
            job_id=run.active_job_id
        )

    if run.status == RUN_STATUS_COLLECTING:
        return still_collecting(run_id=run.id)

    if blocking:
        return blocked_message(blocking=blocking)

    if will_create != expected:
        return shift_count_moved(
            run_id=run.id,
            will_create=will_create,
            expected=expected
        )

    return None


def key_used_differently(
        run_id: str
) -> str:
    """ Return what to say when a key was reused for another request.

        Args:
            run_id (str):
                Run the caller asked about.

        Returns:
            message (str):
                What to tell them.
    """

    return (
        f'This idempotency key already claimed a send of run '
        f'"{run_id}", and this request is not that one -- a different '
        'run, or a different number of shifts. A key is a promise that '
        'the request is the one already made, so this is refused '
        'rather than answered with the first request\'s result. Send '
        'again with a new key.'
    )


def send_in_flight(
        run_id: str
) -> str:
    """ Return what to say when the first request is still being answered.

        Args:
            run_id (str):
                Run the caller asked about.

        Returns:
            message (str):
                What to tell them.
    """

    return (
        f'This idempotency key already claimed a send of run '
        f'"{run_id}", and that request has not answered yet. Read the '
        'run to find the job it started rather than asking again: two '
        'sends of one run would both write into Amplify, which cannot '
        'take a shift back.'
    )


def replay(
        record: IdempotencyRecord,
        run_id: str,
        fingerprint: str
) -> Tuple[str, Optional[str]]:
    """ Return what a request arriving on a used key is.

        Three things it can be, and they are different answers.  A key
        carrying a different request has broken the promise a key makes
        and is refused.  A key whose first request has not answered yet
        is one still in hand, and answering it with anything would be
        inventing a result.  Anything else is the ordinary replay: the
        first request's answer, returned rather than written again.

        The choice is here rather than in each half for the reason
        every choice in this module is: the service and the command
        line client both make it, and two copies could classify one
        request differently.

        Args:
            record (IdempotencyRecord):
                What the key already reserved.

            run_id (str):
                Run this request is about.  Checked, because a key
                claims one operation and not one run: a second run
                asked for under a used key would otherwise be answered
                with the first run's job and be reported as sending
                when nothing was.

            fingerprint (str):
                What this request asks for, as the caller summarized
                it.

        Returns:
            classified (Tuple[str, str | None]):
                One of 'REPLAY_KINDS', and what to tell the caller, or
                None for the replay that is answered rather than
                refused.
    """

    if record.run_id != run_id or record.fingerprint != fingerprint:
        return REPLAY_DIFFERENT, key_used_differently(run_id=record.run_id)

    if record.status_code is None:
        return REPLAY_RUNNING, send_in_flight(run_id=record.run_id)

    return REPLAY_ANSWERED, None


def why_not_recollect(
        run: Run,
        changed: int,
        expected: int
) -> Optional[str]:
    """ Return why a run cannot be collected again, if it cannot.

        Three refusals, each a different thing being wrong.  A run
        something is already working on would have two jobs writing
        the same revisions.  A run that has put shifts into Amplify
        cannot have the events describing them replaced, and Amplify
        has no way to take a shift back.  And a change count that has
        moved says the caller confirmed against a page describing a
        run that no longer exists.

        In that order, because the first is temporary and the others
        are not: a reader told the count has moved would go and read
        it again, where the answer is that something is still running.

        Args:
            run (Run):
                The run being collected again.

            changed (int):
                How many changes its current revision holds.

            expected (int):
                How many the caller was shown.

        Returns:
            reason (str | None):
                What to tell them, or None when the run may be
                collected again.
    """

    if run.active_job_id is not None:
        return already_working(
            run_id=run.id,
            job_id=run.active_job_id
        )

    if run.status in RUN_STATUSES_SENT:
        return already_sent(run_id=run.id)

    if changed != expected:
        return has_moved(
            run_id=run.id,
            changed=changed,
            expected=expected
        )

    return None
