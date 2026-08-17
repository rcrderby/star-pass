#!/usr/bin/env python3
""" The same operations, answered without a service.

    The command line client calls the core in-process by default and
    reaches a service only when told to (D2).  This is the default
    half: the operations the contract publishes, answered from the
    database this process can already open.

    It inherits the same generated operations the remote client does,
    so the two cannot offer different methods -- the surface is
    generated from the contract once and both halves supply a way to
    answer it.  What differs is only how an answer is reached: one
    sends a request, the other opens a connection.

    The answers themselves are built by 'star_pass_contract', the same
    module the service builds its responses with, and returned in the
    same shape a decoded response has.  That is what makes the two
    modes comparable rather than merely similar, and
    'tests/test_local_client.py' compares them.

    An operation with no local answer says so by name rather than
    returning something plausible.  When a write endpoint arrives it
    will appear here as a method that raises until it is implemented,
    which is a failing test rather than a silent difference.
"""

# Imports - Python Standard Library
import sqlite3
from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterator, List, Optional

# Imports - Local
from __version__ import __version__
from star_pass._collect import collect
from star_pass._job_runner import JobRunner
from star_pass._database import connect, transaction
from star_pass._defaults import GCAL_CALENDARS
from star_pass._gcal_time import resolve_window
from star_pass._opportunities import shifts_in_amplify
from star_pass._reading import (
    changes_in_current,
    read_run_detail,
    read_run_for_send,
    read_run_history
)
from star_pass._records import (
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
from star_pass._send import claim, send
from star_pass_contract import (
    CollectRequest,
    IDEMPOTENCY_KEY_HEADER,
    no_such_job,
    no_such_run,
    RecollectRequest,
    replayed,
    sendable,
    SendRequest,
    to_detail_view,
    to_job_view,
    to_preview_view,
    to_revision_views,
    to_run_view,
    why_not_recollect
)
from ._calling import Operation, OperationCaller
from ._client import ApiProblem
from ._operations import Operations
from ._stream import StreamEvent

# Constants
# Which handler answers which operation.  Keyed on what the generated
# methods pass, so an operation whose path changes in the contract
# stops matching here rather than quietly answering the wrong thing.
HANDLERS = {
    ('GET', '/v1/version'): '_version',
    ('POST', '/v1/runs'): '_collect',
    ('POST', '/v1/runs/{run_id}/recollect'): '_recollect',
    ('POST', '/v1/runs/{run_id}/send'): '_send',
    ('GET', '/v1/runs'): '_runs',
    ('GET', '/v1/runs/{run_id}'): '_run',
    ('GET', '/v1/runs/{run_id}/revisions'): '_revisions',
    ('GET', '/v1/runs/{run_id}/preview'): '_preview',
    ('GET', '/v1/jobs/{job_id}'): '_job'
}

# Operations that have no local answer, and why.  Listed rather than
# left to fail as a missing key, so that what the local mode cannot do
# is a statement in the source and a test can hold the list to exactly
# what is unimplemented.
UNAVAILABLE = {
    (
        'GET', '/v1/health'
    ): (
        'Health reports that a service process is serving, for a proxy '
        'deciding whether to route to it. Nothing is serving in local '
        'mode, so there is nothing for it to report.'
    ),
    (
        'GET', '/v1/jobs/{job_id}/events'
    ): (
        'Following a job as it runs is not available in local mode '
        'yet. Read the job instead.'
    )
}

# What a missing answer is reported as.  A 404 is the closest thing the
# contract has to "there is nothing here", and reporting it the same
# way the service does is what lets a caller handle both modes with
# one branch.
NOT_FOUND = 404
NOT_FOUND_TITLE = 'Not Found'

# What a run that is not in a state to be asked is reported as.
CONFLICT = 409
CONFLICT_TITLE = 'Conflict'

# What a write that started a job is reported as.  The remote half
# answers 202 with a job still running; this one answers 202 with a job
# that has ended, because the process that would run it is the one
# about to return.  The same status either way: a caller reading the
# job afterwards is told the same things (D2).
ACCEPTED = 202

# What a request the service would refuse is reported as, so that a
# caller handling one mode has handled both.
UNPROCESSABLE = 422
UNPROCESSABLE_TITLE = 'Unprocessable Entity'

# Who a local write is recorded as (D13).  Distinct from the service's
# principal on purpose: the column exists so that two writers can be
# told apart, and a local run and a run the service collected are two
# different people acting.
LOCAL_PRINCIPAL_ID = 'local-cli'


class LocalOperationUnavailable(Exception):
    """ An operation the contract publishes that local mode cannot answer.

        Raised by name rather than answered with something plausible:
        a local mode that invented an answer would be a difference
        between the modes that nobody could see.
    """


class LocalClient(OperationCaller, Operations):
    """ The contract's operations, answered from the local database.

        Holds no connection.  One is opened for each answer and closed
        again, because a connection belongs to the thread that opened
        it and a caller may be doing more than one thing.
    """

    def __init__(
            self,
            connect_to: Optional[Callable[[], sqlite3.Connection]] = None
    ) -> None:
        """ Point the client at a database.

            Args:
                connect_to (Callable[[], sqlite3.Connection], optional):
                    How to open a connection.  Defaults to None, which
                    opens the configured database.  A factory rather
                    than a connection: a connection belongs to the
                    thread that opened it.

            Returns:
                None.
        """

        self._connect_to = connect_to if connect_to is not None else connect

    @contextmanager
    def _opened(self) -> Iterator[sqlite3.Connection]:
        """ Open a connection for one answer and close it again.

            Args:
                None.

            Raises:
                ConfigurationError:
                    If the database cannot be opened.

            Yields:
                connection (sqlite3.Connection):
                    A connection of this answer's own.
        """

        connection = self._connect_to()

        try:
            yield connection

        finally:
            connection.close()

    def _answer(
            self,
            operation: Operation
    ) -> Any:
        """ Answer one operation from the database.

            Nothing here speaks HTTP, so the headers are handed to the
            handler as values rather than sent: an idempotency key
            means the same thing to a local write as to a remote one,
            which is the point of D2.

            Args:
                operation (Operation):
                    The call a generated method made.

            Raises:
                LocalOperationUnavailable:
                    If the operation has no local answer.

                ApiProblem:
                    If what was asked for is not there.

            Returns:
                answer (Any):
                    The same shape a decoded response carries.
        """

        published = (operation.method, operation.path)

        if published in UNAVAILABLE:
            raise LocalOperationUnavailable(UNAVAILABLE[published])

        if published not in HANDLERS:
            raise LocalOperationUnavailable(
                f'{operation.method} {operation.path} has no local '
                'answer.'
            )

        asked = dict(operation.parameters)

        if operation.body is not None:
            asked['body'] = operation.body

        if operation.headers is not None:
            asked['headers'] = operation.headers

        return getattr(self, HANDLERS[published])(**asked)

    def _stream(
            self,
            method: str,
            path: str,
            **parameters: Any
    ) -> Iterator[StreamEvent]:
        """ Refuse to follow an operation over time, locally.

            Args:
                method (str):
                    The HTTP method the contract publishes it under.

                path (str):
                    The templated path it is published at.

                **parameters (Any):
                    Values the path names.

            Raises:
                LocalOperationUnavailable:
                    Always: nothing streamed has a local answer yet.

            Yields:
                Nothing.
        """

        del parameters

        raise LocalOperationUnavailable(
            UNAVAILABLE.get(
                (method, path),
                f'{method} {path} has no local answer.'
            )
        )

    def _missing(
            self,
            detail: str
    ) -> ApiProblem:
        """ Return the failure for something that is not there.

            The same failure the remote client raises for the same
            question, so a caller handles one mode and has handled
            both.

            Args:
                detail (str):
                    What to tell the caller.

            Returns:
                error (ApiProblem):
                    A not-found failure carrying that reason.
        """

        del self

        return ApiProblem(
            status=NOT_FOUND,
            document={
                'title': NOT_FOUND_TITLE,
                'status': NOT_FOUND,
                'detail': detail
            }
        )

    def _version(self) -> Dict[str, Any]:
        """ Return which version is running.

            Args:
                None.

            Returns:
                answer (Dict[str, Any]):
                    The running version.
        """

        del self

        return {'version': __version__}

    def _runs(self) -> List[Dict[str, Any]]:
        """ Return every run, newest first.

            Args:
                None.

            Returns:
                answer (List[Dict[str, Any]]):
                    The runs.
        """

        with self._opened() as connection:
            return [
                to_run_view(run=run).model_dump(
                    by_alias=True,
                    mode='json'
                )
                for run in RunRepository(
                    connection=connection
                ).list_all()
            ]

    def _run(
            self,
            run_id: str
    ) -> Dict[str, Any]:
        """ Return one run and everything shown beside it.

            Args:
                run_id (str):
                    Run to read.

            Raises:
                ApiProblem:
                    If there is no such run.

            Returns:
                answer (Dict[str, Any]):
                    The run in full.
        """

        with self._opened() as connection:
            detail = read_run_detail(
                connection=connection,
                run_id=run_id
            )

        if detail is None:
            raise self._missing(detail=no_such_run(run_id=run_id))

        return to_detail_view(detail=detail).model_dump(
            by_alias=True,
            mode='json'
        )

    def _revisions(
            self,
            run_id: str
    ) -> List[Dict[str, Any]]:
        """ Return a run's revisions, oldest first.

            Args:
                run_id (str):
                    Run to read the history of.

            Raises:
                ApiProblem:
                    If there is no such run.

            Returns:
                answer (List[Dict[str, Any]]):
                    The revisions.
        """

        with self._opened() as connection:
            history = read_run_history(
                connection=connection,
                run_id=run_id
            )

        if history is None:
            raise self._missing(detail=no_such_run(run_id=run_id))

        run, revisions = history

        return [
            view.model_dump(by_alias=True, mode='json')
            for view in to_revision_views(run=run, revisions=revisions)
        ]

    def _preview(
            self,
            run_id: str
    ) -> Dict[str, Any]:
        """ Return what sending the run's current revision would create.

            Args:
                run_id (str):
                    Run to preview.

            Raises:
                ApiProblem:
                    If there is no such run.

                UpstreamError:
                    If an opportunity cannot be read.  A preview that
                    answered anyway would report every shift as new.

            Returns:
                answer (Dict[str, Any]):
                    What a send would do.
        """

        with self._opened() as connection:
            gathered = read_run_for_send(
                connection=connection,
                run_id=run_id
            )

        if gathered is None:
            raise self._missing(detail=no_such_run(run_id=run_id))

        events, opportunities = gathered

        return to_preview_view(
            events=events,
            opportunities=opportunities,
            existing=shifts_in_amplify(events=events)
        ).model_dump(by_alias=True, mode='json')

    def _job(
            self,
            job_id: str
    ) -> Dict[str, Any]:
        """ Return where a job has got to.

            Args:
                job_id (str):
                    Job to read.

            Raises:
                ApiProblem:
                    If there is no such job.

            Returns:
                answer (Dict[str, Any]):
                    The job.
        """

        with self._opened() as connection:
            job = JobRepository(connection=connection).get(job_id=job_id)

            if job is None:
                raise self._missing(detail=no_such_job(job_id=job_id))

            return to_job_view(job=job).model_dump(
                by_alias=True,
                mode='json'
            )

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

        with self._opened() as connection:
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
                    principal_id=LOCAL_PRINCIPAL_ID
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
                reporter=reporter
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

    def _refused(
            self,
            detail: str
    ) -> ApiProblem:
        """ Return the failure for a request that will not be carried out.

            Args:
                detail (str):
                    What to tell the caller.

            Returns:
                error (ApiProblem):
                    An unprocessable-entity failure carrying that
                    reason.
        """

        del self

        return ApiProblem(
            status=UNPROCESSABLE,
            document={
                'title': UNPROCESSABLE_TITLE,
                'status': UNPROCESSABLE,
                'detail': detail
            }
        )

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

        with self._opened() as connection:
            history = read_run_history(
                connection=connection,
                run_id=run_id
            )

            if history is None:
                raise self._missing(detail=no_such_run(run_id=run_id))

            run, revisions = history
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
                    principal_id=LOCAL_PRINCIPAL_ID
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

    def _conflicted(
            self,
            detail: str
    ) -> ApiProblem:
        """ Return the failure for a run not in a state to be asked.

            Args:
                detail (str):
                    What to tell the caller.

            Returns:
                error (ApiProblem):
                    A conflict carrying that reason.
        """

        del self

        return ApiProblem(
            status=CONFLICT,
            document={
                'title': CONFLICT_TITLE,
                'status': CONFLICT,
                'detail': detail
            }
        )

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

        with self._opened() as connection:
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
                principal_id=LOCAL_PRINCIPAL_ID
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
