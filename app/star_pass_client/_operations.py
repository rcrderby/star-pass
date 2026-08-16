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
from typing import Any, Callable, Iterator


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
    _stream: Callable[..., Iterator[str]]

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

    def stream_job_events(
            self,
            job_id: str
    ) -> Iterator[str]:
        """ Follow what a job reports, as it reports it.

            Args:
                job_id (str):
                    Value for the path.

            Raises:
                ApiProblem:
                    If the service reported a failure.

            Yields:
                line (str):
                    One line of the stream, as it arrives.
        """

        return self._stream(
            method='GET',
            path='/v1/jobs/{job_id}/events',
            job_id=job_id
        )
