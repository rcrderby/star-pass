#!/usr/bin/env python3
""" What a log line is, and where it goes.

    Plan section 8 asks for structured logs.  A line was prose, so the
    reference id that ties a screen's refusal to the line that produced
    it could only be got at with a regular expression.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring
# pylint: disable=protected-access

# Imports - Python Standard Library
import io
import json
import logging
import sys

# Imports - Third-Party
import pytest

# Imports - Local
from star_pass import _logging
from star_pass._exceptions import ConfigurationError


@pytest.fixture(name='formatter')
def _formatter() -> _logging.JSONFormatter:
    return _logging.JSONFormatter()


@pytest.fixture(name='written')
def _written():
    """ Read what the real handler writes.

        Not 'capsys': the handler binds 'sys.stderr' when it is built,
        which is at import, and pytest replaces that object afterwards
        -- so the handler goes on writing to the stream capsys is no
        longer watching.  Swapping the stream on the handler itself is
        what puts a test on the path a record actually takes.
    """

    _logging.configure_logging()
    ours = [
        one
        for one in logging.getLogger().handlers
        if isinstance(one.formatter, _logging.JSONFormatter)
    ]

    assert ours, 'the JSON handler is not on the root logger'

    handler = ours[0]
    kept = handler.stream
    handler.stream = io.StringIO()

    yield lambda: [
        json.loads(line)
        for line in handler.stream.getvalue().splitlines()
        if line.strip()
    ]

    handler.stream = kept


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
    def test_the_handler_is_on_the_root(self):
        # Per package was the arrangement this replaced, and it is
        # what produced the split: the core was configured, the API
        # service was not, and its records fell to 'lastResort'.
        _logging.configure_logging()
        root = logging.getLogger()

        assert any(
            isinstance(handler.formatter, _logging.JSONFormatter)
            for handler in root.handlers
        )

    def test_it_is_standard_error(self):
        # Plan section 8 says standard output.  One logger serves both
        # the services and the command line, and the command line
        # writes what a person asked for to standard output -- so log
        # lines there would interleave with the answer to 'runs list'.
        # Docker captures both streams, so nothing is lost by this.
        _logging.configure_logging()
        ours = [
            handler
            for handler in logging.getLogger().handlers
            if isinstance(handler.formatter, _logging.JSONFormatter)
        ]

        assert ours
        assert all(handler.stream is sys.stderr for handler in ours)

    def test_configuring_twice_adds_no_second_handler(self):
        # Every 'get_logger' call configures, so a handler added per
        # call would print each record as many times as the process had
        # asked for a logger.
        _logging.configure_logging()
        before = len(logging.getLogger().handlers)
        _logging.configure_logging()

        assert len(logging.getLogger().handlers) == before

    def test_it_still_propagates(self):
        # The handler is on the root now, so a package logger that
        # stopped propagating would stop being logged at all -- and
        # 'caplog' captures through the root too.
        assert _logging.configure_logging().propagate is True


class TestEveryPackageIsHeard:
    def test_each_one_talks_at_the_configured_level(self):
        # The API service's records used to inherit the root's
        # WARNING, so everything it said at INFO was discarded before
        # anything could format it.
        _logging.configure_logging()

        for name in _logging.APPLICATION_LOGGERS:
            assert logging.getLogger(name).level == _logging._resolve_level(
                _logging.LOG_LEVEL
            )

    def test_the_service_packages_are_among_them(self):
        # Named rather than inferred, so that dropping one from the
        # tuple is a failure here rather than a package that quietly
        # goes quiet.
        assert 'star_pass' in _logging.APPLICATION_LOGGERS
        assert 'star_pass_api' in _logging.APPLICATION_LOGGERS
        assert 'star_pass_bff' in _logging.APPLICATION_LOGGERS

    def test_a_service_record_comes_out_as_json(self, written):
        # The line this exists for: the reference id on a refusal is
        # logged from 'star_pass_api._problems', which is not under
        # 'star_pass' and used to reach the stream as bare text.
        logging.getLogger('star_pass_api._problems').warning(
            '422 Unprocessable request [abc123] POST /v1/runs'
        )

        line = written()[-1]

        assert line['logger'] == 'star_pass_api._problems'
        assert line['level'] == 'WARNING'
        assert 'abc123' in line['message']

    def test_a_service_record_at_info_is_not_dropped(self, written):
        # It used to inherit the root's WARNING, so this said nothing
        # at all.
        logging.getLogger('star_pass_api._problems').info('still here')

        assert written()[-1]['message'] == 'still here'

    def test_a_library_nobody_named_is_still_formatted(self, written):
        # The reason the handler is on the root: being left out of the
        # tuple makes a logger quieter, not unformatted.
        logging.getLogger('some_library').warning('a warning')

        assert written()[-1]['logger'] == 'some_library'


class TestTheServerIsSentTheSameWay:
    def test_uvicorn_keeps_no_handler_of_its_own(self):
        # It arrives with one per logger and 'propagate' off, so a
        # container's output was JSON from the application and plain
        # text from the server carrying it.
        for name in _logging.SERVER_LOGGERS:
            logging.getLogger(name).addHandler(logging.NullHandler())
            logging.getLogger(name).propagate = False

        _logging.send_server_logs_the_same_way()

        for name in _logging.SERVER_LOGGERS:
            assert logging.getLogger(name).handlers == []
            assert logging.getLogger(name).propagate is True

    def test_a_server_line_comes_out_as_json(self, written):
        _logging.send_server_logs_the_same_way()
        # A message already built, which is how this application logs
        # ('logging-format-style=new' in the pylint configuration, and
        # a note saying to pass the variable).  What is under test is
        # that the record reaches the handler at all; the rendering of
        # arguments has its own test, on a record built directly.
        access = logging.getLogger('uvicorn.access')
        access.warning('POST /v1/runs 202')

        line = written()[-1]

        assert line['logger'] == 'uvicorn.access'
        assert line['message'] == 'POST /v1/runs 202'


class TestTheLevelADeploymentAsksFor:
    @pytest.mark.parametrize('name', sorted(_logging.LEVELS))
    def test_every_level_resolves(self, name):
        assert _logging._resolve_level(name) == _logging.LEVELS[name]

    def test_it_reads_a_name_in_any_case(self):
        assert _logging._resolve_level('  debug ') == logging.DEBUG

    def test_a_name_that_is_not_a_level_is_refused(self):
        # Answering a typo by logging at INFO leaves a service quieter
        # than it was asked to be, for the month until somebody looks.
        with pytest.raises(ConfigurationError) as error:
            _logging._resolve_level('INF')

        assert 'LOG_LEVEL' in str(error.value)
        assert 'INF' in str(error.value)

    def test_an_attribute_of_the_logging_module_is_not_one(self):
        # 'logging.BASIC_FORMAT' is a string in capitals, and a lookup
        # on the module rather than on a mapping would return it, to be
        # refused later by 'setLevel' and further from the cause.
        with pytest.raises(ConfigurationError):
            _logging._resolve_level('BASIC_FORMAT')
