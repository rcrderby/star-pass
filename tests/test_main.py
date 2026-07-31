""" Tests for the application entry point (app/__main__.py).

    __main__.py is normally executed as a script, so it is loaded here
    by file path. CreateShifts, GCALData, and the module-level helpers
    object are replaced with mocks so that main() exercises only the
    argument parsing, run-mode dispatch, and banner output -- no CSV is
    read and no API call is made. Run-mode banners are asserted through
    the 'star_pass' logger via caplog. The mocked helpers keeps the real
    convert_to_bool so that --check-mode parsing is exercised for real.
"""
# pylint: disable=missing-function-docstring,missing-class-docstring
# pylint: disable=redefined-outer-name

# Imports - Python Standard Library
import importlib.util
import logging
from pathlib import Path
from unittest.mock import Mock

# Imports - Third-Party
import pytest

# Imports - Local
from star_pass._helpers import Helpers

# Path to the entry-point module.
_MAIN_PATH = Path(__file__).resolve().parent.parent / 'app' / '__main__.py'


@pytest.fixture
def app_main():
    # Load app/__main__.py as an importable module. Loading under a name
    # other than '__main__' means the module-level guard does not run
    # main() on import.
    spec = importlib.util.spec_from_file_location(
        'star_pass_main', _MAIN_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # Replace collaborators so main() performs no real work. Preserve the
    # real convert_to_bool so argparse validates --check-mode as in
    # production.
    mock_helpers = Mock()
    mock_helpers.convert_to_bool = Helpers().convert_to_bool
    module.helpers = mock_helpers
    module.CreateShifts = Mock()
    module.GCALData = Mock()
    module.AmplifyResponses = Mock()
    module.SlackNotifier = Mock()
    return module


class TestMainRunModeDispatch:
    def test_create_mode_short_flags(self, app_main, caplog):
        with caplog.at_level(logging.INFO, logger='star_pass'):
            app_main.main(['-c', '-i', 'x.csv'])

        assert 'Run mode is "Create Amplify Shifts"' in caplog.text
        app_main.CreateShifts.assert_called_once_with(
            input_file='x.csv',
            check_mode=True,
            output_verbosity='basic'
        )
        app_main.CreateShifts.return_value.create_new_shifts \
            .assert_called_once()

    def test_create_mode_long_flags_and_options(self, app_main):
        app_main.main(
            [
                '--create-amplify-shifts',
                '--input-file', 'x.csv',
                '--check-mode', 'false',
                '--output-verbosity', 'simple'
            ]
        )

        app_main.CreateShifts.assert_called_once_with(
            input_file='x.csv',
            check_mode=False,
            output_verbosity='simple'
        )

    def test_get_mode_short_flags(self, app_main, caplog):
        with caplog.at_level(logging.INFO, logger='star_pass'):
            app_main.main(['-g', '-n', 'events'])

        assert 'Run mode is "Get Google Calendar Events"' in caplog.text
        app_main.GCALData.assert_called_once_with(gcal_name='events')

    def test_get_mode_long_flags(self, app_main):
        app_main.main(['--get-gcal-events', '--gcal-name', 'practices'])

        app_main.GCALData.assert_called_once_with(gcal_name='practices')

    def test_slack_mode_short_flags(self, app_main, caplog):
        with caplog.at_level(logging.INFO, logger='star_pass'):
            app_main.main(['-s', '-N', '879610'])

        assert 'Run mode is "Post Slack Summary"' in caplog.text
        app_main.AmplifyResponses.return_value.build_need_summary \
            .assert_called_once_with(need_id='879610', title=None)
        # Dry run by default; channel falls back to the configured value
        # (None in the test environment).
        app_main.SlackNotifier.assert_called_once_with(
            channel=None,
            check_mode=True
        )
        app_main.SlackNotifier.return_value.post_summary \
            .assert_called_once()

    def test_slack_mode_long_flags_and_options(self, app_main):
        app_main.main(
            [
                '--post-slack-summary',
                '--need-id', '5',
                '--slack-title', 'Custom',
                '--slack-channel', 'C999',
                '--check-mode', 'false'
            ]
        )

        app_main.AmplifyResponses.return_value.build_need_summary \
            .assert_called_once_with(need_id='5', title='Custom')
        app_main.SlackNotifier.assert_called_once_with(
            channel='C999',
            check_mode=False
        )


class TestMainArgumentErrors:
    def test_no_mode_exits_nonzero(self, app_main):
        with pytest.raises(SystemExit) as exc_info:
            app_main.main([])
        assert exc_info.value.code != 0
        app_main.CreateShifts.assert_not_called()
        app_main.GCALData.assert_not_called()

    def test_both_modes_exits_nonzero(self, app_main):
        with pytest.raises(SystemExit) as exc_info:
            app_main.main(['-c', '-g', '-i', 'x.csv'])
        assert exc_info.value.code != 0

    def test_create_without_input_file_exits_nonzero(self, app_main):
        with pytest.raises(SystemExit) as exc_info:
            app_main.main(['-c'])
        assert exc_info.value.code != 0
        app_main.CreateShifts.assert_not_called()

    def test_get_without_gcal_name_exits_nonzero(self, app_main):
        with pytest.raises(SystemExit) as exc_info:
            app_main.main(['-g'])
        assert exc_info.value.code != 0
        app_main.GCALData.assert_not_called()

    def test_get_mode_rejects_create_option(self, app_main):
        with pytest.raises(SystemExit) as exc_info:
            app_main.main(['-g', '-n', 'events', '-i', 'x.csv'])
        assert exc_info.value.code != 0
        app_main.GCALData.assert_not_called()

    def test_create_mode_rejects_gcal_name(self, app_main):
        with pytest.raises(SystemExit) as exc_info:
            app_main.main(['-c', '-i', 'x.csv', '-n', 'events'])
        assert exc_info.value.code != 0
        app_main.CreateShifts.assert_not_called()

    def test_slack_without_need_id_exits_nonzero(self, app_main):
        with pytest.raises(SystemExit) as exc_info:
            app_main.main(['-s'])
        assert exc_info.value.code != 0
        app_main.AmplifyResponses.assert_not_called()

    def test_slack_mode_rejects_create_option(self, app_main):
        with pytest.raises(SystemExit) as exc_info:
            app_main.main(['-s', '-N', '5', '-i', 'x.csv'])
        assert exc_info.value.code != 0
        app_main.AmplifyResponses.assert_not_called()

    def test_get_mode_rejects_slack_option(self, app_main):
        with pytest.raises(SystemExit) as exc_info:
            app_main.main(['-g', '-n', 'events', '-N', '5'])
        assert exc_info.value.code != 0
        app_main.GCALData.assert_not_called()

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
            (['-g', '-n', 'events'], 'GCAL_TOKEN'),
            (['-c', '-i', 'x.csv'], 'AMPLIFY_TOKEN'),
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
        app_main.CreateShifts.assert_not_called()
        app_main.GCALData.assert_not_called()
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
        app_main.GCALData.side_effect = ValueError(
            'GCAL_TIME_MIN must be set'
        )

        with pytest.raises(SystemExit) as exc_info:
            app_main.main(['-g', '-n', 'events'])

        assert exc_info.value.code == 1

    def test_unexpected_error_still_propagates(self, app_main):
        # Only expected failures are converted; a genuine bug must keep
        # its traceback.
        app_main.GCALData.side_effect = RuntimeError('unexpected')

        with pytest.raises(RuntimeError):
            app_main.main(['-g', '-n', 'events'])
