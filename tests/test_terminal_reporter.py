""" Tests for the CLI's terminal renderer.

    The core reports events and never formats them, so the text an
    operator sees is produced here.  These tests pin that text.

    'app/__main__.py' is normally executed as a script, so it is loaded
    by file path.  The renderer writes to the real stdout, which is what
    capsys captures.
"""
# pylint: disable=missing-function-docstring,missing-class-docstring
# pylint: disable=redefined-outer-name

# Imports - Python Standard Library
import importlib.util
from pathlib import Path

# Imports - Third-Party
import pytest

# Imports - Local
from star_pass._reporting import (
    ShiftBatch,
    STEP_FILTER_EVENTS,
    STEP_MATCH_EVENTS,
    STEP_READ_CALENDAR,
    STEP_READ_OPPORTUNITY,
    STEP_STORE_EVENTS
)
from star_pass_cli import step_text

_MAIN_PATH = Path(__file__).resolve().parent.parent / 'app' / '__main__.py'

# One opportunity's worth of sent shifts, in the shape the core reports.
SHIFTS = [
    {'start': '2099-04-09 18:00', 'duration': 120},
    {'start': '2099-04-10 19:30', 'duration': 90}
]
PAYLOAD = {'shifts': SHIFTS}


def batch(**overrides) -> ShiftBatch:
    """ Return a sent batch, with any field replaced. """
    fields = {
        'index': 1,
        'need_id': 879609,
        'title': 'Adult Games: Non-Skating Officials',
        'url': 'https://example.test/needs/879609/shifts',
        'shifts': SHIFTS,
        'skipped': 0,
        'payload': PAYLOAD
    }
    fields.update(overrides)

    return ShiftBatch(**fields)


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
        reporter.step_started(step=STEP_STORE_EVENTS)
        reporter.step_finished()

        assert capsys.readouterr().out == (
            f'\n{step_text(step=STEP_STORE_EVENTS)}...done.\n'
        )

    def test_later_steps_are_not(self, reporter_class, capsys):
        reporter = reporter_class()
        reporter.step_started(step=STEP_FILTER_EVENTS)
        reporter.step_finished()
        reporter.step_started(step=STEP_MATCH_EVENTS)
        reporter.step_finished()

        assert capsys.readouterr().out == (
            f'\n{step_text(step=STEP_FILTER_EVENTS)}...done.\n'
            f'{step_text(step=STEP_MATCH_EVENTS)}...done.\n'
        )

    def test_a_failed_step_closes_its_line(self, reporter_class, capsys):
        # The reason is not printed: it reaches the caller as an
        # exception and is already logged.
        reporter = reporter_class()
        reporter.step_started(step=STEP_READ_CALENDAR)
        reporter.step_failed()

        assert capsys.readouterr().out == (
            f'\n{step_text(step=STEP_READ_CALENDAR)}...\n'
        )

    def test_a_step_names_what_it_is_working_on(
        self, reporter_class, capsys
    ):
        # The send reads each opportunity before writing to it, and
        # which one is the whole content of the line.
        reporter = reporter_class()
        reporter.step_started(
            step=STEP_READ_OPPORTUNITY,
            subject='879609'
        )
        reporter.step_finished()

        assert '879609' in capsys.readouterr().out

    def test_a_step_nobody_worded_names_itself(
        self, reporter_class, capsys
    ):
        # Rather than vanishing, which is what a lookup returning an
        # empty string would do.
        reporter = reporter_class()
        reporter.step_started(step='invented_later')
        reporter.step_finished()

        assert capsys.readouterr().out == '\ninvented_later...done.\n'


class TestCollectionEvents:
    def test_the_calendar_read_is_a_step_like_the_others(
        self, reporter_class, capsys
    ):
        # A step rather than an announcement: it is one of two upstream
        # reads a collection makes, and an operator whose collection
        # stopped needs to see which of them stopped it.
        reporter = reporter_class()
        reporter.step_started(step=STEP_READ_CALENDAR)
        reporter.step_finished()

        assert capsys.readouterr().out == (
            '\nReading data from the Google Calendar service...done.\n'
        )

    def test_a_step_after_the_read_gets_no_second_blank_line(
        self, reporter_class, capsys
    ):
        # The read is the first thing a collection run prints, so it
        # takes the leading blank line and the next step must not.
        reporter = reporter_class()
        reporter.step_started(step=STEP_READ_CALENDAR)
        reporter.step_finished()
        reporter.step_started(step=STEP_FILTER_EVENTS)
        reporter.step_finished()

        assert capsys.readouterr().out == (
            '\nReading data from the Google Calendar service...done.\n'
            f'{step_text(step=STEP_FILTER_EVENTS)}...done.\n'
        )


class TestSendReport:
    def test_basic_names_the_opportunity_and_counts(
        self, reporter_class, capsys
    ):
        reporter = reporter_class(verbosity='basic')
        reporter.opportunity_sent(batch=batch())

        assert capsys.readouterr().out == (
            '1. Adult Games: Non-Skating Officials - 2 new shifts\n'
        )

    def test_basic_makes_a_single_shift_singular(
        self, reporter_class, capsys
    ):
        reporter = reporter_class(verbosity='basic')
        reporter.opportunity_sent(
            batch=batch(
                index=2,
                need_id=879610,
                title='Adult Games: Skating Officials',
                url='https://example.test/needs/879610/shifts',
                shifts=SHIFTS[:1],
                payload={'shifts': SHIFTS[:1]}
            )
        )

        assert capsys.readouterr().out == (
            '2. Adult Games: Skating Officials - 1 new shift\n'
        )

    def test_simple_lists_every_shift_date_and_time(
        self, reporter_class, capsys
    ):
        reporter = reporter_class(verbosity='simple')
        reporter.opportunity_sent(batch=batch())

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
        reporter.opportunity_sent(batch=batch())

        out = capsys.readouterr().out
        assert out.startswith(
            'URL: https://example.test/needs/879609/shifts\n'
            'Opportunity Title: Adult Games: Non-Skating Officials\n'
            'Shift Count: 2\n'
            'Payload:\n'
        )
        assert '"duration": 120' in out

    def test_an_opportunity_that_needed_nothing_says_why(
        self, reporter_class, capsys
    ):
        # Reported like any other, because the send finished with it.
        # A line saying it created nothing, with no reason beside it,
        # would read as a failure.
        reporter = reporter_class(verbosity='basic')
        reporter.opportunity_sent(
            batch=batch(shifts=[], skipped=2, payload={'shifts': []})
        )

        assert capsys.readouterr().out == (
            '1. Adult Games: Non-Skating Officials - 0 new shifts, '
            '2 already in Amplify\n'
        )

    def test_nothing_is_said_about_what_amplify_did_not_hold(
        self, reporter_class, capsys
    ):
        # The usual case, and the clause is left off it entirely.
        reporter = reporter_class(verbosity='basic')
        reporter.opportunity_sent(batch=batch())

        assert 'already in Amplify' not in capsys.readouterr().out

    def test_the_send_says_how_much_of_it_there_is(
        self, reporter_class, capsys
    ):
        # The count a reader watches the send against. Nowhere else to
        # get it: the run does not know what a send would touch.
        reporter = reporter_class()
        reporter.sending_started(opportunities=3)

        assert capsys.readouterr().out == (
            '\nSending shift data to Amplify, across 3 '
            'opportunities...\n'
        )

    def test_one_opportunity_is_singular(self, reporter_class, capsys):
        reporter = reporter_class()
        reporter.sending_started(opportunities=1)

        assert capsys.readouterr().out == (
            '\nSending shift data to Amplify, across 1 '
            'opportunity...\n'
        )

    def test_an_unknown_verbosity_shows_the_least(
        self, reporter_class, capsys
    ):
        # A bad value shows less rather than failing a run that is
        # otherwise fine.
        reporter = reporter_class(verbosity='chatty')
        reporter.opportunity_sent(batch=batch())

        assert capsys.readouterr().out == (
            '1. Adult Games: Non-Skating Officials - 2 new shifts\n'
        )


class TestSlackEvents:
    def test_a_dry_run_shows_the_banner_and_the_payload(
        self, reporter_class, capsys
    ):
        reporter = reporter_class()
        reporter.slack_dry_run(payload=[{'type': 'header'}])

        assert capsys.readouterr().out == (
            '\n** Slack Check Mode Run (no message sent) **\n'
            '[\n'
            '  {\n'
            '    "type": "header"\n'
            '  }\n'
            ']\n'
        )

    def test_an_empty_window_says_nothing_was_posted(
        self, reporter_class, capsys
    ):
        reporter = reporter_class()
        reporter.summary_skipped()

        assert capsys.readouterr().out == (
            'No shifts in the summary window; skipped posting to '
            'Slack.\n'
        )
