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
from typing import Optional

# Imports - Local
from star_pass._records import Run, RUN_STATUSES_SENT


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
