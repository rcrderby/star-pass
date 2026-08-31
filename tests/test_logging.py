#!/usr/bin/env python3
""" What a log line is, and where it goes.

    Plan section 8 asks for structured logs.  A line was prose, so the
    reference id that ties a screen's refusal to the line that produced
    it could only be got at with a regular expression.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
import json
import logging
import sys

# Imports - Third-Party
import pytest

# Imports - Local
from star_pass import _logging


@pytest.fixture(name='formatter')
def _formatter() -> _logging.JSONFormatter:
    return _logging.JSONFormatter()


def _record(
        message: str = 'a message',
        args=None,
        level: int = logging.INFO,
        name: str = 'star_pass.example',
        exc_info=None
) -> logging.LogRecord:
    return logging.LogRecord(
        name, level, 'a_file.py', 1, message, args, exc_info
    )


class TestALineIsJSON:
    def test_it_parses(self, formatter):
        assert json.loads(formatter.format(_record()))

    def test_it_carries_the_four_things_a_line_is_read_for(
        self, formatter
    ):
        written = json.loads(
            formatter.format(
                _record(message='what happened', level=logging.WARNING)
            )
        )

        assert written['level'] == 'WARNING'
        assert written['logger'] == 'star_pass.example'
        assert written['message'] == 'what happened'
        assert written['time'].startswith('20')

    def test_the_time_is_stamped_in_utc(self, formatter):
        # A container usually runs in UTC and a laptop does not, so a
        # stamp without a zone is two different times depending on
        # where the process happened to be.
        written = json.loads(formatter.format(_record()))

        assert written['time'].endswith('+00:00')

    def test_a_record_is_one_line(self, formatter):
        # The whole point of a line: anything reading this a line at a
        # time has to get one record per line, and a message can carry
        # a newline -- an upstream sentence, a traceback.
        line = formatter.format(_record(message='first\nsecond'))

        assert '\n' not in line
        assert json.loads(line)['message'] == 'first\nsecond'

    def test_the_arguments_are_rendered_into_the_message(
        self, formatter
    ):
        # Call sites log '%s' style, and the redaction they apply is
        # applied to the value they pass -- so the message has to be
        # the rendered one, not the template.
        written = json.loads(
            formatter.format(
                _record(message='key=%s', args=('REDACTED',))
            )
        )

        assert written['message'] == 'key=REDACTED'


class TestWhatIsNotSerialized:
    def test_nothing_a_caller_attached_reaches_the_line(
        self, formatter
    ):
        # Full upstream detail is redacted at the call site, on its way
        # into the message.  A formatter that serialized 'extra' would
        # be a second way into the log, one nothing had redacted.
        # The attribute is named for what it is rather than for what
        # a caller might put in one: bandit reads a name holding
        # 'token' beside a string as a credential somebody hardcoded
        # (B105), and this file would be the place it was wrong.
        record = _record()
        record.carried = 'nothing-redacted-this'

        written = json.loads(formatter.format(record))

        assert 'carried' not in written
        assert 'nothing-redacted-this' not in json.dumps(written)


class TestAnExceptionIsKept:
    def test_the_traceback_survives(self, formatter):
        # Nothing logs with 'exc_info' today.  The previous formatter
        # would have appended a traceback if something started to, and
        # dropping it silently would lose it with no sign it had gone.
        try:
            raise ValueError('boom')
        except ValueError:
            written = json.loads(
                formatter.format(_record(exc_info=sys.exc_info()))
            )

            assert 'ValueError: boom' in written['exception']

    def test_a_record_without_one_says_nothing_about_it(
        self, formatter
    ):
        assert 'exception' not in json.loads(formatter.format(_record()))


class TestWhereALineGoes:
    def test_it_is_standard_error(self):
        # Plan section 8 says standard output.  One logger serves both
        # the services and the command line, and the command line
        # writes what a person asked for to standard output -- so log
        # lines there would interleave with the answer to 'runs list'.
        # Docker captures both streams, so nothing is lost by this.
        logger = _logging.configure_logging()
        streams = [
            handler.stream
            for handler in logger.handlers
            if isinstance(handler, logging.StreamHandler)
        ]

        assert streams
        assert all(stream is sys.stderr for stream in streams)

    def test_every_handler_writes_json(self):
        logger = _logging.configure_logging()

        assert logger.handlers
        assert all(
            isinstance(handler.formatter, _logging.JSONFormatter)
            for handler in logger.handlers
        )

    def test_configuring_twice_adds_no_second_handler(self):
        # Every 'get_logger' call configures, so a handler added per
        # call would print each record as many times as the process had
        # asked for a logger.
        before = len(_logging.configure_logging().handlers)

        assert len(_logging.configure_logging().handlers) == before

    def test_it_still_propagates(self):
        # 'caplog' captures through the root logger, so a package
        # logger that stopped propagating would take the log out of
        # reach of every test that reads one.
        assert _logging.configure_logging().propagate is True
