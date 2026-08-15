""" Tests for the CLI's terminal renderer.

    'CreateShifts' no longer formats its own output, so the text an
    operator sees is produced here.  These tests pin that text, because
    the move was meant to change where it is decided and not what it
    says.

    'app/__main__.py' is normally executed as a script, so it is loaded
    by file path.  Unlike the entry-point tests, the module's real
    'helpers' is left in place: 'printer' writing to the real stdout is
    what capsys captures.
"""
# pylint: disable=missing-function-docstring,missing-class-docstring
# pylint: disable=redefined-outer-name

# Imports - Python Standard Library
import importlib.util
from pathlib import Path

# Imports - Third-Party
import pytest

_MAIN_PATH = Path(__file__).resolve().parent.parent / 'app' / '__main__.py'

# One opportunity's worth of sent shifts, in the shape the core reports.
SHIFTS = [
    {'start': '2099-04-09 18:00', 'duration': 120},
    {'start': '2099-04-10 19:30', 'duration': 90}
]
PAYLOAD = {'shifts': SHIFTS}


@pytest.fixture
def reporter_class():
    spec = importlib.util.spec_from_file_location('star_pass_cli', _MAIN_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return module.TerminalReporter


class TestSteps:
    def test_the_first_step_is_preceded_by_a_blank_line(
        self, reporter_class, capsys
    ):
        # The blank line separates the run from the command that started
        # it.  The core cannot add it, because it does not know which
        # step is first.
        reporter = reporter_class()
        reporter.step_started(label='Removing duplicate shifts')
        reporter.step_finished()

        assert capsys.readouterr().out == (
            '\nRemoving duplicate shifts...done.\n'
        )

    def test_later_steps_are_not(self, reporter_class, capsys):
        reporter = reporter_class()
        reporter.step_started(label='First')
        reporter.step_finished()
        reporter.step_started(label='Second')
        reporter.step_finished()

        assert capsys.readouterr().out == (
            '\nFirst...done.\nSecond...done.\n'
        )

    def test_a_failed_step_closes_its_line(self, reporter_class, capsys):
        # The reason is not printed: it reaches the caller as an
        # exception and is already logged.
        reporter = reporter_class()
        reporter.step_started(label='Reading shift data')
        reporter.step_failed()

        assert capsys.readouterr().out == '\nReading shift data...\n'

    def test_schema_validation_failure_is_named(
        self, reporter_class, capsys
    ):
        reporter = reporter_class()
        reporter.schema_validation_failed()

        assert capsys.readouterr().out == (
            '\n\n** Error validating shift data **\n\n'
        )


class TestCollectionEvents:
    def test_the_calendar_read_is_announced_on_its_own_line(
        self, reporter_class, capsys
    ):
        # Announced rather than opened as a step: the read reports
        # nothing until every configured query string has returned.
        reporter = reporter_class()
        reporter.calendar_read_started()

        assert capsys.readouterr().out == (
            '\nReading data from the Google Calendar service...\n'
        )

    def test_a_step_after_the_read_gets_no_second_blank_line(
        self, reporter_class, capsys
    ):
        # The read is the first thing a collection run prints, so it
        # takes the leading blank line and the next step must not.
        reporter = reporter_class()
        reporter.calendar_read_started()
        reporter.step_started(label='Processing Google Calendar event data')
        reporter.step_finished()

        assert capsys.readouterr().out == (
            '\nReading data from the Google Calendar service...\n'
            'Processing Google Calendar event data...done.\n'
        )

    def test_the_written_file_is_named(self, reporter_class, capsys):
        reporter = reporter_class()
        reporter.step_started(label='Writing Amplify shift data to a CSV file')
        reporter.step_finished()
        reporter.csv_written(path='/data/csv/gcal_shifts_2099.csv')

        assert capsys.readouterr().out == (
            '\nWriting Amplify shift data to a CSV file...done.\n'
            '\nWrote CSV data to "/data/csv/gcal_shifts_2099.csv"\n\n'
        )


class TestSendReport:
    def test_basic_names_the_opportunity_and_counts(
        self, reporter_class, capsys
    ):
        reporter = reporter_class(verbosity='basic')
        reporter.shifts_sent(
            index=1,
            need_id=879609,
            title='Adult Games: Non-Skating Officials',
            url='https://example.test/needs/879609/shifts',
            shifts=SHIFTS,
            payload=PAYLOAD
        )

        assert capsys.readouterr().out == (
            '1. Adult Games: Non-Skating Officials - 2 new shifts\n'
        )

    def test_basic_makes_a_single_shift_singular(
        self, reporter_class, capsys
    ):
        reporter = reporter_class(verbosity='basic')
        reporter.shifts_sent(
            index=2,
            need_id=879610,
            title='Adult Games: Skating Officials',
            url='https://example.test/needs/879610/shifts',
            shifts=SHIFTS[:1],
            payload={'shifts': SHIFTS[:1]}
        )

        assert capsys.readouterr().out == (
            '2. Adult Games: Skating Officials - 1 new shift\n'
        )

    def test_simple_lists_every_shift_date_and_time(
        self, reporter_class, capsys
    ):
        reporter = reporter_class(verbosity='simple')
        reporter.shifts_sent(
            index=1,
            need_id=879609,
            title='Adult Games: Non-Skating Officials',
            url='https://example.test/needs/879609/shifts',
            shifts=SHIFTS,
            payload=PAYLOAD
        )

        out = capsys.readouterr().out
        assert out.startswith(
            'Opportunity Title: Adult Games: Non-Skating Officials\n'
            'URL: https://example.test/needs/879609/shifts\n'
            'Shift Count: 2\n'
        )
        assert 'Thursday, April 09 2099' in out
        assert 'Friday, April 10 2099' in out

    def test_detailed_includes_the_payload(self, reporter_class, capsys):
        reporter = reporter_class(verbosity='detailed')
        reporter.shifts_sent(
            index=1,
            need_id=879609,
            title='Adult Games: Non-Skating Officials',
            url='https://example.test/needs/879609/shifts',
            shifts=SHIFTS,
            payload=PAYLOAD
        )

        out = capsys.readouterr().out
        assert out.startswith(
            'URL: https://example.test/needs/879609/shifts\n'
            'Opportunity Title: Adult Games: Non-Skating Officials\n'
            'Shift Count: 2\n'
            'Payload:\n'
        )
        assert '"duration": 120' in out

    def test_an_unknown_verbosity_shows_the_least(
        self, reporter_class, capsys
    ):
        # A bad value shows less rather than failing a run that is
        # otherwise fine.
        reporter = reporter_class(verbosity='chatty')
        reporter.shifts_sent(
            index=1,
            need_id=879609,
            title='Adult Games: Non-Skating Officials',
            url='https://example.test/needs/879609/shifts',
            shifts=SHIFTS,
            payload=PAYLOAD
        )

        assert capsys.readouterr().out == (
            '1. Adult Games: Non-Skating Officials - 2 new shifts\n'
        )


class TestInvalidShiftData:
    def test_the_reason_is_appended_when_there_is_one(
        self, reporter_class, capsys
    ):
        reporter = reporter_class()
        reporter.shift_data_invalid(detail="'duration' is a required property")

        # The trailing blank line is the message's own newline plus
        # printer's; both were there before the renderer moved.
        assert capsys.readouterr().out == (
            '** Unable to create shifts while shift data is invalid **\n\n'
            "'duration' is a required property\n\n"
        )

    def test_unvalidated_data_still_reports(self, reporter_class, capsys):
        # Returning in silence would read as though shifts were created.
        reporter = reporter_class()
        reporter.shift_data_invalid()

        assert capsys.readouterr().out == (
            '** Unable to create shifts while shift data is invalid **\n\n'
        )
