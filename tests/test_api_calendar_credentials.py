#!/usr/bin/env python3
""" Asking the service whether its League Calendar key still works.

    What the check itself does is pinned in
    'test_calendar_credentials.py'.  These tests ask what the endpoint
    adds: each calendar's answer in the body, the scope it needs, and
    an allowance of its own, apart from the Amplify test's.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
from typing import Any, Dict, List

# Imports - Third-Party
import pytest
from fastapi.testclient import TestClient

# Imports - Local
from star_pass_api import _credentials, _defaults
from star_pass_api._limiting import RateLimit

# Constants
CALENDAR_PATH = f'{_defaults.API_VERSION_PREFIX}/credentials/calendar/test'
AMPLIFY_PATH = f'{_defaults.API_VERSION_PREFIX}/credentials/test'


@pytest.fixture(name='fresh_allowances', autouse=True)
def fixture_fresh_allowances(monkeypatch: pytest.MonkeyPatch) -> None:
    """ Start both tests' counts from nothing for every test here. """
    for name in ('TESTS', 'CALENDAR_TESTS'):
        monkeypatch.setattr(
            _credentials,
            name,
            RateLimit(
                allowed=_defaults.CREDENTIAL_TEST_ATTEMPTS,
                window_seconds=_defaults.CREDENTIAL_TEST_WINDOW_SECONDS
            )
        )


@pytest.fixture(name='read_accepted')
def fixture_read_accepted(
    answer_requests: Any
) -> List[Dict[str, Any]]:
    """ Have every upstream read succeed, and return what was asked. """
    return answer_requests(lambda _request: {'items': [], 'data': []})


class TestWhatItAnswers:
    def test_each_calendar_is_answered_for(
        self,
        authenticated_client: TestClient,
        read_accepted: List[Dict[str, Any]]
    ) -> None:
        del read_accepted

        answer = authenticated_client.post(CALENDAR_PATH)

        assert answer.status_code == 200
        assert answer.json() == {
            'working': True,
            'lastFour': 'oken',
            'reason': None,
            'calendars': [
                {'calendar': 'events', 'working': True, 'reason': None},
                {'calendar': 'practices', 'working': True, 'reason': None}
            ]
        }


class TestItsOwnAllowance:
    def test_using_up_the_amplify_tests_leaves_it_answering(
        self,
        authenticated_client: TestClient,
        read_accepted: List[Dict[str, Any]]
    ) -> None:
        del read_accepted

        for _attempt in range(_defaults.CREDENTIAL_TEST_ATTEMPTS + 1):
            authenticated_client.post(AMPLIFY_PATH)

        assert authenticated_client.post(CALENDAR_PATH).status_code == 200

    def test_asking_too_often_is_refused_before_any_read(
        self,
        authenticated_client: TestClient,
        read_accepted: List[Dict[str, Any]]
    ) -> None:
        for _attempt in range(_defaults.CREDENTIAL_TEST_ATTEMPTS):
            authenticated_client.post(CALENDAR_PATH)

        reads = len(read_accepted)
        refused = authenticated_client.post(CALENDAR_PATH)

        assert refused.status_code == 429
        assert len(read_accepted) == reads


class TestWhoMayTestIt:
    def test_a_caller_without_a_credential_is_refused(
        self,
        anonymous_client: TestClient
    ) -> None:
        assert anonymous_client.post(CALENDAR_PATH).status_code == 401

    def test_it_needs_the_scope_the_amplify_test_needs(
        self,
        client: TestClient
    ) -> None:
        paths = client.get(_defaults.API_OPENAPI_PATH).json()['paths']

        assert (
            paths[CALENDAR_PATH]['post']['security']
            == paths[AMPLIFY_PATH]['post']['security']
        )
