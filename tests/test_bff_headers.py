#!/usr/bin/env python3
""" The policy the page is served under, and who sets it.

    The front end sets it, and the Caddyfile repeats it.  That is the
    arrangement rather than a duplication: 'docs/deployment.md'
    documents running both services under bare uvicorn, and a policy
    that arrives only from the proxy disappears the moment the process
    is started a different way.

    So there are two claims here.  The first is that the service sets
    the policy on everything it answers -- the page, a proxied answer,
    and a refusal -- because a header set in one place is one rule
    rather than a list of exceptions.

    The second is that the two copies say the same thing.  A test for
    it for the reason 'test_web_routes.py' holds two route tables to
    each other: neither copy shows the drift in a diff of one file,
    and the Caddyfile's is the copy that wins in the deployment.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
from pathlib import Path
from re import MULTILINE, search
from typing import Callable, Tuple

# Imports - Third-Party
import httpx2
import pytest
from fastapi.testclient import TestClient

# Imports - Local
from star_pass_bff import _defaults, create_app
from star_pass_bff._headers import (
    CONTENT_SECURITY_POLICY,
    SECURITY_HEADERS
)

# Constants
REPOSITORY_ROOT = Path(__file__).parent.parent
CADDYFILE = REPOSITORY_ROOT / 'deploy' / 'caddy' / 'Caddyfile'
RUNS_PATH = f'{_defaults.API_PREFIX}/v1/runs'
HEADER_NAMES = sorted(SECURITY_HEADERS)


@pytest.fixture(name='opened')
def fixture_opened() -> Callable[[], Tuple[TestClient, object]]:
    """ Return a way to open a browser onto the front end.

        The connection to the API is replaced after the application
        has started, because starting it is what opens the real one.
    """

    def answer(_request: httpx2.Request) -> httpx2.Response:
        """ Answer anything the proxy forwards. """
        return httpx2.Response(status_code=200, json={'runs': []})

    def opened() -> Tuple[TestClient, object]:
        """ Return a client and the application behind it. """
        api = create_app()
        client = TestClient(api)
        client.__enter__()  # pylint: disable=unnecessary-dunder-call
        api.state.api = httpx2.AsyncClient(
            transport=httpx2.MockTransport(answer),
            base_url=_defaults.API_URL
        )

        return client, api

    return opened


def _caddy_sets(name: str) -> str:
    """ Return the value the Caddyfile sets for one header. """
    found = search(
        rf'^\s*{name}\s+"(?P<value>[^"]*)"\s*$',
        CADDYFILE.read_text(encoding='utf-8'),
        flags=MULTILINE
    )

    assert found is not None, f'the Caddyfile sets no {name}'

    return found.group('value')


class TestWhatEveryAnswerCarries:
    @pytest.mark.parametrize('name', HEADER_NAMES)
    def test_the_page_carries_it(
        self,
        opened: Callable[[], Tuple[TestClient, object]],
        name: str
    ) -> None:
        client, _api = opened()

        assert client.get('/').headers[name] == SECURITY_HEADERS[name]

    @pytest.mark.parametrize('name', HEADER_NAMES)
    def test_a_proxied_answer_carries_it(
        self,
        opened: Callable[[], Tuple[TestClient, object]],
        name: str
    ) -> None:
        client, _api = opened()

        answer = client.get(RUNS_PATH)

        assert answer.status_code == 200
        assert answer.headers[name] == SECURITY_HEADERS[name]

    def test_a_refusal_carries_the_policy(
        self,
        opened: Callable[[], Tuple[TestClient, object]]
    ) -> None:
        # A refusal is a response a browser is given like any other,
        # and is the one an attacker is most likely to be looking at.
        client, _api = opened()

        answer = client.post(RUNS_PATH)

        assert answer.status_code == 403
        assert answer.headers[
            'Content-Security-Policy'
        ] == CONTENT_SECURITY_POLICY


class TestTheTwoCopiesAgree:
    @pytest.mark.parametrize('name', HEADER_NAMES)
    def test_the_caddyfile_says_what_the_service_says(
        self,
        name: str
    ) -> None:
        assert _caddy_sets(name) == SECURITY_HEADERS[name]


class TestWhatThePolicyNames:
    def test_form_action_is_named(self) -> None:
        # Unlike 'object-src' it does not fall back to 'default-src',
        # so a policy that leaves it out lets a form on this page
        # submit anywhere.
        assert "form-action 'none'" in CONTENT_SECURITY_POLICY

    def test_nothing_inline_is_allowed(self) -> None:
        # The script and the stylesheet are files, which is what lets
        # this be strict rather than decorative.
        assert 'unsafe-inline' not in CONTENT_SECURITY_POLICY
        assert 'unsafe-eval' not in CONTENT_SECURITY_POLICY
