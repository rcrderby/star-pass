#!/usr/bin/env python3
""" Running an interrupted job again.

    A job left queued or running when a process stopped is marked
    interrupted and never resumed on its own: a send that resumed
    itself would write to a live volunteer system from state rebuilt
    after a crash.  Somebody asks, and this is what their asking runs.

    A resume is the ordinary work pointed at a job that already
    exists.  A resumed collection collects the run's window again, and
    a resumed send sends what is still missing, so nothing has to
    record how far the interrupted attempt got: every opportunity is
    read immediately before it is written to, and Amplify answers what
    is missing.

    Which work a job runs is decided here, below the service and the
    command line, so both resume the same way.
"""

# Imports - Python Standard Library
import sqlite3
from typing import Callable

# Imports - Local
from ._collect import collect
from ._logging import get_logger
from ._records import Job, JOB_KIND_SEND
from ._reporting import Reporter
from ._send import send

# What the rows a resumed send creates are labelled with.  The key is
# built from the job rather than a fresh value, so the record of what
# was sent says which resume put it there.
RESUME_KEY_PREFIX = 'resume'

# Module logger
logger = get_logger(__name__)


def resume_key(
        job: Job
) -> str:
    """ Return what a resumed send records its rows under.

        Args:
            job (Job):
                The job being resumed.

        Returns:
            key (str):
                The idempotency key the rows carry.
    """

    return f'{RESUME_KEY_PREFIX}-{job.id}'


def work_for(
        job: Job,
        principal_id: str
) -> Callable[[sqlite3.Connection, Reporter], None]:
    """ Return what resuming one job runs.

        Args:
            job (Job):
                The job being resumed, which names the run and what was
                being done to it.

            principal_id (str):
                Who asked for the resume.  Recorded against what
                the resumed work writes, because they are the person
                who caused it, not whoever asked for the attempt that
                was interrupted.

        Returns:
            work (Callable[[sqlite3.Connection, Reporter], None]):
                What to run, on a connection of its own.
    """

    message = f'Resuming the {job.kind} of run {job.run_id}'
    logger.info(message)

    if job.kind == JOB_KIND_SEND:
        key = resume_key(job=job)

        def sending(
                connection: sqlite3.Connection,
                reporter: Reporter
        ) -> None:
            """ Send what the interrupted attempt did not. """
            send(
                connection=connection,
                run_id=job.run_id,
                reporter=reporter,
                principal_id=principal_id,
                idempotency_key=key
            )

        return sending

    def collecting(
            connection: sqlite3.Connection,
            reporter: Reporter
    ) -> None:
        """ Collect the run's window again. """
        collect(
            connection=connection,
            run_id=job.run_id,
            reporter=reporter,
            principal_id=principal_id
        )

    return collecting
