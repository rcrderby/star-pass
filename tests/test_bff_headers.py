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

# Imports - Third-Party
import pytest

# Imports - Local
from _bff_clients import opened
from star_pass_bff import _defaults
from star_pass_bff._headers import (
    CONTENT_SECURITY_POLICY,
    SECURITY_HEADERS
)

# Constants
REPOSITORY_ROOT = Path(__file__).parent.parent
CADDYFILE = REPOSITORY_ROOT / 'deploy' / 'caddy' / 'Caddyfile'
RUNS_PATH = f'{_defaults.API_PREFIX}/v1/runs'
HEADER_NAMES = sorted(SECURITY_HEADERS)


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
        name: str
    ) -> None:
        client, _api = opened()

        assert client.get('/').headers[name] == SECURITY_HEADERS[name]

    @pytest.mark.parametrize('name', HEADER_NAMES)
    def test_a_proxied_answer_carries_it(
        self,
        name: str
    ) -> None:
        client, _api = opened()
        # A read without a session is refused.
        client.get('/')

        answer = client.get(RUNS_PATH)

        assert answer.status_code == 200
        assert answer.headers[name] == SECURITY_HEADERS[name]

    def test_a_refusal_carries_the_policy(self) -> None:
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
