#!/usr/bin/env python3
""" Tests for reading a job, and for what a restart does to one. """

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
from pathlib import Path
from typing import Any, Callable

# Imports - Third-Party
from fastapi.testclient import TestClient

# Imports - Local
from star_pass._records import (
    JOB_STATUS_INTERRUPTED,
    JOB_STATUS_QUEUED,
    JOB_STATUS_SUCCEEDED
)
from star_pass._repository import JobRepository
from star_pass_api import _defaults
from star_pass_api._problems import PROBLEM_MEDIA_TYPE
from star_pass_api._security import SCOPE_RUNS_READ

# Constants
JOBS_PATH = f'{_defaults.API_VERSION_PREFIX}/jobs'


def job_path(job_id: str) -> str:
    """ Return the address of one job. """
    return f'{JOBS_PATH}/{job_id}'


def status_after_a_restart(
    start_service: Callable[[], Any],
    job_id: str
) -> str:
    """ Start a service and return what it says the job's status is.

        Whatever the caller did to the job first happened before the
        service started, which is what makes this a restart.
    """
    with start_service() as client:
        return client.get(job_path(job_id=job_id)).json()['status']


class TestReadingAJob:
    def test_a_job_reads_back(
        self,
        running_client: TestClient,
        jobs: JobRepository,
        job_id: str
    ) -> None:
        response = running_client.get(job_path(job_id=job_id))

        assert response.status_code == 200
        assert response.json()['id'] == job_id
        assert jobs.get(job_id=job_id) is not None

    def test_the_fields_are_camel_case(
        self,
        running_client: TestClient,
        job_id: str
    ) -> None:
        # The contract is read by a browser and by generated clients.
        document = running_client.get(job_path(job_id=job_id)).json()

        assert 'runId' in document
        assert 'createdAt' in document
        assert 'run_id' not in document

    def test_a_queued_job_has_not_started_or_finished(
        self,
        running_client: TestClient,
        job_id: str
    ) -> None:
        document = running_client.get(job_path(job_id=job_id)).json()

        assert document['status'] == JOB_STATUS_QUEUED
        assert document['startedAt'] is None
        assert document['finishedAt'] is None

    def test_an_unknown_job_is_not_found(
        self,
        running_client: TestClient
    ) -> None:
        # The repository reports a value it cannot use and a missing
        # job the same way, so the endpoint says which it asked for.
        response = running_client.get(job_path(job_id='no-such-job'))

        assert response.status_code == 404
        assert response.headers['content-type'] == PROBLEM_MEDIA_TYPE

    def test_reading_a_job_needs_a_credential(
        self,
        anonymous_client: TestClient,
        job_id: str
    ) -> None:
        assert anonymous_client.get(
            job_path(job_id=job_id)
        ).status_code == 401


class TestWhatARestartDoesToAJob:
    def test_a_running_job_is_interrupted(
        self,
        service_database: Path,
        jobs: JobRepository,
        job_id: str,
        start_service: Callable[[], Any]
    ) -> None:
        # The process holding it no longer exists, and the sweep runs
        # during startup, so the first request already sees the truth.
        del service_database
        jobs.start(job_id=job_id)

        assert status_after_a_restart(
            start_service=start_service,
            job_id=job_id
        ) == JOB_STATUS_INTERRUPTED

    def test_a_queued_job_is_interrupted(
        self,
        service_database: Path,
        jobs: JobRepository,
        job_id: str,
        start_service: Callable[[], Any]
    ) -> None:
        # It was waiting on the process that is gone.
        del service_database, jobs

        assert status_after_a_restart(
            start_service=start_service,
            job_id=job_id
        ) == JOB_STATUS_INTERRUPTED

    def test_a_finished_job_is_left_alone(
        self,
        service_database: Path,
        jobs: JobRepository,
        job_id: str,
        start_service: Callable[[], Any]
    ) -> None:
        del service_database
        jobs.start(job_id=job_id)
        jobs.finish(job_id=job_id, status=JOB_STATUS_SUCCEEDED)

        assert status_after_a_restart(
            start_service=start_service,
            job_id=job_id
        ) == JOB_STATUS_SUCCEEDED

    def test_the_service_has_a_runner_while_it_is_up(
        self,
        running_client: TestClient
    ) -> None:
        assert running_client.app.state.runner is not None


class TestWhatTheSpecificationSays:
    def test_reading_a_job_declares_the_scope_it_needs(
        self,
        client: TestClient
    ) -> None:
        security = client.get(
            _defaults.API_OPENAPI_PATH
        ).json()['paths']['/v1/jobs/{job_id}']['get']['security']

        assert [SCOPE_RUNS_READ] in [
            scopes
            for requirement in security
            for scopes in requirement.values()
        ]

    def test_the_job_shape_is_published_in_camel_case(
        self,
        client: TestClient
    ) -> None:
        properties = client.get(
            _defaults.API_OPENAPI_PATH
        ).json()['components']['schemas']['JobView']['properties']

        assert 'runId' in properties
        assert 'finishedAt' in properties
