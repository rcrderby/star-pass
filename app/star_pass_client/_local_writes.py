#!/usr/bin/env python3
""" The writes, answered without a service.

    The other half of the local client, and a module of its own because
    the two halves are two things: one answers a question about what is
    stored, and this one changes it, starts a job, and reaches Amplify.

    **A local write runs in the call.**  The remote half answers as soon
    as the job exists and leaves it running; the process that would run
    a local one is the process about to return, so the work happens here
    and the job is answered as it ended.  That is a difference in when,
    not in what: the run, the job and every event the work reported are
    written exactly as the service writes them, so reading the job
    afterwards says the same things (D2).

    Every job written here is held by the command line rather than by
    the service, which is what lets each of them sweep up after itself
    without ending the other's work.

    A mixin rather than a base: 'LocalClient' is one client answering
    one contract, and splitting it into two classes a caller could hold
    separately would invite a caller to hold one.
"""

# Imports - Python Standard Library
import sqlite3
from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterator

# Imports - Local
from star_pass._collect import collect
from star_pass._database import transaction
from star_pass._defaults import GCAL_CALENDARS
from star_pass._gcal_time import resolve_window
from star_pass._job_runner import JobRunner
from star_pass._logging import get_logger
from star_pass._reading import changes_in_current
from star_pass._records import (
    JOB_HOLDER_LOCAL,
    JOB_KIND_COLLECT,
    JOB_KIND_RECOLLECT,
    JOB_KIND_SEND,
    RUN_STATUS_COLLECTING
)
from star_pass._reporting import Reporter
from star_pass._repository import (
    IdempotencyRepository,
    JobRepository,
    RunRepository
)
from star_pass._resume import work_for
from star_pass._send import claim, send
from star_pass_contract import (
    CollectRequest,
    IDEMPOTENCY_KEY_HEADER,
    no_such_job,
    no_such_run,
    RecollectRequest,
    replayed,
    resumable,
    sendable,
    SendRequest,
    to_job_view,
    why_not_delete,
    why_not_recollect
)
from ._client import ApiProblem

# Constants
# What a write that started a job is reported as.  The remote half
# answers 202 with a job still running; this one answers 202 with a job
# that has ended, because the process that would run it is the one
# about to return.  The same status either way: a caller reading the
# job afterwards is told the same things (D2).
ACCEPTED = 202

# Who a local write is recorded as (D13).  Distinct from the service's
# principal on purpose: the column exists so that two writers can be
# told apart, and a local run and a run the service collected are two
# different people acting.
LOCAL_PRINCIPAL_ID = 'local-cli'

# Module logger
logger = get_logger(__name__)


class LocalWrites:
    """ The contract's writes, carried out against the local database.

        Mixed into 'LocalClient', which supplies the connection and the
        failures these use.
    """

    # What the other half provides.  Declared rather than assumed, so
    # what this mixin needs is on the page and a checker reading this
    # file alone can see it.
    _connect_to: Callable[[], sqlite3.Connection]
    _opened: Callable[..., Any]
    _history: Callable[..., Any]
    _missing: Callable[[str], ApiProblem]
    _refused: Callable[[str], ApiProblem]
    _conflicted: Callable[[str], ApiProblem]

    @contextmanager
    def _writing(self) -> Iterator[sqlite3.Connection]:
        """ Open a connection for a write, after sweeping up.

            A command line process that stopped part way through left a
            job saying it is still running, and the run it worked on
            saying something is still working on it -- so nothing can
            be done with that run until somebody says what became of
            the job.  Ending those is what the service does at startup
            (D10), and this is the same sweep for the same reason.

            **Only the jobs this half held.**  The service and the
            command line write into one database (D2), so a sweep that
            took everything unfinished would mark a live send
            interrupted, and the run would then accept a second send
            while the first was still writing into Amplify.  What makes
            that possible is the holder on the job.

            Two command line processes at once are the case this does
            not cover: the second would end the first's job.  A local
            job runs inside the call that asked for it, so that means
            two commands writing to one database at the same moment,
            which is not something one operator at one terminal does.

            Args:
                None.

            Raises:
                ConfigurationError:
                    If the database cannot be opened.

            Yields:
                connection (sqlite3.Connection):
                    A connection of this answer's own.
        """

        with self._opened() as connection:
            with transaction(connection=connection):
                ended = JobRepository(
                    connection=connection
                ).interrupt_unfinished(held_by=JOB_HOLDER_LOCAL)

            if ended:
                message = (
                    f'Ended {ended} job(s) an earlier command left '
                    'unfinished. Resume them with "jobs resume".'
                )
                logger.warning(message)

            yield connection

    def _collect(
            self,
            body: Dict[str, Any]
    ) -> Dict[str, Any]:
        """ Create a run and collect into it, here and now.

            The remote half answers as soon as the run exists and
            leaves a job running.  This one cannot: the process that
            would run the job is the one about to return, so the work
            happens in the call and the job is answered as it ended.

            That is a difference in when, not in what.  The run, the
            job and every event the collection reported are written
            exactly as the service writes them, so reading the job
            afterwards -- or following it -- says the same things.

            Args:
                body (Dict[str, Any]):
                    Which calendar to collect, and over which days.

            Raises:
                ApiProblem:
                    If the calendar is not configured, or the window
                    does not name days a search can cover.

                StarPassError:
                    If the collection cannot be carried out.

            Returns:
                answer (Dict[str, Any]):
                    The job, as it ended.
        """

        asked = CollectRequest.model_validate(body)
        self._checked(asked=asked)

        with self._writing() as connection:
            with transaction(connection=connection):
                run = RunRepository(connection=connection).create(
                    calendar=asked.calendar,
                    window_start=asked.window.start,
                    window_end=asked.window.end
                )
                jobs = JobRepository(connection=connection)
                job = jobs.create(
                    run_id=run.id,
                    kind=JOB_KIND_COLLECT,
                    principal_id=LOCAL_PRINCIPAL_ID,
                    held_by=JOB_HOLDER_LOCAL
                )

            JobRunner(
                connect=self._connect_to,
                workers=1
            ).submit(
                job_id=job.id,
                work=lambda reporter: self._collected(
                    run_id=run.id,
                    reporter=reporter
                )
            ).result()

            return to_job_view(
                job=jobs.get(job_id=job.id)
            ).model_dump(by_alias=True, mode='json')

    def _collected(
            self,
            run_id: str,
            reporter: Reporter
    ) -> None:
        """ Collect a run on a connection of the job's own.

            Args:
                run_id (str):
                    Run to collect into.

                reporter (Reporter):
                    Where the job records what it reported.

            Raises:
                StarPassError:
                    If the collection cannot be carried out.

            Returns:
                None.
        """

        with self._opened() as connection:
            collect(
                connection=connection,
                run_id=run_id,
                reporter=reporter,
                principal_id=LOCAL_PRINCIPAL_ID
            )

        return None

    def _checked(
            self,
            asked: CollectRequest
    ) -> None:
        """ Fail on a request the service would refuse.

            The same two refusals the service makes, reported the same
            way, so a person who mistypes a calendar name is told the
            same thing in either mode (D2).

            Args:
                asked (CollectRequest):
                    What the caller asked for.

            Raises:
                ApiProblem:
                    If the calendar is not configured, or the window
                    does not name days a search can cover.

            Returns:
                None.
        """

        if asked.calendar not in GCAL_CALENDARS:
            raise self._refused(
                detail=(
                    f'"{asked.calendar}" is not a calendar this '
                    'service reads. Use one of: '
                    f'{", ".join(sorted(GCAL_CALENDARS))}.'
                )
            )

        try:
            resolve_window(
                start=asked.window.start,
                end=asked.window.end,
                start_name='The window start',
                end_name='the window end'
            )

        except ValueError as error:
            raise self._refused(detail=str(error)) from error

        return None

    def _delete(
            self,
            run_id: str
    ) -> None:
        """ Delete a run, here and now.

            The same two refusals the service makes, for the same
            reasons, because housekeeping has to work with no server
            running (D2, D24).

            Args:
                run_id (str):
                    Run to delete.

            Raises:
                ApiProblem:
                    If there is no such run, or it is not one that may
                    be deleted.

            Returns:
                None:
                    Nothing, which is what a 204 carries.
        """

        with self._writing() as connection:
            runs = RunRepository(connection=connection)
            run = runs.get(run_id=run_id)

            if run is None:
                raise self._missing(detail=no_such_run(run_id=run_id))

            refusal = why_not_delete(run=run)

            if refusal is not None:
                raise self._conflicted(detail=refusal)

            runs.delete(run_id=run_id)

        return None

    def _recollect(
            self,
            run_id: str,
            body: Dict[str, Any]
    ) -> Dict[str, Any]:
        """ Collect a run's window again, here and now.

            The same three refusals the service makes, and the same
            work, run in the call for the same reason a first
            collection is (D2).

            Args:
                run_id (str):
                    Run to collect again.

                body (Dict[str, Any]):
                    How many changes the operator was told would be
                    discarded.

            Raises:
                ApiProblem:
                    If there is no such run, or it is not one a
                    recollection may replace.

                StarPassError:
                    If the collection cannot be carried out.

            Returns:
                answer (Dict[str, Any]):
                    The job, as it ended.
        """

        asked = RecollectRequest.model_validate(body)

        with self._writing() as connection:
            run, revisions = self._history(
                connection=connection,
                run_id=run_id
            )
            refusal = why_not_recollect(
                run=run,
                changed=changes_in_current(
                    run=run,
                    revisions=revisions
                ),
                expected=asked.expected_change_count
            )

            if refusal is not None:
                raise self._conflicted(detail=refusal)

            with transaction(connection=connection):
                RunRepository(connection=connection).set_status(
                    run_id=run_id,
                    status=RUN_STATUS_COLLECTING
                )
                jobs = JobRepository(connection=connection)
                job = jobs.create(
                    run_id=run_id,
                    kind=JOB_KIND_RECOLLECT,
                    principal_id=LOCAL_PRINCIPAL_ID,
                    held_by=JOB_HOLDER_LOCAL
                )

            JobRunner(
                connect=self._connect_to,
                workers=1
            ).submit(
                job_id=job.id,
                work=lambda reporter: self._collected(
                    run_id=run_id,
                    reporter=reporter
                )
            ).result()

            return to_job_view(
                job=jobs.get(job_id=job.id)
            ).model_dump(by_alias=True, mode='json')

    def _send(
            self,
            run_id: str,
            body: Dict[str, Any],
            headers: Dict[str, str]
    ) -> Dict[str, Any]:
        """ Send a run's outstanding shifts to Amplify, here and now.

            The same four refusals the service makes, the same claim on
            the idempotency key, and the same work -- run in the call
            for the reason a local collection is (D2).  A local send is
            recorded as 'local-cli' rather than as the service's
            principal, because two writers into one live volunteer
            system are two different people acting (D13).

            Args:
                run_id (str):
                    Run to send.

                body (Dict[str, Any]):
                    How many shifts the operator was told would be
                    created.

                headers (Dict[str, str]):
                    Carries the key this attempt is claimed under.

            Raises:
                ApiProblem:
                    If there is no such run, it is not one that may be
                    sent, or the key carries a different request.

                StarPassError:
                    If the send cannot be carried out.

            Returns:
                answer (Dict[str, Any]):
                    The job, as it ended.
        """

        asked = SendRequest.model_validate(body)
        key = headers[IDEMPOTENCY_KEY_HEADER]

        with self._writing() as connection:
            self._refused_send(
                connection=connection,
                run_id=run_id,
                expected=asked.expected_shift_count
            )
            existing, job = claim(
                connection=connection,
                run_id=run_id,
                key=key,
                fingerprint=asked.fingerprint(),
                principal_id=LOCAL_PRINCIPAL_ID,
                held_by=JOB_HOLDER_LOCAL
            )

            if existing is not None:
                return replayed(
                    record=existing,
                    run_id=run_id,
                    fingerprint=asked.fingerprint(),
                    refuse=self._refused,
                    conflict=self._conflicted
                )

            JobRunner(
                connect=self._connect_to,
                workers=1
            ).submit(
                job_id=job.id,
                work=lambda reporter: self._sent(
                    run_id=run_id,
                    reporter=reporter,
                    key=key
                )
            ).result()

            answer = to_job_view(
                job=JobRepository(connection=connection).get(job_id=job.id)
            ).model_dump(by_alias=True, mode='json')

            IdempotencyRepository(connection=connection).complete(
                operation=JOB_KIND_SEND,
                key=key,
                status_code=ACCEPTED,
                response=answer
            )

            return answer

    def _refused_send(
            self,
            connection: sqlite3.Connection,
            run_id: str,
            expected: int
    ) -> None:
        """ Fail on a send the service would refuse.

            The decision is the shared one, so the two modes cannot
            refuse different things about one run (D2).  Only what a
            refusal is reported as belongs to this half.

            Args:
                connection (sqlite3.Connection):
                    The database to read.

                run_id (str):
                    Run to send.

                expected (int):
                    How many shifts the caller was shown.

            Raises:
                ApiProblem:
                    If there is no such run, or it is not one that may
                    be sent.

            Returns:
                None.
        """

        found = sendable(
            connection=connection,
            run_id=run_id,
            expected=expected
        )

        if found is None:
            raise self._missing(detail=no_such_run(run_id=run_id))

        _run, refusal = found

        if refusal is not None:
            raise self._conflicted(detail=refusal)

        return None

    def _sent(
            self,
            run_id: str,
            reporter: Reporter,
            key: str
    ) -> None:
        """ Send a run on a connection of the job's own.

            Args:
                run_id (str):
                    Run to send.

                reporter (Reporter):
                    Where the job records what it reported.

                key (str):
                    The key the send is made under (D13).

            Raises:
                StarPassError:
                    If the send cannot be carried out.

            Returns:
                None.
        """

        with self._opened() as connection:
            send(
                connection=connection,
                run_id=run_id,
                reporter=reporter,
                principal_id=LOCAL_PRINCIPAL_ID,
                idempotency_key=key
            )

        return None

    def _resume(
            self,
            job_id: str
    ) -> Dict[str, Any]:
        """ Run an interrupted job again, here and now (D10).

            The same two refusals the service makes, and the same work
            chosen the same way, run in the call for the reason a local
            collection is (D2).  The job passes into this half's hands
            as it is queued, so a later sweep by this half recognizes
            it and one by the service leaves it alone.

            Args:
                job_id (str):
                    Job to run again.

            Raises:
                ApiProblem:
                    If there is no such job, or it is not one that may
                    be resumed.

                StarPassError:
                    If the work cannot be carried out.

            Returns:
                answer (Dict[str, Any]):
                    The job, as it ended.
        """

        with self._writing() as connection:
            found = resumable(connection=connection, job_id=job_id)

            if found is None:
                raise self._missing(detail=no_such_job(job_id=job_id))

            job, refusal = found

            if refusal is not None:
                raise self._conflicted(detail=refusal)

            jobs = JobRepository(connection=connection)
            jobs.requeue(job_id=job.id, held_by=JOB_HOLDER_LOCAL)

            work = work_for(job=job, principal_id=LOCAL_PRINCIPAL_ID)

            JobRunner(
                connect=self._connect_to,
                workers=1
            ).submit(
                job_id=job.id,
                work=lambda reporter: self._resumed(
                    work=work,
                    reporter=reporter
                )
            ).result()

            return to_job_view(
                job=jobs.get(job_id=job.id)
            ).model_dump(by_alias=True, mode='json')

    def _resumed(
            self,
            work: Callable[..., None],
            reporter: Reporter
    ) -> None:
        """ Run resumed work on a connection of the job's own.

            Args:
                work (Callable[..., None]):
                    What resuming the job runs.

                reporter (Reporter):
                    Where the job records what it reported.

            Raises:
                StarPassError:
                    If the work cannot be carried out.

            Returns:
                None.
        """

        with self._opened() as connection:
            work(connection, reporter)

        return None
