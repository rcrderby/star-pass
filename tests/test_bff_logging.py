#!/usr/bin/env python3
""" What the front end writes down, and in what shape.

    Two claims.  The first is that this service records what it
    refused: it enforces a session, a token, an origin and a body
    size, and an access log's status code cannot say which of them
    answered.  The reference in the line is the one in the document,
    so a person quoting a refusal can be answered.

    The second is that the line is JSON, because the API's are, and a
    deployment reading 'docker compose logs' should not have to read
    two formats.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
import json
import logging
from sys import exc_info
from typing import Callable, Tuple

# Imports - Third-Party
import httpx2
import pytest
from fastapi.testclient import TestClient

# Imports - Local
from star_pass_bff import _defaults, create_app
from star_pass_bff._exceptions import ConfigurationError
from star_pass_bff._logging import (
    JSONFormatter,
    LEVELS,
    resolve_level
)

# Constants
RUNS_PATH = f'{_defaults.API_PREFIX}/v1/runs'


@pytest.fixture(name='opened')
def fixture_opened() -> Callable[[], Tuple[TestClient, object]]:
    """ Return a way to open a browser onto the front end. """

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


class TestWhatARefusalRecords:
    def test_a_read_without_a_session_is_logged(
        self,
        opened: Callable[[], Tuple[TestClient, object]],
        caplog: pytest.LogCaptureFixture
    ) -> None:
        client, _api = opened()

        with caplog.at_level(logging.WARNING, logger='star_pass_bff'):
            answer = client.get(RUNS_PATH)

        assert answer.status_code == 403
        assert 'no star-pass session' in caplog.text

    def test_the_line_carries_the_document_reference(
        self,
        opened: Callable[[], Tuple[TestClient, object]],
        caplog: pytest.LogCaptureFixture
    ) -> None:
        # What the caller is told to quote has to be findable in the
        # log, or quoting it buys nothing.
        client, _api = opened()

        with caplog.at_level(logging.WARNING, logger='star_pass_bff'):
            answer = client.get(RUNS_PATH)

        assert answer.json()['reference'] in caplog.text

    def test_the_line_names_the_method_and_the_path(
        self,
        opened: Callable[[], Tuple[TestClient, object]],
        caplog: pytest.LogCaptureFixture
    ) -> None:
        client, _api = opened()

        with caplog.at_level(logging.WARNING, logger='star_pass_bff'):
            client.get(RUNS_PATH)

        assert f'GET {RUNS_PATH}' in caplog.text

    def test_a_write_without_the_token_is_logged_apart(
        self,
        opened: Callable[[], Tuple[TestClient, object]],
        caplog: pytest.LogCaptureFixture
    ) -> None:
        # The point of the line: three refusals share a status code
        # and only the detail says which check answered.
        client, _api = opened()
        client.get('/')

        with caplog.at_level(logging.WARNING, logger='star_pass_bff'):
            answer = client.post(RUNS_PATH, json={})

        assert answer.status_code == 403
        assert 'Reload the page' in caplog.text


class TestTheShapeOfALine:
    def test_it_is_one_line_of_json(self) -> None:
        record = logging.LogRecord(
            name='star_pass_bff._proxy',
            level=logging.WARNING,
            pathname=__file__,
            lineno=1,
            msg='403 Request refused [abc] GET /api/v1/runs: no session',
            args=(),
            exc_info=None
        )

        written = JSONFormatter().format(record)

        assert '\n' not in written
        assert json.loads(written)['message'].startswith('403')

    def test_a_traceback_is_not_dropped(self) -> None:
        try:
            raise ValueError('the reason')

        except ValueError:
            record = logging.LogRecord(
                name='star_pass_bff',
                level=logging.ERROR,
                pathname=__file__,
                lineno=1,
                msg='something',
                args=(),
                exc_info=exc_info()
            )

        written = json.loads(JSONFormatter().format(record))

        assert 'the reason' in written['exception']


class TestTheLevelADeploymentAsksFor:
    @pytest.mark.parametrize('name', sorted(LEVELS))
    def test_every_level_resolves(self, name: str) -> None:
        assert resolve_level(name) == LEVELS[name]

    def test_it_reads_a_name_in_any_case(self) -> None:
        assert resolve_level('  debug ') == logging.DEBUG

    def test_a_name_that_is_not_a_level_is_refused(self) -> None:
        # Silently logging at INFO is how a typo goes unnoticed for a
        # month, which is the interval this tool runs on.
        with pytest.raises(ConfigurationError) as error:
            resolve_level('INF')

        assert 'LOG_LEVEL' in str(error.value)
        assert 'INF' in str(error.value)

    def test_an_attribute_of_the_logging_module_is_not_one(self) -> None:
        # 'logging.BASIC_FORMAT' is a string in capitals, and a lookup
        # on the module rather than on a mapping would return it.
        with pytest.raises(ConfigurationError):
            resolve_level('BASIC_FORMAT')
