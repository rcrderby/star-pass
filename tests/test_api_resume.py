#!/usr/bin/env python3
""" Asking the service to run an interrupted job again (D10).

    What resuming runs is pinned in 'test_job_repository.py' and in the
    tests of the work itself, and it is replaced here.  These tests ask
    a narrower question: that only an interrupted job is resumed, that a
    second ask does not start a second worker, and that the job keeps
    its identifier and loses what the interrupted attempt said about
    itself.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
from typing import Any, Callable, List

# Imports - Third-Party
import pytest
from fastapi.testclient import TestClient

# Imports - Local
from star_pass._records import (
    JOB_KIND_COLLECT,
    JOB_KIND_SEND,
    JOB_STATUS_INTERRUPTED,
    JOB_STATUS_SUCCEEDED
)
from star_pass._repository import JobRepository
from star_pass_api import _defaults

# Constants
PROBLEM_MEDIA_TYPE = 'application/problem+json'


def resume_path(job_id: str) -> str:
    """ Return the address a job is resumed from. """
    return f'{_defaults.API_VERSION_PREFIX}/jobs/{job_id}/resume'


@pytest.fixture(name='interrupted')
def fixture_interrupted(
    jobs: JobRepository,
    collected: str
) -> str:
    """ Return a job left interrupted by a process that stopped. """
    job = jobs.create(
        run_id=collected,
        kind=JOB_KIND_COLLECT,
        principal_id='someone'
    )
    jobs.start(job_id=job.id)
    jobs.finish(job_id=job.id, status=JOB_STATUS_INTERRUPTED)

    return job.id


@pytest.fixture(name='resuming')
def fixture_resuming(
    started_client: TestClient,
    finish_jobs: Callable[[], None],
    monkeypatch: pytest.MonkeyPatch
) -> Callable[..., Any]:
    """ Return a way to ask for a resume and wait for it.

        The work itself is replaced.  What it does is pinned where that
        work is tested; this asks whether the endpoint queues the job
        again and hands it over.
    """
    ran: List[Any] = []

    def chosen(job: Any, principal_id: str) -> Callable[..., None]:
        """ Stand in for the work, recording what was resumed. """
        ran.append((job.id, job.kind, principal_id))

        return lambda _connection, _reporter: None

    monkeypatch.setattr('star_pass_api._jobs.work_for', chosen)

    def ask(job_id: str) -> Any:
        """ Ask for a resume, and wait for the job it started. """
        response = started_client.post(resume_path(job_id=job_id))
        finish_jobs()

        return response, ran

    return ask


class TestResumingAJob:
    def test_an_interrupted_job_is_queued_again(
        self,
        resuming: Callable[..., Any],
        interrupted: str
    ) -> None:
        response, _ran = resuming(interrupted)

        assert response.status_code == 202
        assert response.json()['id'] == interrupted

    def test_the_work_the_job_was_doing_is_what_runs(
        self,
        resuming: Callable[..., Any],
        interrupted: str
    ) -> None:
        # A resumed collection collects and a resumed send sends; the
        # job is what says which.
        _response, ran = resuming(interrupted)

        assert [(job_id, kind) for job_id, kind, _who in ran] == [
            (interrupted, JOB_KIND_COLLECT)
        ]

    def test_the_resume_is_recorded_against_whoever_asked_for_it(
        self,
        resuming: Callable[..., Any],
        job_principal: str,
        interrupted: str
    ) -> None:
        # They caused this work, not whoever asked for the attempt that
        # was interrupted (D13).
        _response, ran = resuming(interrupted)

        assert ran[0][2] == job_principal


class TestWhatIsRefused:
    def test_an_unknown_job_is_not_found(
        self,
        resuming: Callable[..., Any]
    ) -> None:
        response, _ran = resuming('no-such-job')

        assert response.status_code == 404
        assert response.headers['content-type'] == PROBLEM_MEDIA_TYPE

    def test_a_job_that_ended_is_refused(
        self,
        resuming: Callable[..., Any],
        jobs: JobRepository,
        collected: str
    ) -> None:
        job = jobs.create(
            run_id=collected,
            kind=JOB_KIND_SEND,
            principal_id='someone'
        )
        jobs.start(job_id=job.id)
        jobs.finish(job_id=job.id, status=JOB_STATUS_SUCCEEDED)

        response, ran = resuming(job.id)

        assert response.status_code == 409
        assert JOB_STATUS_SUCCEEDED in response.json()['detail']
        assert ran == []

    def test_asking_twice_does_not_start_a_second_worker(
        self,
        resuming: Callable[..., Any],
        interrupted: str
    ) -> None:
        # The job is no longer interrupted after the first ask, which
        # is what makes a second click harmless.
        resuming(interrupted)

        response, ran = resuming(interrupted)

        assert response.status_code == 409
        assert len(ran) == 1

    def test_a_run_something_else_is_working_on_is_refused(
        self,
        resuming: Callable[..., Any],
        working_on: Callable[..., Any],
        collected: str,
        interrupted: str
    ) -> None:
        # Two workers would write the same revisions, or two sends
        # would write into Amplify at once.
        working = working_on(collected)

        response, ran = resuming(interrupted)

        assert response.status_code == 409
        assert working.id in response.json()['detail']
        assert ran == []

    def test_resuming_needs_a_credential(
        self,
        anonymous_client: TestClient,
        job_id: str
    ) -> None:
        assert anonymous_client.post(
            resume_path(job_id=job_id)
        ).status_code == 401
