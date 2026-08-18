#!/usr/bin/env python3
""" The operations the star-pass API publishes.

    Generated from 'docs/api/openapi.json' by
    'app/star_pass_client/_generator.py'. Do not edit: run
    "python scripts/generate_contract.py" and commit the result.

    One method per operation in the contract, which is what makes
    "the command line client can do anything the web interface can"
    a property of the build rather than a promise (D15). What each
    method sends, and what it does with the answer, is in
    '_client.py'.
"""

# Imports - Python Standard Library
from typing import Any, Callable, Dict, Iterator

# Imports - Local
from ._stream import StreamEvent


class Operations:
    """ One method per operation the contract publishes.

        Mixed into 'Client', which supplies the '_call' and '_stream'
        these methods use.
    """

    # What the other half has to provide.  Declared rather than
    # assumed, so the contract between the generated methods and the
    # written ones is on the page and a checker reading this file
    # alone can see it.
    _call: Callable[..., Any]
    _stream: Callable[..., Iterator[StreamEvent]]

    def add_event(
            self,
            body: Dict[str, Any],
            run_id: str
    ) -> Any:
        """ Pull an event the search missed into this run.

            Args:
                body (Dict[str, Any]):
                    What the operation is sent, shaped as the
                    contract publishes it.

                run_id (str):
                    Value for the path.

            Raises:
                ApiProblem:
                    If the service reported a failure.

            Returns:
                answer (Any):
                    What the service answered.
        """

        return self._call(
            method='POST',
            path='/v1/runs/{run_id}/events',
            body=body,
            run_id=run_id
        )

    def collect_run(
            self,
            body: Dict[str, Any]
    ) -> Any:
        """ Collect a calendar window into a new run.

            Args:
                body (Dict[str, Any]):
                    What the operation is sent, shaped as the
                    contract publishes it.

            Raises:
                ApiProblem:
                    If the service reported a failure.

            Returns:
                answer (Any):
                    What the service answered.
        """

        return self._call(
            method='POST',
            path='/v1/runs',
            body=body
        )

    def edit_events(
            self,
            body: Dict[str, Any],
            run_id: str,
            idempotency_key: str
    ) -> Any:
        """ Edit the events in this run's current revision.

            Args:
                body (Dict[str, Any]):
                    What the operation is sent, shaped as the
                    contract publishes it.

                run_id (str):
                    Value for the path.

                idempotency_key (str):
                    Value for the Idempotency-Key header.

            Raises:
                ApiProblem:
                    If the service reported a failure.

            Returns:
                answer (Any):
                    What the service answered.
        """

        return self._call(
            method='PATCH',
            path='/v1/runs/{run_id}/events',
            body=body,
            headers={'Idempotency-Key': idempotency_key},
            run_id=run_id
        )

    def get_config(
            self
    ) -> Any:
        """ Report what the service was configured with.

            Args:
                None.

            Raises:
                ApiProblem:
                    If the service reported a failure.

            Returns:
                answer (Any):
                    What the service answered.
        """

        return self._call(
            method='GET',
            path='/v1/config'
        )

    def get_health(
            self
    ) -> Any:
        """ Report that the service is serving.

            Args:
                None.

            Raises:
                ApiProblem:
                    If the service reported a failure.

            Returns:
                answer (Any):
                    What the service answered.
        """

        return self._call(
            method='GET',
            path='/v1/health'
        )

    def get_job(
            self,
            job_id: str
    ) -> Any:
        """ Report where a job has got to.

            Args:
                job_id (str):
                    Value for the path.

            Raises:
                ApiProblem:
                    If the service reported a failure.

            Returns:
                answer (Any):
                    What the service answered.
        """

        return self._call(
            method='GET',
            path='/v1/jobs/{job_id}',
            job_id=job_id
        )

    def get_preview(
            self,
            run_id: str
    ) -> Any:
        """ Report what sending this run would create.

            Args:
                run_id (str):
                    Value for the path.

            Raises:
                ApiProblem:
                    If the service reported a failure.

            Returns:
                answer (Any):
                    What the service answered.
        """

        return self._call(
            method='GET',
            path='/v1/runs/{run_id}/preview',
            run_id=run_id
        )

    def get_run(
            self,
            run_id: str
    ) -> Any:
        """ Read one run in full.

            Args:
                run_id (str):
                    Value for the path.

            Raises:
                ApiProblem:
                    If the service reported a failure.

            Returns:
                answer (Any):
                    What the service answered.
        """

        return self._call(
            method='GET',
            path='/v1/runs/{run_id}',
            run_id=run_id
        )

    def get_version(
            self
    ) -> Any:
        """ Report the running version.

            Args:
                None.

            Raises:
                ApiProblem:
                    If the service reported a failure.

            Returns:
                answer (Any):
                    What the service answered.
        """

        return self._call(
            method='GET',
            path='/v1/version'
        )

    def list_revisions(
            self,
            run_id: str
    ) -> Any:
        """ List a run's revisions, oldest first.

            Args:
                run_id (str):
                    Value for the path.

            Raises:
                ApiProblem:
                    If the service reported a failure.

            Returns:
                answer (Any):
                    What the service answered.
        """

        return self._call(
            method='GET',
            path='/v1/runs/{run_id}/revisions',
            run_id=run_id
        )

    def list_runs(
            self
    ) -> Any:
        """ List the runs, newest first.

            Args:
                None.

            Raises:
                ApiProblem:
                    If the service reported a failure.

            Returns:
                answer (Any):
                    What the service answered.
        """

        return self._call(
            method='GET',
            path='/v1/runs'
        )

    def list_uncollected(
            self,
            run_id: str
    ) -> Any:
        """ List what the window held and the run did not collect.

            Args:
                run_id (str):
                    Value for the path.

            Raises:
                ApiProblem:
                    If the service reported a failure.

            Returns:
                answer (Any):
                    What the service answered.
        """

        return self._call(
            method='GET',
            path='/v1/runs/{run_id}/uncollected',
            run_id=run_id
        )

    def recollect_run(
            self,
            body: Dict[str, Any],
            run_id: str
    ) -> Any:
        """ Collect a run's calendar window again.

            Args:
                body (Dict[str, Any]):
                    What the operation is sent, shaped as the
                    contract publishes it.

                run_id (str):
                    Value for the path.

            Raises:
                ApiProblem:
                    If the service reported a failure.

            Returns:
                answer (Any):
                    What the service answered.
        """

        return self._call(
            method='POST',
            path='/v1/runs/{run_id}/recollect',
            body=body,
            run_id=run_id
        )

    def resume_job(
            self,
            job_id: str
    ) -> Any:
        """ Run an interrupted job again.

            Args:
                job_id (str):
                    Value for the path.

            Raises:
                ApiProblem:
                    If the service reported a failure.

            Returns:
                answer (Any):
                    What the service answered.
        """

        return self._call(
            method='POST',
            path='/v1/jobs/{job_id}/resume',
            job_id=job_id
        )

    def revert_revision(
            self,
            run_id: str,
            number: int,
            idempotency_key: str
    ) -> Any:
        """ Take the run back to what an earlier revision held.

            Args:
                run_id (str):
                    Value for the path.

                number (int):
                    Value for the path.

                idempotency_key (str):
                    Value for the Idempotency-Key header.

            Raises:
                ApiProblem:
                    If the service reported a failure.

            Returns:
                answer (Any):
                    What the service answered.
        """

        return self._call(
            method='POST',
            path='/v1/runs/{run_id}/revisions/{number}/revert',
            headers={'Idempotency-Key': idempotency_key},
            run_id=run_id,
            number=number
        )

    def seal_revision(
            self,
            run_id: str,
            idempotency_key: str
    ) -> Any:
        """ Seal the revision being worked in and open the next.

            Args:
                run_id (str):
                    Value for the path.

                idempotency_key (str):
                    Value for the Idempotency-Key header.

            Raises:
                ApiProblem:
                    If the service reported a failure.

            Returns:
                answer (Any):
                    What the service answered.
        """

        return self._call(
            method='POST',
            path='/v1/runs/{run_id}/revisions',
            headers={'Idempotency-Key': idempotency_key},
            run_id=run_id
        )

    def send_run(
            self,
            body: Dict[str, Any],
            run_id: str,
            idempotency_key: str
    ) -> Any:
        """ Create this run's shifts in Amplify.

            Args:
                body (Dict[str, Any]):
                    What the operation is sent, shaped as the
                    contract publishes it.

                run_id (str):
                    Value for the path.

                idempotency_key (str):
                    Value for the Idempotency-Key header.

            Raises:
                ApiProblem:
                    If the service reported a failure.

            Returns:
                answer (Any):
                    What the service answered.
        """

        return self._call(
            method='POST',
            path='/v1/runs/{run_id}/send',
            body=body,
            headers={'Idempotency-Key': idempotency_key},
            run_id=run_id
        )

    def stream_job_events(
            self,
            job_id: str
    ) -> Iterator[StreamEvent]:
        """ Follow what a job reports, as it reports it.

            Args:
                job_id (str):
                    Value for the path.

            Raises:
                ApiProblem:
                    If the service reported a failure.

            Yields:
                event (StreamEvent):
                    One event, in the order they arrive.
        """

        return self._stream(
            method='GET',
            path='/v1/jobs/{job_id}/events',
            job_id=job_id
        )
