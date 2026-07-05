""" Tests for the application entry point (app/__main__.py).

    __main__.py is normally executed as a script, so it is loaded here
    by file path. CreateShifts, GCALData, and the module-level helpers
    object are replaced with mocks so that main() exercises only the
    argument parsing, run-mode dispatch, and banner output -- no CSV is
    read, no API call is made, and banner text is asserted via the
    mocked printer (the real printer binds sys.stdout at import time,
    which defeats stdout capture fixtures). The mocked helpers keeps the
    real convert_to_bool so that --check-mode parsing is exercised for
    real.
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

    # Replace collaborators so main() performs no real work and banner
    # output is observable through the mocked printer. Preserve the real
    # convert_to_bool so argparse validates --check-mode as in production.
    mock_helpers = Mock()
    mock_helpers.convert_to_bool = Helpers().convert_to_bool
    module.helpers = mock_helpers
    module.CreateShifts = Mock()
    module.GCALData = Mock()
    return module


class TestMainRunModeBanners:
    def test_create_mode_logs_banner_and_runs(self, app_main, caplog):
        with caplog.at_level(logging.INFO, logger='star_pass'):
            app_main.main(
                ['create_amplify_shifts', '--input-file', 'x.csv']
            )

        assert 'Run mode is "Create Amplify Shifts"' in caplog.text
        app_main.CreateShifts.assert_called_once_with(
            input_file='x.csv',
            check_mode=True,
            output_verbosity='basic'
        )
        app_main.CreateShifts.return_value.create_new_shifts \
            .assert_called_once()

    def test_create_mode_alias_and_options(self, app_main):
        app_main.main(
            [
                'c',
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

    def test_get_mode_logs_banner_and_runs(self, app_main, caplog):
        with caplog.at_level(logging.INFO, logger='star_pass'):
            app_main.main(['get_gcal_events', '--gcal-name', 'events'])

        assert 'Run mode is "Get Google Calendar Events"' in caplog.text
        app_main.GCALData.assert_called_once_with(gcal_name='events')

    def test_get_mode_alias(self, app_main):
        app_main.main(['g', '--gcal-name', 'practices'])

        app_main.GCALData.assert_called_once_with(gcal_name='practices')


class TestMainArgumentErrors:
    def test_missing_mode_exits_nonzero(self, app_main):
        with pytest.raises(SystemExit) as exc_info:
            app_main.main([])
        assert exc_info.value.code != 0
        app_main.CreateShifts.assert_not_called()
        app_main.GCALData.assert_not_called()

    def test_invalid_mode_exits_nonzero(self, app_main):
        with pytest.raises(SystemExit) as exc_info:
            app_main.main(['bogus'])
        assert exc_info.value.code != 0

    def test_missing_required_input_file_exits_nonzero(self, app_main):
        with pytest.raises(SystemExit) as exc_info:
            app_main.main(['create_amplify_shifts'])
        assert exc_info.value.code != 0
        app_main.CreateShifts.assert_not_called()

    def test_invalid_check_mode_value_exits_nonzero(self, app_main):
        with pytest.raises(SystemExit) as exc_info:
            app_main.main(
                [
                    'create_amplify_shifts',
                    '--input-file', 'x.csv',
                    '--check-mode', 'maybe'
                ]
            )
        assert exc_info.value.code != 0

    def test_invalid_verbosity_choice_exits_nonzero(self, app_main):
        with pytest.raises(SystemExit) as exc_info:
            app_main.main(
                [
                    'create_amplify_shifts',
                    '--input-file', 'x.csv',
                    '--output-verbosity', 'loud'
                ]
            )
        assert exc_info.value.code != 0

    def test_invalid_gcal_name_choice_exits_nonzero(self, app_main):
        with pytest.raises(SystemExit) as exc_info:
            app_main.main(['get_gcal_events', '--gcal-name', 'nope'])
        assert exc_info.value.code != 0

    def test_help_exits_zero(self, app_main):
        with pytest.raises(SystemExit) as exc_info:
            app_main.main(['--help'])
        assert exc_info.value.code == 0
