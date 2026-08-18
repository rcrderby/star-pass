#!/usr/bin/env python3
""" Long operations, and what they reported while they ran. """

# Imports - Python Standard Library
import json
import sqlite3
from typing import Any, Dict, List, Optional
from uuid import uuid4

# Imports - Local
from .._database import execute, query, query_one
from .._logging import get_logger
from .._records import (
    Job,
    JobEvent,
    JOB_HOLDER_SERVICE,
    JOB_HOLDERS,
    JOB_KINDS,
    JOB_STATUS_INTERRUPTED,
    JOB_STATUS_QUEUED,
    JOB_STATUS_RUNNING,
    JOB_STATUSES_FINISHED,
    JOB_STATUSES_UNFINISHED
)
from ._common import (
    insert_statement,
    Repository,
    require_one_of,
    require_row,
    utc_now
)

# Constants
JOB_COLUMNS = (
    'id',
    'run_id',
    'kind',
    'status',
    'principal_id',
    'held_by',
    'created_at'
)

# Module logger
logger = get_logger(__name__)


def _to_job(
        row: sqlite3.Row
) -> Job:
    """ Build a job record from a row.

        Args:
            row (sqlite3.Row):
                A row from the jobs table.

        Returns:
            job (Job):
                The job the row describes.
    """

    return Job(
        id=row['id'],
        run_id=row['run_id'],
        kind=row['kind'],
        status=row['status'],
        principal_id=row['principal_id'],
        held_by=row['held_by'],
        created_at=row['created_at'],
        started_at=row['started_at'],
        finished_at=row['finished_at'],
        detail=row['detail']
    )


def _to_job_event(
        row: sqlite3.Row
) -> JobEvent:
    """ Build a job event record from a row.

        Args:
            row (sqlite3.Row):
                A row from the job events table.

        Returns:
            event (JobEvent):
                The event the row describes.
    """

    return JobEvent(
        id=row['id'],
        job_id=row['job_id'],
        recorded_at=row['recorded_at'],
        kind=row['kind'],
        payload=json.loads(row['payload'])
    )


class JobRepository(Repository):
    """ Jobs, and the events each one recorded.

        A status change is a conditional update rather than a read
        followed by a write: two requests arriving together would both
        read 'queued' and both start the same job, and the condition is
        what makes the second one fail instead.
    """

    def create(
            self,
            run_id: str,
            kind: str,
            principal_id: str,
            held_by: str = JOB_HOLDER_SERVICE
    ) -> Job:
        """ Record a job that has been asked for but not begun.

            Args:
                run_id (str):
                    Run the job works on.

                kind (str):
                    One of 'JOB_KINDS'.

                principal_id (str):
                    Who asked for it.

                held_by (str, optional):
                    Which of 'JOB_HOLDERS' will run it.  Defaults to
                    the service, which is what wrote every job before
                    the column existed, so a caller that does not say
                    is recorded as what it would have been.

            Raises:
                ValidationError:
                    If the kind or the holder is not one a job can
                    have, or there is no such run.

                UpstreamError:
                    If the job cannot be written.

            Returns:
                job (Job):
                    The job as stored, queued and not yet started.
        """

        require_one_of(
            value=kind,
            allowed=JOB_KINDS,
            description='a job kind'
        )
        require_one_of(
            value=held_by,
            allowed=JOB_HOLDERS,
            description='something that can hold a job'
        )

        job_id = uuid4().hex
        created_at = utc_now()

        execute(
            connection=self._connection,
            statement=insert_statement(
                table='jobs',
                columns=JOB_COLUMNS
            ),
            parameters=(
                job_id,
                run_id,
                kind,
                JOB_STATUS_QUEUED,
                principal_id,
                held_by,
                created_at
            )
        )

        message = f'Queued {kind} job {job_id} for run {run_id}'
        logger.debug(message)

        return Job(
            id=job_id,
            run_id=run_id,
            kind=kind,
            status=JOB_STATUS_QUEUED,
            principal_id=principal_id,
            held_by=held_by,
            created_at=created_at
        )

    def get(
            self,
            job_id: str
    ) -> Optional[Job]:
        """ Return one job.

            Args:
                job_id (str):
                    Identifier of the job to read.

            Raises:
                UpstreamError:
                    If the job cannot be read.

            Returns:
                job (Job | None):
                    The job, or None when there is no such job.
        """

        row = query_one(
            connection=self._connection,
            statement='SELECT * FROM jobs WHERE id = ?',
            parameters=(job_id,)
        )

        return _to_job(row=row) if row is not None else None

    def list_for_run(
            self,
            run_id: str
    ) -> List[Job]:
        """ Return a run's jobs, most recently asked for first.

            Args:
                run_id (str):
                    Run to read the jobs of.

            Raises:
                UpstreamError:
                    If they cannot be read.

            Returns:
                jobs (List[Job]):
                    Every job for the run, newest first.
        """

        rows = query(
            connection=self._connection,
            statement=(
                'SELECT * FROM jobs WHERE run_id = ? '
                'ORDER BY created_at DESC, id'
            ),
            parameters=(run_id,)
        )

        return [_to_job(row=row) for row in rows]

    def start(
            self,
            job_id: str
    ) -> None:
        """ Record that a queued job has begun.

            Only a queued job starts.  A job already running has
            somebody running it, and a finished one is over; either way
            starting it again would produce a second worker writing the
            same events.

            Args:
                job_id (str):
                    Identifier of the job to start.

            Raises:
                ValidationError:
                    If there is no such job, or it is not queued.

                UpstreamError:
                    If the job cannot be updated.

            Returns:
                None.
        """

        cursor = execute(
            connection=self._connection,
            statement=(
                'UPDATE jobs SET status = ?, started_at = ? '
                'WHERE id = ? AND status = ?'
            ),
            parameters=(
                JOB_STATUS_RUNNING,
                utc_now(),
                job_id,
                JOB_STATUS_QUEUED
            )
        )

        require_row(
            cursor=cursor,
            message=(
                f'Job "{job_id}" cannot be started: there is no such '
                'job, or it is not queued.'
            )
        )

        return None

    def finish(
            self,
            job_id: str,
            status: str,
            detail: Optional[str] = None
    ) -> None:
        """ Record that a running job is over.

            Args:
                job_id (str):
                    Identifier of the job that finished.

                status (str):
                    How it ended: one of 'JOB_STATUSES_FINISHED'.

                detail (str, optional):
                    Why it failed, as a summary safe to show a caller.
                    Defaults to None.  An upstream body or a traceback
                    belongs in the log, not here: this is read back
                    over the API.

            Raises:
                ValidationError:
                    If the status is not one a job finishes in, or the
                    job is not running.

                UpstreamError:
                    If the job cannot be updated.

            Returns:
                None.
        """

        require_one_of(
            value=status,
            allowed=JOB_STATUSES_FINISHED,
            description='a status a job finishes in'
        )

        cursor = execute(
            connection=self._connection,
            statement=(
                'UPDATE jobs SET status = ?, finished_at = ?, '
                'detail = ? WHERE id = ? AND status = ?'
            ),
            parameters=(
                status,
                utc_now(),
                detail,
                job_id,
                JOB_STATUS_RUNNING
            )
        )

        require_row(
            cursor=cursor,
            message=(
                f'Job "{job_id}" cannot be finished: there is no such '
                'job, or it is not running.'
            )
        )

        return None

    def interrupt_unfinished(
            self,
            held_by: str = JOB_HOLDER_SERVICE
    ) -> int:
        """ End every unfinished job one holder was left with.

            Called while a process starts.  A job left queued or
            running belongs to a process that no longer exists, so
            without this it stays that way for good and a caller
            watching it waits for something nothing is doing.

            Scoped to one holder, and that is the whole point of the
            column.  The service and the command line write into one
            database (D2), so a sweep that took everything unfinished
            would let a command line run mark a live send interrupted
            -- and the run it belonged to would then accept a second
            send while the first was still writing into Amplify.

            Marked interrupted rather than failed: nothing observed a
            failure, and rather than resumed, because resuming is a
            human action (D10).

            Args:
                held_by (str, optional):
                    Which of 'JOB_HOLDERS' to sweep after.  Defaults to
                    the service.

            Raises:
                ValidationError:
                    If the holder is not one a job can have.

                UpstreamError:
                    If the jobs cannot be updated.

            Returns:
                count (int):
                    How many jobs were ended.
        """

        require_one_of(
            value=held_by,
            allowed=JOB_HOLDERS,
            description='something that can hold a job'
        )

        # An 'IN' list has one placeholder per value and SQLite has no
        # way to bind a whole list, so the placeholders are counted out
        # here.  What is interpolated is question marks and commas; the
        # statuses themselves bind like every other value.
        placeholders = ', '.join('?' * len(JOB_STATUSES_UNFINISHED))

        cursor = execute(
            connection=self._connection,
            statement=(
                # What is interpolated is the placeholders counted out
                # above; every value below binds.
                'UPDATE jobs SET status = ?, finished_at = ? '  # nosec B608
                f'WHERE held_by = ? AND status IN ({placeholders})'
            ),
            parameters=(
                JOB_STATUS_INTERRUPTED,
                utc_now(),
                held_by,
                *JOB_STATUSES_UNFINISHED
            )
        )
        count = cursor.rowcount

        if count:
            message = (
                f'Marked {count} unfinished job(s) held by {held_by} '
                'interrupted'
            )
            logger.warning(message)

        return count

    def requeue(
            self,
            job_id: str,
            held_by: str = JOB_HOLDER_SERVICE
    ) -> None:
        """ Put an interrupted job back in the queue (D10).

            Only an interrupted job.  A failed one was observed to
            fail and a succeeded one is over; queueing either again
            would be starting new work under the identifier of work
            that already ended, and the job's own record of when it
            began and how it went would then describe two runs of it.

            The holder is written again, because the process resuming
            the job is not the one that was holding it, and it is the
            new holder that a later sweep has to recognize.

            Args:
                job_id (str):
                    Identifier of the job to queue again.

                held_by (str, optional):
                    Which of 'JOB_HOLDERS' will run it now.  Defaults
                    to the service.

            Raises:
                ValidationError:
                    If the holder is not one a job can have, or there
                    is no such job, or it is not interrupted.

                UpstreamError:
                    If the job cannot be updated.

            Returns:
                None.
        """

        require_one_of(
            value=held_by,
            allowed=JOB_HOLDERS,
            description='something that can hold a job'
        )

        cursor = execute(
            connection=self._connection,
            statement=(
                'UPDATE jobs SET status = ?, held_by = ?, '
                'started_at = NULL, finished_at = NULL, detail = NULL '
                'WHERE id = ? AND status = ?'
            ),
            parameters=(
                JOB_STATUS_QUEUED,
                held_by,
                job_id,
                JOB_STATUS_INTERRUPTED
            )
        )

        require_row(
            cursor=cursor,
            message=(
                f'Job "{job_id}" cannot be resumed: there is no such '
                'job, or it is not one that was interrupted.'
            )
        )

        return None

    def add_event(
            self,
            job_id: str,
            kind: str,
            payload: Optional[Dict[str, Any]] = None
    ) -> JobEvent:
        """ Record something a job reported.

            Args:
                job_id (str):
                    Job that reported it.

                kind (str):
                    What happened.

                payload (Dict[str, Any], optional):
                    What the event carries.  Defaults to None, for an
                    event that is only its kind.

            Raises:
                ValidationError:
                    If there is no such job.

                UpstreamError:
                    If the event cannot be written.

            Returns:
                event (JobEvent):
                    The event as stored, with the identifier it was
                    given.
        """

        recorded_at = utc_now()
        members = payload or {}

        cursor = execute(
            connection=self._connection,
            statement=insert_statement(
                table='job_events',
                columns=('job_id', 'recorded_at', 'kind', 'payload')
            ),
            parameters=(
                job_id,
                recorded_at,
                kind,
                json.dumps(members, sort_keys=True)
            )
        )

        return JobEvent(
            id=cursor.lastrowid or 0,
            job_id=job_id,
            recorded_at=recorded_at,
            kind=kind,
            payload=members
        )

    def forget_events_before(
            self,
            cutoff: str
    ) -> int:
        """ Delete the event logs of jobs that finished before a time.

            What the retention window is protecting is here rather
            than on the job row (D12): an event log names volunteers
            and the times they were asked to be somewhere, while the
            row says only that a job of some kind ran and how it
            ended.  So the log goes and the row stays, and a run's
            history still says a send happened without still saying
            who it was for.

            A job that has not finished is left alone whatever its
            age.  One still running is one somebody may be watching,
            and its log is the thing they are watching.

            Args:
                cutoff (str):
                    ISO-8601 UTC timestamp.  Logs of jobs that
                    finished before this are removed.

            Raises:
                UpstreamError:
                    If the events cannot be removed.

            Returns:
                removed (int):
                    How many events were deleted.
        """

        cursor = execute(
            connection=self._connection,
            statement=(
                'DELETE FROM job_events WHERE job_id IN ('
                '    SELECT id FROM jobs '
                '    WHERE finished_at IS NOT NULL AND finished_at < ?'
                ')'
            ),
            parameters=(cutoff,)
        )

        return cursor.rowcount

    def events(
            self,
            job_id: str,
            after: int = 0
    ) -> List[JobEvent]:
        """ Return what a job reported, oldest first.

            Args:
                job_id (str):
                    Job to read the events of.

                after (int, optional):
                    Return only events later than this identifier.
                    Defaults to 0, which returns all of them.  A client
                    that reconnects passes the last one it saw, so the
                    stream continues instead of repeating.

            Raises:
                UpstreamError:
                    If the events cannot be read.

            Returns:
                events (List[JobEvent]):
                    The matching events, in the order they happened.
        """

        rows = query(
            connection=self._connection,
            statement=(
                'SELECT * FROM job_events '
                'WHERE job_id = ? AND id > ? ORDER BY id'
            ),
            parameters=(job_id, after)
        )

        return [_to_job_event(row=row) for row in rows]
