#!/usr/bin/env python3
""" Tests for the problem documents every failure is returned as.

    The routes here exist only for these tests: each raises one thing,
    so that the translation from an exception to a response can be
    exercised without an endpoint that does something else as well.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
import logging
from typing import Callable

# Imports - Third-Party
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

# Imports - Local
from star_pass._exceptions import (
    ConfigurationError,
    StarPassError,
    UpstreamError,
    ValidationError
)
from star_pass_api._problems import (
    INTERNAL_DETAIL,
    PROBLEM_MEDIA_TYPE,
    PROBLEM_TYPE_BLANK,
    PROBLEM_TYPE_CONFIGURATION,
    PROBLEM_TYPE_UNEXPECTED,
    PROBLEM_TYPE_UPSTREAM,
    PROBLEM_TYPE_VALIDATION
)

# Constants
# A message shaped like the ones that must not reach a caller: the
# redaction filter runs over log output, not over an exception a defect
# raised, so the response is what has to withhold it.  The name avoids
# the words bandit reads as a credential being assigned here.
WITHHELD_REASON = 'connection refused for token abcd1234secret'


@pytest.fixture(name='raising_client')
def fixture_raising_client(api: FastAPI) -> Callable[..., TestClient]:
    """ Return a factory mounting a route that raises what it is given. """

    def build(error: Exception) -> TestClient:
        """ Return a client for a service whose route raises 'error'. """

        @api.get('/raise')
        async def _raise() -> None:
            raise error

        return TestClient(
            app=api,
            raise_server_exceptions=False
        )

    return build


class TestTheDocumentShape:
    def test_a_problem_uses_the_problem_media_type(
        self,
        client: TestClient
    ) -> None:
        response = client.get('/v1/no-such-endpoint')

        assert response.headers['content-type'] == PROBLEM_MEDIA_TYPE

    def test_a_problem_carries_the_members_rfc_9457_names(
        self,
        client: TestClient
    ) -> None:
        document = client.get('/v1/no-such-endpoint').json()

        assert set(document) >= {
            'type',
            'title',
            'status',
            'detail',
            'reference'
        }

    def test_a_bare_status_is_titled_with_its_phrase(
        self,
        client: TestClient
    ) -> None:
        # What RFC 9457 asks for when 'type' is 'about:blank'.
        document = client.get('/v1/no-such-endpoint').json()

        assert document['type'] == PROBLEM_TYPE_BLANK
        assert document['title'] == 'Not Found'
        assert document['status'] == 404

    def test_every_problem_carries_its_own_reference(
        self,
        client: TestClient
    ) -> None:
        first = client.get('/v1/no-such-endpoint').json()
        second = client.get('/v1/no-such-endpoint').json()

        assert first['reference'] != second['reference']


class TestTheCoreExceptions:
    @pytest.mark.parametrize(
        'error, expected_status, expected_type',
        (
            (
                ConfigurationError('AMPLIFY_TOKEN is not set'),
                500,
                PROBLEM_TYPE_CONFIGURATION
            ),
            (
                ValidationError('Row 4 has no need ID'),
                422,
                PROBLEM_TYPE_VALIDATION
            ),
            (
                UpstreamError('Amplify answered 503'),
                502,
                PROBLEM_TYPE_UPSTREAM
            )
        )
    )
    def test_each_becomes_its_own_status_and_type(
        self,
        raising_client: Callable[..., TestClient],
        error: StarPassError,
        expected_status: int,
        expected_type: str
    ) -> None:
        response = raising_client(error).get('/raise')

        assert response.status_code == expected_status
        assert response.json()['type'] == expected_type

    def test_a_subclass_added_later_is_still_answered(
        self,
        raising_client: Callable[..., TestClient]
    ) -> None:
        # The handler is registered for the base class, so a new
        # subclass is answered rather than escaping uncaught.
        class NewCoreError(StarPassError):
            pass

        response = raising_client(NewCoreError('something')).get('/raise')

        assert response.status_code == 500
        assert response.json()['type'] == PROBLEM_TYPE_UNEXPECTED


class TestWhatACallerIsTold:
    def test_a_client_error_gives_the_reason(
        self,
        raising_client: Callable[..., TestClient]
    ) -> None:
        # The caller is the one who can fix it.
        error = ValidationError('Row 4 has no need ID')

        document = raising_client(error).get('/raise').json()

        assert document['detail'] == 'Row 4 has no need ID'

    def test_a_server_error_withholds_the_reason(
        self,
        raising_client: Callable[..., TestClient]
    ) -> None:
        # An internal failure can carry a credential or a volunteer's
        # name, so the caller gets a sentence and the reference.
        error = UpstreamError(WITHHELD_REASON)

        document = raising_client(error).get('/raise').json()

        assert document['detail'] == INTERNAL_DETAIL
        assert 'abcd1234secret' not in str(document)

    def test_a_defect_withholds_the_reason(
        self,
        raising_client: Callable[..., TestClient]
    ) -> None:
        error = RuntimeError(WITHHELD_REASON)

        response = raising_client(error).get('/raise')

        assert response.status_code == 500
        assert response.json()['detail'] == INTERNAL_DETAIL
        assert 'abcd1234secret' not in response.text

    def test_a_withheld_reason_is_logged_under_the_reference(
        self,
        raising_client: Callable[..., TestClient],
        caplog: pytest.LogCaptureFixture
    ) -> None:
        # The reference is what joins a response that says nothing to
        # the log line that says everything.
        error = UpstreamError(WITHHELD_REASON)

        with caplog.at_level(logging.ERROR):
            document = raising_client(error).get('/raise').json()

        assert document['reference'] in caplog.text
        assert WITHHELD_REASON in caplog.text

    def test_a_raised_status_keeps_its_detail(
        self,
        raising_client: Callable[..., TestClient]
    ) -> None:
        error = HTTPException(status_code=404, detail='No run with that ID')

        document = raising_client(error).get('/raise').json()

        assert document['status'] == 404
        assert document['detail'] == 'No run with that ID'


class TestRequestValidation:
    def test_a_bad_query_value_is_a_problem_document(
        self,
        api: FastAPI
    ) -> None:
        @api.get('/needs-a-number')
        async def _needs_a_number(count: int) -> dict:
            return {'count': count}

        response = TestClient(
            app=api,
            raise_server_exceptions=False
        ).get('/needs-a-number?count=not-a-number')

        assert response.status_code == 422
        assert response.headers['content-type'] == PROBLEM_MEDIA_TYPE
        assert response.json()['type'] == PROBLEM_TYPE_VALIDATION

    def test_the_field_errors_are_kept(
        self,
        api: FastAPI
    ) -> None:
        # They describe the request the caller sent, so they are the
        # caller's to read.
        @api.get('/needs-a-number')
        async def _needs_a_number(count: int) -> dict:
            return {'count': count}

        document = TestClient(
            app=api,
            raise_server_exceptions=False
        ).get('/needs-a-number?count=not-a-number').json()

        assert document['errors']
        assert 'count' in document['errors'][0]['location']
