#!/usr/bin/env python3
""" Tests for who the service lets in, and what it lets them ask for. """

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
from typing import Callable

# Imports - Third-Party
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Imports - Local
from star_pass._exceptions import ConfigurationError
from star_pass_api import _defaults, create_app
from star_pass_api._problems import PROBLEM_MEDIA_TYPE
from star_pass_api._security import (
    AUTHENTICATE_CHALLENGE,
    AUTHENTICATE_HEADER,
    Principal,
    requires,
    SCOPE_CONFIG_READ,
    SCOPES
)

# Constants
VERSION_PATH = f'{_defaults.API_VERSION_PREFIX}/version'
HEALTH_PATH = f'{_defaults.API_VERSION_PREFIX}/health'


@pytest.fixture(name='scoped_client')
def fixture_scoped_client(
    api: FastAPI,
    api_credential: str
) -> Callable[..., TestClient]:
    """ Return a factory mounting a route behind the given scopes. """

    def build(*scopes: str) -> TestClient:
        """ Return an authenticated client for a route needing 'scopes'. """

        @api.get('/scoped')
        async def _scoped(
            principal: Principal = requires(*scopes)
        ) -> dict:
            return {'id': principal.id, 'scopes': sorted(principal.scopes)}

        return TestClient(
            app=api,
            raise_server_exceptions=False,
            headers={'Authorization': f'Bearer {api_credential}'}
        )

    return build


class TestAnUnidentifiedCaller:
    def test_no_credential_is_refused(
        self,
        client: TestClient
    ) -> None:
        assert client.get(VERSION_PATH).status_code == 401

    def test_the_refusal_names_the_scheme(
        self,
        client: TestClient
    ) -> None:
        # RFC 9110 requires the challenge on a 401, and it is what
        # tells a client what to send.
        response = client.get(VERSION_PATH)

        assert response.headers[AUTHENTICATE_HEADER] == (
            AUTHENTICATE_CHALLENGE
        )

    def test_the_refusal_is_a_problem_document(
        self,
        client: TestClient
    ) -> None:
        response = client.get(VERSION_PATH)

        assert response.headers['content-type'] == PROBLEM_MEDIA_TYPE
        assert response.json()['status'] == 401

    def test_a_wrong_token_is_refused(
        self,
        client: TestClient
    ) -> None:
        response = client.get(
            VERSION_PATH,
            headers={'Authorization': 'Bearer not-the-configured-value'}
        )

        assert response.status_code == 401

    def test_another_scheme_is_refused(
        self,
        client: TestClient,
        api_credential: str
    ) -> None:
        response = client.get(
            VERSION_PATH,
            headers={'Authorization': f'Basic {api_credential}'}
        )

        assert response.status_code == 401

    def test_a_token_in_the_query_string_does_not_authenticate(
        self,
        client: TestClient,
        api_credential: str
    ) -> None:
        # A query string lands in access logs and in browser history,
        # so the credential is only ever read from the header.
        response = client.get(f'{VERSION_PATH}?token={api_credential}')

        assert response.status_code == 401

    def test_the_refusal_does_not_repeat_the_token_back(
        self,
        client: TestClient
    ) -> None:
        wrong = 'a-wrong-value-that-must-not-be-echoed'

        response = client.get(
            VERSION_PATH,
            headers={'Authorization': f'Bearer {wrong}'}
        )

        assert wrong not in response.text


class TestAnIdentifiedCaller:
    def test_a_valid_token_reaches_the_endpoint(
        self,
        authenticated_client: TestClient
    ) -> None:
        response = authenticated_client.get(VERSION_PATH)

        assert response.status_code == 200
        assert response.json() == {'version': _defaults.API_VERSION}

    def test_the_principal_carries_the_recorded_identity(
        self,
        scoped_client: Callable[..., TestClient]
    ) -> None:
        # One value while the credential is a static token, and it is
        # what a write records (D13).
        document = scoped_client(SCOPE_CONFIG_READ).get('/scoped').json()

        assert document['id'] == _defaults.API_PRINCIPAL_ID

    def test_the_principal_holds_every_scope(
        self,
        scoped_client: Callable[..., TestClient]
    ) -> None:
        document = scoped_client(SCOPE_CONFIG_READ).get('/scoped').json()

        assert document['scopes'] == sorted(SCOPES)


class TestScopes:
    def test_a_scope_the_caller_lacks_is_forbidden(
        self,
        scoped_client: Callable[..., TestClient]
    ) -> None:
        # The single principal holds every declared scope, so this asks
        # for one that does not exist: the check has to be right before
        # there is a second principal to exercise it.
        response = scoped_client('nothing:granted').get('/scoped')

        assert response.status_code == 403

    def test_a_forbidden_request_is_not_challenged(
        self,
        scoped_client: Callable[..., TestClient]
    ) -> None:
        # The credential was accepted; repeating the challenge would
        # invite another one for a decision that was not about it.
        response = scoped_client('nothing:granted').get('/scoped')

        assert AUTHENTICATE_HEADER not in response.headers

    def test_a_forbidden_request_names_the_scope(
        self,
        scoped_client: Callable[..., TestClient]
    ) -> None:
        response = scoped_client('nothing:granted').get('/scoped')

        assert 'nothing:granted' in response.json()['detail']


class TestWhatIsPublic:
    def test_health_still_answers_without_a_credential(
        self,
        client: TestClient
    ) -> None:
        assert client.get(HEALTH_PATH).status_code == 200

    def test_the_documentation_is_still_readable(
        self,
        client: TestClient
    ) -> None:
        assert client.get(_defaults.API_DOCS_PATH).status_code == 200
        assert client.get(_defaults.API_OPENAPI_PATH).status_code == 200


class TestTheGeneratedSpecification:
    def test_the_bearer_scheme_is_declared(
        self,
        client: TestClient
    ) -> None:
        components = client.get(
            _defaults.API_OPENAPI_PATH
        ).json()['components']

        assert components['securitySchemes']

    def test_an_authenticated_route_declares_its_scopes(
        self,
        client: TestClient
    ) -> None:
        security = client.get(
            _defaults.API_OPENAPI_PATH
        ).json()['paths'][VERSION_PATH]['get']['security']

        assert [SCOPE_CONFIG_READ] in [
            scopes
            for requirement in security
            for scopes in requirement.values()
        ]

    def test_health_declares_no_security(
        self,
        client: TestClient
    ) -> None:
        health = client.get(
            _defaults.API_OPENAPI_PATH
        ).json()['paths'][HEALTH_PATH]['get']

        assert 'security' not in health


class TestStartupConfiguration:
    def test_a_missing_token_stops_the_service_starting(
        self,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A deployment missing its token fails at startup rather than
        # at the first request that mattered.
        monkeypatch.setattr(_defaults, 'API_TOKEN', None)

        with pytest.raises(ConfigurationError) as error:
            create_app()

        assert 'STAR_PASS_API_TOKEN' in str(error.value)

    def test_a_short_token_stops_the_service_starting(
        self,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(_defaults, 'API_TOKEN', 'too-short')

        with pytest.raises(ConfigurationError) as error:
            create_app()

        assert 'shorter than' in str(error.value)

    def test_a_token_of_the_minimum_length_is_accepted(
        self,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            _defaults,
            'API_TOKEN',
            'x' * _defaults.API_TOKEN_MINIMUM_LENGTH
        )

        assert create_app()
