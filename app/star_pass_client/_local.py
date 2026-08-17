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
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

# Imports - Local
from __version__ import __version__
from star_pass._database import connect
from star_pass._opportunities import shifts_in_amplify
from star_pass._reading import (
    read_run_detail,
    read_run_for_send,
    read_run_history,
    read_run_uncollected
)
from star_pass._records import Revision, Run
from star_pass._repository import JobRepository, RunRepository
from star_pass_contract import (
    no_such_job,
    no_such_run,
    to_detail_view,
    to_job_view,
    to_preview_view,
    to_revision_views,
    to_run_view,
    to_uncollected_views
)
from ._calling import Operation, OperationCaller
from ._client import ApiProblem
from ._local_writes import LocalWrites
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
    ('POST', '/v1/jobs/{job_id}/resume'): '_resume',
    ('GET', '/v1/runs'): '_runs',
    ('GET', '/v1/runs/{run_id}'): '_run',
    ('GET', '/v1/runs/{run_id}/revisions'): '_revisions',
    ('GET', '/v1/runs/{run_id}/uncollected'): '_uncollected',
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
    ),
    (
        'PATCH', '/v1/runs/{run_id}/events'
    ): (
        'Editing a run is done in the web interface, which is what has '
        'the run in front of it. The command line collects, reads and '
        'sends (D2).'
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

# What a request the service would refuse is reported as, so that a
# caller handling one mode has handled both.
UNPROCESSABLE = 422
UNPROCESSABLE_TITLE = 'Unprocessable Entity'


class LocalOperationUnavailable(Exception):
    """ An operation the contract publishes that local mode cannot answer.

        Raised by name rather than answered with something plausible:
        a local mode that invented an answer would be a difference
        between the modes that nobody could see.
    """


class LocalClient(OperationCaller, LocalWrites, Operations):
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

    def _history(
            self,
            connection: sqlite3.Connection,
            run_id: str
    ) -> Tuple[Run, List[Revision]]:
        """ Read a run and its revisions, or say there is no such run.

            Both halves of this client read a run's history and both
            answer a missing one the same way, so the pair is read
            here.  Two copies would be two chances to answer a missing
            run with something other than a not-found.

            Args:
                connection (sqlite3.Connection):
                    The database to read.

                run_id (str):
                    Run to read the history of.

            Raises:
                ApiProblem:
                    If there is no such run.

            Returns:
                history (Tuple[Run, List[Revision]]):
                    The run and its revisions, oldest first.
        """

        history = read_run_history(
            connection=connection,
            run_id=run_id
        )

        if history is None:
            raise self._missing(detail=no_such_run(run_id=run_id))

        return history

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
            run, revisions = self._history(
                connection=connection,
                run_id=run_id
            )

        return [
            view.model_dump(by_alias=True, mode='json')
            for view in to_revision_views(run=run, revisions=revisions)
        ]

    def _uncollected(
            self,
            run_id: str
    ) -> List[Dict[str, Any]]:
        """ Return what the run's window held and the run left out.

            Answered locally rather than declared unavailable: "why is
            this event not in the run" is a troubleshooting question,
            and troubleshooting is what the command line is for (D2).
            It costs nothing to answer either, because the collection
            already stored it.

            Args:
                run_id (str):
                    Run to read.

            Raises:
                ApiProblem:
                    If there is no such run.

            Returns:
                answer (List[Dict[str, Any]]):
                    One group per reason anything was left out for.
        """

        with self._opened() as connection:
            uncollected = read_run_uncollected(
                connection=connection,
                run_id=run_id
            )

        if uncollected is None:
            raise self._missing(detail=no_such_run(run_id=run_id))

        return [
            view.model_dump(by_alias=True, mode='json')
            for view in to_uncollected_views(uncollected=uncollected)
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
