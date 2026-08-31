#!/usr/bin/env python3
""" Asking the service whether its Amplify credential still works.

    What the check itself does is pinned in 'test_credentials.py'.
    These tests ask what the endpoint adds: that it publishes four
    characters and no more, that asking too often is refused before
    anything reaches Amplify, and that the refusal says when to come
    back.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
from typing import Any, Callable, Dict, Iterator, List

# Imports - Third-Party
import pytest
from fastapi.testclient import TestClient

# Imports - Local
from star_pass._credentials import CREDENTIAL_VARIABLE
from star_pass_api import _credentials, _defaults
from star_pass_api._limiting import RateLimit
from star_pass_api._problems import PROBLEM_MEDIA_TYPE, RETRY_AFTER_HEADER

# Constants
CREDENTIALS_PATH = f'{_defaults.API_VERSION_PREFIX}/credentials/test'

# What the suite configures, and the four characters of it a caller
# may see.
CONFIGURED = 'test-amplify-token'

# Written out rather than sliced from the value above: how much of a
# credential may be shown is a decision, and a test that took the
# length from the code would agree with whatever the code did.
SHOWN = 'oken'


@pytest.fixture(name='counted_afresh', autouse=True)
def fixture_counted_afresh() -> Iterator[None]:
    """ Give each test its own count of recent attempts.

        The count lives as long as the process, which is right for a
        service and wrong for a suite: one test using up the allowance
        would refuse the next test's first request.
    """
    kept = _credentials.TESTS
    _credentials.TESTS = RateLimit(
        allowed=_defaults.CREDENTIAL_TEST_ATTEMPTS,
        window_seconds=_defaults.CREDENTIAL_TEST_WINDOW_SECONDS
    )

    yield

    _credentials.TESTS = kept


@pytest.fixture(name='test_credential')
def fixture_test_credential(
    authenticated_client: TestClient
) -> Callable[[], Any]:
    """ Return a way to ask for the credential to be tested. """

    def ask() -> Any:
        """ Ask, and return what the service answered. """
        return authenticated_client.post(CREDENTIALS_PATH)

    return ask


class TestWhatItAnswers:
    def test_a_credential_amplify_takes_is_reported_as_working(
        self,
        credential_accepted: List[Dict[str, Any]],
        test_credential: Callable[[], Any]
    ) -> None:
        del credential_accepted

        answer = test_credential()

        assert answer.status_code == 200
        assert answer.json()['working'] is True

    def test_four_characters_of_it_are_published(
        self,
        credential_accepted: List[Dict[str, Any]],
        test_credential: Callable[[], Any]
    ) -> None:
        del credential_accepted

        assert test_credential().json()['lastFour'] == SHOWN

    def test_the_credential_itself_is_not(
        self,
        credential_accepted: List[Dict[str, Any]],
        test_credential: Callable[[], Any]
    ) -> None:
        # No endpoint publishes it and none replaces it: rotation is
        # changing the secret and restarting.
        del credential_accepted

        assert CONFIGURED not in test_credential().text

    def test_a_credential_amplify_refuses_is_an_answer_not_a_failure(
        self,
        monkeypatch: pytest.MonkeyPatch,
        test_credential: Callable[[], Any]
    ) -> None:
        # Whether it works is the question that was asked, so the
        # answer is 200 saying no rather than a problem document.
        monkeypatch.delenv(CREDENTIAL_VARIABLE, raising=False)

        answer = test_credential()

        assert answer.status_code == 200
        assert answer.json()['working'] is False
        assert CREDENTIAL_VARIABLE in answer.json()['reason']


@pytest.fixture(name='asked_too_often')
def fixture_asked_too_often(
    credential_accepted: List[Dict[str, Any]],
    test_credential: Callable[[], Any]
) -> Any:
    """ Use the allowance up, and return what the next attempt got. """
    del credential_accepted

    for _attempt in range(_defaults.CREDENTIAL_TEST_ATTEMPTS):
        test_credential()

    return test_credential()


class TestAskingTooOften:
    def test_the_allowance_goes_through(
        self,
        credential_accepted: List[Dict[str, Any]],
        test_credential: Callable[[], Any]
    ) -> None:
        del credential_accepted

        for _attempt in range(_defaults.CREDENTIAL_TEST_ATTEMPTS):
            assert test_credential().status_code == 200

    def test_the_next_attempt_is_refused(
        self,
        asked_too_often: Any
    ) -> None:
        assert asked_too_often.status_code == 429
        assert asked_too_often.headers['content-type'] == PROBLEM_MEDIA_TYPE

    def test_the_refusal_says_when_to_come_back(
        self,
        asked_too_often: Any
    ) -> None:
        assert 0 < int(asked_too_often.headers[RETRY_AFTER_HEADER]) <= int(
            _defaults.CREDENTIAL_TEST_WINDOW_SECONDS
        )

    def test_a_refused_attempt_reaches_nothing_upstream(
        self,
        credential_accepted: List[Dict[str, Any]],
        test_credential: Callable[[], Any]
    ) -> None:
        # Which is what the limit is for: an endpoint that spends
        # somebody else's service on every call is one to ask rarely.
        for _attempt in range(_defaults.CREDENTIAL_TEST_ATTEMPTS + 3):
            test_credential()

        assert len(credential_accepted) == _defaults.CREDENTIAL_TEST_ATTEMPTS

    def test_less_than_a_second_to_wait_is_still_a_second(
        self,
        monkeypatch: pytest.MonkeyPatch,
        test_credential: Callable[[], Any]
    ) -> None:
        # Rounded up rather than truncated. A Retry-After of zero
        # tells a client to try again immediately, which is refused
        # again, which is the loop the header exists to prevent.
        monkeypatch.setattr(
            _credentials.TESTS,
            'claim',
            lambda caller: 0.4
        )

        answer = test_credential()

        assert answer.status_code == 429
        assert answer.headers[RETRY_AFTER_HEADER] == '1'


class TestWhoMayTestIt:
    def test_a_caller_without_a_credential_is_refused(
        self,
        anonymous_client: TestClient
    ) -> None:
        assert anonymous_client.post(CREDENTIALS_PATH).status_code == 401

    def test_the_endpoint_declares_the_scope_it_needs(
        self,
        client: TestClient
    ) -> None:
        # A read of what the deployment is running on, which is the
        # scope the settings screen already holds.
        published = client.get(
            _defaults.API_OPENAPI_PATH
        ).json()['paths'][CREDENTIALS_PATH]['post']

        assert published['security'] == [{'Bearer token': ['config:read']}]
