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
