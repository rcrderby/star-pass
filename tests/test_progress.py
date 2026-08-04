""" Unit tests for star_pass._progress.

    No terminal is involved: the spinner writes to an in-memory stream
    and the animation is either forced on with a short interval or
    forced off, so the tests stay fast and deterministic.
"""
# pylint: disable=missing-function-docstring,missing-class-docstring
# pylint: disable=protected-access

# Imports - Python Standard Library
import io
import time

# Imports - Third-Party
import pytest

# Imports - Local
from star_pass._progress import Spinner, SPINNER_FRAMES

# Fast enough to animate several frames inside a test.
TEST_INTERVAL = 0.01


def _spun(stream: io.StringIO) -> int:
    # Number of animation frames written to the stream.
    return sum(stream.getvalue().count(frame) for frame in SPINNER_FRAMES)


class TestSpinnerEnabled:
    def test_animates_and_shows_the_message(self):
        stream = io.StringIO()

        with Spinner(
            message='Reading recent sign-ups',
            stream=stream,
            interval=TEST_INTERVAL,
            enabled=True
        ):
            time.sleep(TEST_INTERVAL * 5)

        output = stream.getvalue()
        assert 'Reading recent sign-ups' in output
        assert _spun(stream) > 1

    def test_update_replaces_the_message(self):
        stream = io.StringIO()

        with Spinner(
            message='Reading recent sign-ups (page 1)',
            stream=stream,
            interval=TEST_INTERVAL,
            enabled=True
        ) as spinner:
            time.sleep(TEST_INTERVAL * 3)
            spinner.update('Reading opportunity 2 of 5')
            time.sleep(TEST_INTERVAL * 3)

        assert 'Reading opportunity 2 of 5' in stream.getvalue()

    def test_clears_the_line_on_exit(self):
        # The run should leave the terminal as it found it.
        stream = io.StringIO()

        with Spinner(
            message='Working',
            stream=stream,
            interval=TEST_INTERVAL,
            enabled=True
        ):
            time.sleep(TEST_INTERVAL * 2)

        assert stream.getvalue().endswith('\r')

    def test_a_shorter_message_does_not_leave_characters_behind(self):
        stream = io.StringIO()

        with Spinner(
            message='Reading recent sign-ups (page 1)',
            stream=stream,
            interval=TEST_INTERVAL,
            enabled=True
        ) as spinner:
            time.sleep(TEST_INTERVAL * 3)
            spinner.update('Done')
            time.sleep(TEST_INTERVAL * 3)

        # Every 'Done' frame is padded out to the longest line written.
        for line in stream.getvalue().split('\r'):
            if line.startswith(('- Done', '\\ Done', '| Done', '/ Done')):
                assert len(line) >= len('- Reading recent sign-ups (page 1)')

    def test_stops_the_thread_on_exit(self):
        stream = io.StringIO()
        spinner = Spinner(
            message='Working',
            stream=stream,
            interval=TEST_INTERVAL,
            enabled=True
        )

        with spinner:
            time.sleep(TEST_INTERVAL * 2)

        assert spinner._thread is None

    def test_an_error_in_the_block_still_stops_the_spinner(self):
        # A failure must not be hidden, and must not leave the thread
        # animating over the traceback.
        stream = io.StringIO()
        spinner = Spinner(
            message='Working',
            stream=stream,
            interval=TEST_INTERVAL,
            enabled=True
        )

        with pytest.raises(ValueError, match='boom'):
            with spinner:
                time.sleep(TEST_INTERVAL)
                raise ValueError('boom')

        assert spinner._thread is None


class TestSpinnerDisabled:
    def test_writes_nothing_when_disabled(self):
        # A scheduled run redirects its output, where animation frames
        # would be noise in a log file.
        stream = io.StringIO()

        with Spinner(
            message='Working',
            stream=stream,
            interval=TEST_INTERVAL,
            enabled=False
        ) as spinner:
            time.sleep(TEST_INTERVAL * 3)
            spinner.update('Still working')

        assert stream.getvalue() == ''

    def test_defaults_to_off_for_a_stream_that_is_not_a_terminal(self):
        assert Spinner(stream=io.StringIO()).enabled is False

    def test_defaults_to_on_for_a_terminal(self):
        class _Terminal(io.StringIO):
            def isatty(self):
                return True

        assert Spinner(stream=_Terminal()).enabled is True

    def test_update_is_safe_before_and_after_the_block(self):
        spinner = Spinner(stream=io.StringIO(), enabled=False)
        spinner.update('before')
        spinner.stop()

        assert spinner.message == 'before'


class TestSpinnerStreamErrors:
    def test_a_closed_stream_disables_the_display(self):
        # The display is cosmetic; a closed stream must not take the
        # run down with it.
        stream = io.StringIO()
        spinner = Spinner(
            message='Working',
            stream=stream,
            interval=TEST_INTERVAL,
            enabled=True
        )

        with spinner:
            time.sleep(TEST_INTERVAL)
            stream.close()
            time.sleep(TEST_INTERVAL * 3)

        assert spinner.enabled is False
