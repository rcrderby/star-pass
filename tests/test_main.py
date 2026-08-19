""" Tests for the application entry point (app/__main__.py).

    __main__.py is normally executed as a script, so it is loaded here
    by file path.  What the Slack summary reaches, and the module-level
    helpers object, are replaced with mocks so that main() exercises
    only the argument parsing, the run-mode dispatch and the banner --
    no API call is made.  The banner is asserted through the
    'star_pass' logger via caplog.  The mocked helpers keeps the real
    convert_to_bool so that --check-mode parsing is exercised for real.

    **One run mode is left.**  The two CSV modes are retired: the API
    and the commands over it do what they did.  The Slack summary is
    not retired with them, because nothing replaces it -- it is out of
    the API's scope by decision -- and it is on a schedule.  So these
    tests hold what that schedule depends on: the flags it passes, and
    that the run opens no database.
"""
# pylint: disable=missing-function-docstring,missing-class-docstring
# pylint: disable=redefined-outer-name

# Imports - Python Standard Library
import io
import logging
from unittest.mock import Mock

# Imports - Third-Party
import pytest

# Imports - Local
from star_pass._helpers import Helpers
from conftest import ENTRY_POINT, load_entry_point
from _importing import imported_modules

# Constants
# What the image the schedule runs on does not install, and what the
# '-s' path must therefore not import.  The distribution is 'httpx2'
# and so is the module it provides, which is not 'httpx'.
WEB_MODULES = ('fastapi', 'starlette', 'uvicorn', 'httpx2', 'jsonschema')

# Loading the entry point the way 'conftest' does, in a process that
# has imported nothing else.
LOAD_THE_ENTRY_POINT = (
    'import importlib.util\n'
    'spec = importlib.util.spec_from_file_location(\n'
    f'    "summary", {str(ENTRY_POINT)!r}\n'
    ')\n'
    'module = importlib.util.module_from_spec(spec)\n'
    'spec.loader.exec_module(module)'
)


@pytest.fixture
def app_main():
    # Load app/__main__.py as an importable module. Loading under a name
    # other than '__main__' means the module-level guard does not run
    # main() on import.
    module = load_entry_point()

    # Replace collaborators so main() performs no real work. Preserve the
    # real convert_to_bool so argparse validates --check-mode as in
    # production.
    mock_helpers = Mock()
    mock_helpers.convert_to_bool = Helpers().convert_to_bool
    module.helpers = mock_helpers
    module.AmplifyResponses = Mock()
    module.SlackNotifier = Mock()
    return module


class TestResolveNeedIds:
    def test_repeated_options_accumulate(self, app_main):
        assert app_main.resolve_need_ids(['1', '2']) == ['1', '2']

    def test_comma_separated_values_expand(self, app_main):
        assert app_main.resolve_need_ids(['1,2', '3']) == ['1', '2', '3']

    def test_order_is_preserved_and_duplicates_dropped(self, app_main):
        # Order drives the message, so it must survive de-duplication.
        assert app_main.resolve_need_ids(
            ['3', '1,3', '2', '1']
        ) == ['3', '1', '2']

    def test_blanks_and_spacing_are_ignored(self, app_main):
        assert app_main.resolve_need_ids([' 1 , ,2 ']) == ['1', '2']

    def test_dash_reads_ids_from_stdin(self, app_main):
        # stdin is a value of -N, not a separate option.
        stdin = io.StringIO('607934 628861\n')

        assert app_main.resolve_need_ids(['-'], stdin=stdin) == [
            '607934', '628861'
        ]

    def test_stdin_ids_may_be_newline_separated(self, app_main):
        stdin = io.StringIO('1\n2\n3\n')

        assert app_main.resolve_need_ids(['-'], stdin=stdin) == [
            '1', '2', '3'
        ]

    def test_dash_merges_with_explicit_ids(self, app_main):
        stdin = io.StringIO('2 3')

        assert app_main.resolve_need_ids(['1', '-'], stdin=stdin) == [
            '1', '2', '3'
        ]

    def test_empty_stdin_yields_nothing(self, app_main):
        assert app_main.resolve_need_ids(['-'], stdin=io.StringIO('')) == []

    def test_falls_back_to_the_configured_ids(self, app_main, monkeypatch):
        # With no -N at all, a scheduled run needs no arguments.
        monkeypatch.setattr(
            app_main, 'SLACK_SUMMARY_NEED_IDS', ['11', '22']
        )

        assert app_main.resolve_need_ids(None) == ['11', '22']

    def test_explicit_ids_win_over_the_configured_ids(
            self, app_main, monkeypatch
    ):
        monkeypatch.setattr(app_main, 'SLACK_SUMMARY_NEED_IDS', ['99'])

        assert app_main.resolve_need_ids(['7']) == ['7']

    def test_no_ids_anywhere_returns_empty(self, app_main, monkeypatch):
        monkeypatch.setattr(app_main, 'SLACK_SUMMARY_NEED_IDS', [])

        assert app_main.resolve_need_ids(None) == []


class TestMainRunModeDispatch:
    def test_slack_mode_short_flags(self, app_main, caplog):
        with caplog.at_level(logging.INFO, logger='star_pass'):
            app_main.main(['-s', '-N', '879610'])

        assert 'Run mode is "Post Slack Summary"' in caplog.text
        app_main.AmplifyResponses.return_value.build_summary \
            .assert_called_once_with(
                need_ids=['879610'], title=None, days=None,
                start_in_days=None
            )
        # Dry run by default; channel falls back to the configured value
        # (None in the test environment).
        kwargs = app_main.SlackNotifier.call_args.kwargs
        assert kwargs['channel'] is None
        assert kwargs['check_mode'] is True
        assert isinstance(
            kwargs['reporter'], app_main.TerminalReporter
        )
        app_main.SlackNotifier.return_value.post_summary \
            .assert_called_once()

    def test_slack_mode_long_flags_and_options(self, app_main):
        app_main.main(
            [
                '--post-slack-summary',
                '--need-id', '5',
                '--days', '3',
                '--slack-title', 'Custom',
                '--slack-channel', 'C999',
                '--check-mode', 'false'
            ]
        )

        app_main.AmplifyResponses.return_value.build_summary \
            .assert_called_once_with(
                need_ids=['5'], title='Custom', days=3,
                start_in_days=None
            )
        kwargs = app_main.SlackNotifier.call_args.kwargs
        assert kwargs['channel'] == 'C999'
        assert kwargs['check_mode'] is False
        assert isinstance(
            kwargs['reporter'], app_main.TerminalReporter
        )


class TestSlackNeedIdOptions:
    def test_repeated_option_reaches_the_builder(self, app_main):
        app_main.main(['-s', '-N', '1', '-N', '2'])

        app_main.AmplifyResponses.return_value.build_summary \
            .assert_called_once_with(
                need_ids=['1', '2'], title=None, days=None,
                start_in_days=None
            )

    def test_comma_separated_option_reaches_the_builder(self, app_main):
        app_main.main(['-s', '-N', '1,2'])

        app_main.AmplifyResponses.return_value.build_summary \
            .assert_called_once_with(
                need_ids=['1', '2'], title=None, days=None,
                start_in_days=None
            )

    def test_configured_ids_allow_a_bare_run(self, app_main, monkeypatch):
        monkeypatch.setattr(app_main, 'SLACK_SUMMARY_NEED_IDS', ['4', '5'])

        app_main.main(['-s'])

        app_main.AmplifyResponses.return_value.build_summary \
            .assert_called_once_with(
                need_ids=['4', '5'], title=None, days=None,
                start_in_days=None
            )


class TestSlackWindowOffset:
    def test_the_offset_reaches_the_builder(self, app_main):
        # The Friday notice covering Saturday and Sunday.
        app_main.main(['-s', '-N', '5', '-D', '1', '-d', '2'])

        app_main.AmplifyResponses.return_value.build_summary \
            .assert_called_once_with(
                need_ids=['5'], title=None, days=2, start_in_days=1
            )

    def test_zero_starts_today(self, app_main):
        app_main.main(['-s', '-N', '5', '--start-in-days', '0'])

        app_main.AmplifyResponses.return_value.build_summary \
            .assert_called_once_with(
                need_ids=['5'], title=None, days=None, start_in_days=0
            )

    def test_a_negative_offset_exits_nonzero(self, app_main):
        with pytest.raises(SystemExit) as exc_info:
            app_main.main(['-s', '-N', '5', '-D', '-1'])

        assert exc_info.value.code != 0
        app_main.AmplifyResponses.assert_not_called()


class TestMainArgumentErrors:
    def test_no_mode_exits_nonzero(self, app_main, capsys):
        # The message has to name both ways in, because "no arguments"
        # is what somebody types when they do not yet know either --
        # and it is a different error from the one a run mode with no
        # need IDs gives.
        with pytest.raises(SystemExit) as exc_info:
            app_main.main([])

        assert exc_info.value.code != 0
        # The wording of the no-selection error, not the usage banner
        # above it, which names every command whatever went wrong.
        assert 'or a command such as' in capsys.readouterr().err
        app_main.AmplifyResponses.assert_not_called()

    @pytest.mark.parametrize(
        'retired',
        ('-g', '--get-gcal-events', '-c', '--create-amplify-shifts')
    )
    def test_a_retired_run_mode_is_no_longer_a_flag(
        self, app_main, retired
    ):
        # The API and the commands over it do what these did, and a
        # flag that still parsed would send somebody to a CSV path
        # that is not there.
        with pytest.raises(SystemExit) as exc_info:
            app_main.main([retired])
        assert exc_info.value.code != 0

    def test_slack_without_need_id_exits_nonzero(
            self, app_main, monkeypatch
    ):
        # No -N and no configured IDs leaves nothing to summarize.
        monkeypatch.setattr(app_main, 'SLACK_SUMMARY_NEED_IDS', [])
        with pytest.raises(SystemExit) as exc_info:
            app_main.main(['-s'])
        assert exc_info.value.code != 0
        app_main.AmplifyResponses.assert_not_called()

    def test_slack_mode_rejects_create_option(self, app_main):
        with pytest.raises(SystemExit) as exc_info:
            app_main.main(['-s', '-N', '5', '-i', 'x.csv'])
        assert exc_info.value.code != 0
        app_main.AmplifyResponses.assert_not_called()

    def test_zero_days_exits_nonzero(self, app_main):
        # Day one is today, so a window must cover at least one day.
        with pytest.raises(SystemExit) as exc_info:
            app_main.main(['-s', '-N', '5', '-d', '0'])
        assert exc_info.value.code != 0
        app_main.AmplifyResponses.assert_not_called()

    def test_negative_days_exits_nonzero(self, app_main):
        with pytest.raises(SystemExit) as exc_info:
            app_main.main(['-s', '-N', '5', '-d', '-2'])
        assert exc_info.value.code != 0
        app_main.AmplifyResponses.assert_not_called()

    def test_non_numeric_days_exits_nonzero(self, app_main):
        with pytest.raises(SystemExit) as exc_info:
            app_main.main(['-s', '-N', '5', '-d', 'today'])
        assert exc_info.value.code != 0

    def test_invalid_check_mode_value_exits_nonzero(self, app_main):
        with pytest.raises(SystemExit) as exc_info:
            app_main.main(['-c', '-i', 'x.csv', '-C', 'maybe'])
        assert exc_info.value.code != 0

    def test_invalid_verbosity_choice_exits_nonzero(self, app_main):
        with pytest.raises(SystemExit) as exc_info:
            app_main.main(['-c', '-i', 'x.csv', '-o', 'loud'])
        assert exc_info.value.code != 0

    def test_invalid_gcal_name_choice_exits_nonzero(self, app_main):
        with pytest.raises(SystemExit) as exc_info:
            app_main.main(['-g', '-n', 'nope'])
        assert exc_info.value.code != 0

    def test_help_exits_zero(self, app_main):
        with pytest.raises(SystemExit) as exc_info:
            app_main.main(['--help'])
        assert exc_info.value.code == 0


class TestCredentialPreflight:
    # A missing credential must be named before any request is sent.
    # Without the preflight the run sent 'Bearer None', and reported the
    # resulting 401 -- which says nothing about the real cause.

    @pytest.mark.parametrize(
        'argv, missing',
        [
            (['-s', '-N', '5'], 'AMPLIFY_TOKEN'),
        ]
    )
    def test_missing_credential_exits(
        self, app_main, monkeypatch, caplog, argv, missing
    ):
        monkeypatch.delenv(missing, raising=False)

        with caplog.at_level(logging.ERROR, logger='star_pass'):
            with pytest.raises(SystemExit) as exc_info:
                app_main.main(argv)

        assert exc_info.value.code == 1
        assert missing in caplog.text
        # The run mode never started.
        app_main.AmplifyResponses.assert_not_called()

    def test_slack_token_required_only_for_a_live_post(
        self, app_main, monkeypatch, caplog
    ):
        monkeypatch.delenv('SLACK_BOT_TOKEN', raising=False)

        with caplog.at_level(logging.ERROR, logger='star_pass'):
            with pytest.raises(SystemExit):
                app_main.main(['-s', '-N', '5', '-C', 'false'])

        assert 'SLACK_BOT_TOKEN' in caplog.text

    def test_check_mode_does_not_require_the_slack_token(
        self, app_main, monkeypatch
    ):
        # A dry run builds the message but never contacts Slack.
        monkeypatch.delenv('SLACK_BOT_TOKEN', raising=False)

        app_main.main(['-s', '-N', '5'])

        app_main.SlackNotifier.return_value.post_summary \
            .assert_called_once()


class TestRunFailureHandling:
    # A run mode that reports a failure and raises must exit non-zero
    # without a traceback landing on top of the message it just logged.

    def test_value_error_exits_nonzero(self, app_main):
        app_main.AmplifyResponses.side_effect = ValueError(
            'LOCAL_TIMEZONE is not a known time zone'
        )

        with pytest.raises(SystemExit) as exc_info:
            app_main.main(['-s', '-N', '5'])

        assert exc_info.value.code == 1

    def test_unexpected_error_still_propagates(self, app_main):
        # Only expected failures are converted; a genuine bug must keep
        # its traceback.
        app_main.AmplifyResponses.side_effect = RuntimeError('unexpected')

        with pytest.raises(RuntimeError):
            app_main.main(['-s', '-N', '5'])


class TestWhatTheScheduledSummaryDependsOn:
    # '.github/workflows/slack-summary.yml' runs
    # 'python /app/__main__.py -s -C ... -d ... -D ...' inside the
    # container, twice a week, and it is the only thing in the
    # repository on a schedule.  These hold what that invocation needs.

    def test_the_flags_the_schedule_passes_are_all_accepted(
        self, app_main
    ):
        app_main.main(
            ['-s', '-N', '5', '-C', 'true', '-d', '2', '-D', '1']
        )

        app_main.AmplifyResponses.return_value.build_summary \
            .assert_called_once_with(
                need_ids=['5'], title=None, days=2, start_in_days=1
            )

    def test_the_summary_opens_no_database(
        self, app_main, monkeypatch
    ):
        # The runner is ephemeral with no volume, so a database opened
        # here would be a file written into a container about to be
        # destroyed -- and would fail outright where the path is not
        # writable.  A dispatcher that opened one for every invocation
        # is the way this would be lost, so it is held here.
        def refuse(*args, **kwargs):
            """ Stand in for opening a database, and refuse. """
            del args, kwargs

            raise AssertionError(
                'the Slack summary opened a database'
            )

        monkeypatch.setattr('star_pass._database.connect', refuse)

        app_main.main(['-s', '-N', '5'])

        app_main.SlackNotifier.return_value.post_summary \
            .assert_called_once()

    def test_the_summary_imports_nothing_its_image_does_not_carry(
        self
    ) -> None:
        # The image the schedule runs on installs the core
        # requirements alone (the Dockerfile's 'slack' target), so one
        # of these imported on this path is a missing dependency
        # discovered by a scheduled post rather than here.  Asked in a
        # process of its own, because this suite has imported the
        # service long before it reaches this line.
        loaded = imported_modules(statement=LOAD_THE_ENTRY_POINT)

        assert not set(loaded) & set(WEB_MODULES)

    def test_the_entry_point_did_load_in_that_process(self) -> None:
        # What gives the test above its meaning: the packages are
        # absent because nothing on this path imports them, not
        # because the entry point failed to load and imported nothing
        # at all.
        loaded = imported_modules(statement=LOAD_THE_ENTRY_POINT)

        assert 'star_pass_cli' in loaded
        assert 'slack_sdk' in loaded
