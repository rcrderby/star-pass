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
"""


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
