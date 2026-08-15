#!/usr/bin/env python3
""" Tests for the service skeleton: health, and the shape of the API. """

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Third-Party
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Imports - Local
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
        # D15 asks for 3.1, which is the version that reads JSON Schema
        # as JSON Schema.
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
