#!/usr/bin/env python3
""" Running work in the background, and recording what it reported.

    The core already describes what it is doing to a 'Reporter' the
    caller supplies rather than printing it, which is what makes this
    possible: 'JobReporter' is a reporter that writes those calls to
    the job's event log, so progress becomes stored data without the
    core knowing anything ran it.

    'JobRunner' owns the other half -- starting a job, running the
    work, and recording how it ended -- so that a caller hands over a
    callable and gets an identifier back rather than waiting.

    Both live in the core rather than in the service.  Nothing here is
    about HTTP, and the command line client runs the same operations
    locally (D2); putting them in the service would mean the CLI could
    not reuse them.

    **Threads and connections.** A SQLite connection belongs to the
    thread that opened it, so the runner is given a way to open one
    rather than a connection to share.  Each job opens its own and
    closes it when it is done, which is also what lets a job write
    while a request reads: the database is in write-ahead logging, so
    a reader does not block the writer.
"""

# Imports - Python Standard Library
import sqlite3
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable, Dict, List

# Imports - Local
from . import _defaults
from ._exceptions import StarPassError
from ._logging import get_logger
from ._records import (
    JOB_STATUS_FAILED,
    JOB_STATUS_SUCCEEDED
)
from ._reporting import Reporter, ShiftBatch
from ._repository import JobRepository

# Constants
JOB_WORKERS = _defaults.JOB_WORKERS

# Names threads after what they are, so a stack trace or a process
# listing says which part of the service is busy.
THREAD_NAME_PREFIX = 'star-pass-job'

# What a caller is told when a job failed for a reason that was not
# written for them to read.  The core's own exceptions carry a message
# meant for the person running the command and are safe to store;
# anything else is a defect whose message can carry a credential, an
# upstream body, or a volunteer's data, so it goes to the log and the
# job records this instead.
UNEXPECTED_DETAIL = (
    'The job failed unexpectedly. The reason is in the service log.'
)

# Module logger
logger = get_logger(__name__)


class JobReporter(Reporter):
    """ A reporter that records what it is told as job events.

        Every method the core reports through is recorded, so that
        nothing it said is lost between the work and whoever is
        watching.  The event's kind is the name of the method that
        reported it, which keeps the stream describing the run rather
        than describing this class.
    """

    def __init__(
            self,
            jobs: JobRepository,
            job_id: str
    ) -> None:
        """ Record against one job.

            Args:
                jobs (JobRepository):
                    Where the events are written.

                job_id (str):
                    Job the events belong to.

            Returns:
                None.
        """

        self._jobs = jobs
        self._job_id = job_id

    def _record(
            self,
            kind: str,
            **payload: Any
    ) -> None:
        """ Write one event.

            Args:
                kind (str):
                    What happened.

                **payload (Any):
                    What the event carries.

            Returns:
                None.
        """

        self._jobs.add_event(
            job_id=self._job_id,
            kind=kind,
            payload=payload
        )

        return None

    def step_started(
            self,
            step: str,
            subject: str = ''
    ) -> None:
        """ A named unit of work began.

            The step is recorded as the identifier the core reported,
            and the subject beside it, rather than as a sentence: a
            job's event log is read back over the API, and a client
            reading it words the step the way it words everything else
            the contract publishes.

            Args:
                step (str):
                    Which one, from 'STEPS'.

                subject (str, optional):
                    What it is working on, or an empty string.

            Returns:
                None.
        """

        return self._record(
            kind='step_started',
            step=step,
            subject=subject
        )

    def step_finished(self) -> None:
        """ The step most recently started completed.

            Args:
                None.

            Returns:
                None.
        """

        return self._record(kind='step_finished')

    def step_failed(self) -> None:
        """ The step most recently started did not complete.

            Recorded as well as raised: the exception ends the job, and
            this is what says which step it ended in.

            Args:
                None.

            Returns:
                None.
        """

        return self._record(kind='step_failed')

    def sending_started(
            self,
            opportunities: int
    ) -> None:
        """ The run began sending shift data to Amplify.

            Args:
                opportunities (int):
                    How many opportunities the send will work through.

            Returns:
                None.
        """

        return self._record(
            kind='sending_started',
            opportunities=opportunities
        )

    def slack_dry_run(
            self,
            payload: List[Dict[str, Any]]
    ) -> None:
        """ A Slack post was prepared but not sent.

            The blocks themselves are not recorded, only how many there
            were: a job's event log is read back over the API, and the
            rendering of a Slack message is not something a run needs
            to answer for.

            Args:
                payload (List[Dict[str, Any]]):
                    The Block Kit blocks that would have been posted.

            Returns:
                None.
        """

        return self._record(
            kind='slack_dry_run',
            blocks=len(payload or ())
        )

    def summary_skipped(self) -> None:
        """ There was nothing in the window, so nothing was posted.

            Args:
                None.

            Returns:
                None.
        """

        return self._record(kind='summary_skipped')

    def opportunity_sent(
            self,
            batch: ShiftBatch
    ) -> None:
        """ One opportunity's turn in the send is over.

            The request body is not recorded.  It is built from the
            shifts, so storing both keeps two copies of one fact, and
            the shifts are the half a reader can act on.  The need ID
            is recorded as text, so that a reader is not given a number
            by one run and a string by the next, and under the name
            the contract uses for it everywhere else: this payload
            crosses the wire to the same browser that reads 'needId'
            on every other answer.

            Args:
                batch (ShiftBatch):
                    The opportunity, what was created under it, and
                    what it already held.

            Returns:
                None.
        """

        return self._record(
            kind='opportunity_sent',
            index=batch.index,
            needId=str(batch.need_id),
            title=batch.title,
            url=batch.url,
            shifts=batch.shifts,
            skipped=batch.skipped
        )


class JobRunner:
    """ Runs a job's work on a thread and records how it ended.

        A job is asked for, queued, and picked up here; the caller is
        given an identifier rather than made to wait.  One job runs at
        a time by default, so a second waits as a queued job -- a state
        a caller can see -- rather than competing for the one writer
        SQLite and Amplify each allow.
    """

    def __init__(
            self,
            connect: Callable[[], sqlite3.Connection],
            workers: int = JOB_WORKERS
    ) -> None:
        """ Prepare to run jobs.

            Args:
                connect (Callable[[], sqlite3.Connection]):
                    Opens a connection.  Called once per job, on the
                    thread that runs it, because a connection belongs
                    to the thread that opened it.

                workers (int, optional):
                    How many jobs run at once.  Defaults to the
                    configured value.

            Returns:
                None.
        """

        self._connect = connect
        self._pool = ThreadPoolExecutor(
            max_workers=workers,
            thread_name_prefix=THREAD_NAME_PREFIX
        )

    def submit(
            self,
            job_id: str,
            work: Callable[[Reporter], None]
    ) -> 'Future[None]':
        """ Run a queued job's work, and return without waiting for it.

            Args:
                job_id (str):
                    Job to run, which must be queued.

                work (Callable[[Reporter], None]):
                    What to do, given a reporter to describe it
                    through.  It is called on a worker thread.

            Returns:
                future (Future[None]):
                    Completes when the job is over.  A caller watching
                    over the API uses the job's status and events
                    instead; this is for a caller in the same process,
                    and for shutting down in an orderly way.
        """

        return self._pool.submit(
            self._run,
            job_id,
            work
        )

    def shutdown(
            self,
            wait: bool = True
    ) -> None:
        """ Stop accepting jobs, and optionally wait for the current one.

            Args:
                wait (bool, optional):
                    Whether to wait for running jobs.  Defaults to
                    True, so that a job in hand finishes and records
                    how it ended rather than being left running for a
                    restart to find.

            Returns:
                None.
        """

        self._pool.shutdown(wait=wait)

        return None

    def _run(
            self,
            job_id: str,
            work: Callable[[Reporter], None]
    ) -> None:
        """ Start the job, do the work, and record the outcome.

            Args:
                job_id (str):
                    Job being run.

                work (Callable[[Reporter], None]):
                    What to do.

            Returns:
                None.
        """

        connection = self._connect()

        try:
            jobs = JobRepository(connection=connection)
            jobs.start(job_id=job_id)

            self._work(
                jobs=jobs,
                job_id=job_id,
                work=work
            )

        finally:
            connection.close()

        return None

    def _work(
            self,
            jobs: JobRepository,
            job_id: str,
            work: Callable[[Reporter], None]
    ) -> None:
        """ Do the work and record whether it succeeded.

            Args:
                jobs (JobRepository):
                    Where the outcome is recorded.

                job_id (str):
                    Job being run.

                work (Callable[[Reporter], None]):
                    What to do.

            Returns:
                None.
        """

        try:
            work(
                JobReporter(
                    jobs=jobs,
                    job_id=job_id
                )
            )

        except StarPassError as error:
            # Written for the person who asked for the run, and already
            # redacted, so it is what the job records.
            message = f'Job {job_id} failed: {error}'
            logger.error(message)
            jobs.finish(
                job_id=job_id,
                status=JOB_STATUS_FAILED,
                detail=str(error)
            )

        # A defect, not a condition the core expects.  Caught so that
        # the job records an ending rather than staying 'running' until
        # a restart sweeps it, and its message is kept out of what the
        # job stores.
        except Exception as error:  # pylint: disable=broad-except
            message = f'Job {job_id} failed unexpectedly: {error!r}'
            logger.exception(message)
            jobs.finish(
                job_id=job_id,
                status=JOB_STATUS_FAILED,
                detail=UNEXPECTED_DETAIL
            )

        else:
            jobs.finish(
                job_id=job_id,
                status=JOB_STATUS_SUCCEEDED
            )

        return None
