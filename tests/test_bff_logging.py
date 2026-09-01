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

# Imports - Third-Party
import pytest

# Imports - Local
from _bff_clients import opened
from star_pass import _logging as core_logging
from star_pass_bff import _defaults
from star_pass_bff._exceptions import ConfigurationError
from star_pass_bff._logging import (
    JSONFormatter,
    LEVELS,
    resolve_level,
    SERVER_LOGGERS
)

# Constants
RUNS_PATH = f'{_defaults.API_PREFIX}/v1/runs'


class TestWhatARefusalRecords:
    def test_a_read_without_a_session_is_logged(
        self,
        caplog: pytest.LogCaptureFixture
    ) -> None:
        client, _api = opened()

        with caplog.at_level(logging.WARNING, logger='star_pass_bff'):
            answer = client.get(RUNS_PATH)

        assert answer.status_code == 403
        assert 'no star-pass session' in caplog.text

    def test_the_line_carries_the_document_reference(
        self,
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
        caplog: pytest.LogCaptureFixture
    ) -> None:
        client, _api = opened()

        with caplog.at_level(logging.WARNING, logger='star_pass_bff'):
            client.get(RUNS_PATH)

        assert f'GET {RUNS_PATH}' in caplog.text

    def test_a_write_without_the_token_is_logged_apart(
        self,
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
        failure = None

        try:
            raise ValueError('the reason')

        except ValueError:
            failure = exc_info()

        assert failure is not None

        record = logging.LogRecord(
            name='star_pass_bff',
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg='something',
            args=(),
            exc_info=failure
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


class TestTheCopyOfTheCoresFormatter:
    """ The front end cannot import the core, so it repeats it.

        Two copies that can drift will, which is why the policy in
        '_headers' is held to the Caddyfile's.  This is the same claim
        for the same reason: a deployment reads both containers'
        output together, and a field renamed on one side would be a
        field missing from half the log.
    """

    def test_both_write_the_same_fields(self) -> None:
        record = logging.LogRecord(
            name='whichever',
            level=logging.WARNING,
            pathname=__file__,
            lineno=1,
            msg='a message',
            args=(),
            exc_info=None
        )

        assert json.loads(JSONFormatter().format(record)).keys() == json.loads(
            core_logging.JSONFormatter().format(record)
        ).keys()

    def test_both_adopt_the_same_server_loggers(self) -> None:
        assert SERVER_LOGGERS == core_logging.SERVER_LOGGERS
