#!/usr/bin/env python3
""" Tests for the service skeleton: health, and the shape of the API. """

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
from threading import Event
from typing import Any, Callable

# Imports - Third-Party
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Imports - Local
from star_pass import _defaults as core_defaults
from star_pass._repository import JobRepository
from star_pass_api import _defaults, create_app
from star_pass_api._health import HEALTH_STATUS_OK
from star_pass_api._problems import PROBLEM_MEDIA_TYPE

# Constants
HEALTH_PATH = f'{_defaults.API_VERSION_PREFIX}/health'


class TestHealth:
    def test_health_reports_the_service_is_serving(
        self,
        client: TestClient
    ) -> None:
        response = client.get(HEALTH_PATH)

        assert response.status_code == 200
        assert response.json() == {'status': HEALTH_STATUS_OK}

    def test_health_answers_without_a_credential(
        self,
        client: TestClient
    ) -> None:
        # What asks is a container runtime or a proxy, and neither
        # holds one.
        response = client.get(HEALTH_PATH)

        assert 'authorization' not in {
            key.lower()
            for key in response.request.headers
        }
        assert response.status_code == 200

    def test_health_lives_under_the_version_prefix(
        self,
        client: TestClient
    ) -> None:
        assert client.get('/health').status_code == 404


class TestTheGeneratedSpecification:
    def test_the_specification_is_openapi_3_1(
        self,
        client: TestClient
    ) -> None:
        # 3.1 is the version that reads JSON Schema as JSON Schema.
        specification = client.get(_defaults.API_OPENAPI_PATH).json()

        assert specification['openapi'].startswith('3.1')

    def test_the_specification_names_the_service_and_version(
        self,
        client: TestClient
    ) -> None:
        information = client.get(
            _defaults.API_OPENAPI_PATH
        ).json()['info']

        assert information['title'] == _defaults.API_TITLE
        assert information['version'] == _defaults.API_VERSION

    def test_every_path_is_under_the_version_prefix(
        self,
        client: TestClient
    ) -> None:
        paths = client.get(_defaults.API_OPENAPI_PATH).json()['paths']

        assert paths
        for path in paths:
            assert path.startswith(_defaults.API_VERSION_PREFIX)

    def test_a_problem_document_is_the_default_response(
        self,
        client: TestClient
    ) -> None:
        responses = client.get(
            _defaults.API_OPENAPI_PATH
        ).json()['paths'][HEALTH_PATH]['get']['responses']

        assert PROBLEM_MEDIA_TYPE in responses['default']['content']

    def test_the_documentation_is_readable_without_a_credential(
        self,
        client: TestClient
    ) -> None:
        # The shape of an API is not a secret, and every endpoint still
        # requires authentication.
        assert client.get(_defaults.API_DOCS_PATH).status_code == 200
        assert client.get(_defaults.API_REDOC_PATH).status_code == 200


class TestTheFactory:
    def test_each_call_builds_a_separate_service(self) -> None:
        # Configuration is read when a server starts, not when a module
        # is imported, so a test can build one per test.
        first = create_app()
        second = create_app()

        assert isinstance(first, FastAPI)
        assert first is not second


class TestWhatStartingUpDoes:
    def test_the_retention_policy_is_applied_before_anything_answers(
        self,
        finished_job: str,
        jobs: JobRepository,
        monkeypatch: pytest.MonkeyPatch,
        start_service: Callable[[], Any]
    ) -> None:
        # At startup as well as on the interval, because a service
        # restarted often would otherwise never reach its first sweep
        # -- and before it answers, so nothing reads what is about to
        # be removed.
        monkeypatch.setattr(core_defaults, 'RETENTION_JOB_LOG_DAYS', -1)

        with start_service():
            pass

        assert jobs.events(job_id=finished_job) == []

    def test_a_failing_sweep_does_not_stop_the_service_starting(
        self,
        monkeypatch: pytest.MonkeyPatch,
        start_service: Callable[[], Any]
    ) -> None:
        # Retention falling behind is a thing to fix. It is not a
        # reason to refuse to serve, and a deployment that would not
        # start is harder to diagnose than a logged failure.
        def refuse(*_args: Any, **_kwargs: Any) -> None:
            """ Fail the way a locked database does. """
            raise RuntimeError('the database is locked')

        monkeypatch.setattr('star_pass_api._app.sweep', refuse)

        with start_service() as client:
            assert client.get(HEALTH_PATH).status_code == 200

    def test_the_interval_actually_comes_round(
        self,
        monkeypatch: pytest.MonkeyPatch,
        start_service: Callable[[], Any]
    ) -> None:
        # A task that exists and is cancelled at the end is not the
        # same claim as a task that sweeps again: the first is also
        # true of a task that only sleeps. The interval is shortened
        # rather than waited out, and the second call is what says the
        # loop came round -- the first is the one at startup.
        swept = Event()
        calls = []

        async def record() -> None:
            """ Count a sweep, and say when a second one happened. """
            calls.append(1)

            if len(calls) > 1:
                swept.set()

        monkeypatch.setattr(
            'star_pass_api._app.RETENTION_SWEEP_HOURS',
            0.0001
        )
        monkeypatch.setattr('star_pass_api._app._sweep_once', record)

        with start_service():
            assert swept.wait(timeout=10)

    def test_the_sweep_on_the_interval_ends_with_the_service(
        self,
        start_service: Callable[[], Any]
    ) -> None:
        # Left running, it would hold the process open after the
        # service had shut down.
        with start_service() as client:
            sweeping = client.app.state.sweeping

            assert not sweeping.done()

        assert sweeping.cancelled()
