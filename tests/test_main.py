""" Tests for the application entry point (app/__main__.py).

    __main__.py is normally executed as a script, so it is loaded here
    by file path. CreateShifts, GCALData, and the module-level helpers
    object are replaced with mocks so that main() exercises only the
    run-mode dispatch and banner output -- no CSV is read, no API call
    is made, and banner text is asserted via the mocked printer (the
    real printer binds sys.stdout at import time, which defeats stdout
    capture fixtures).
"""
# pylint: disable=missing-function-docstring,missing-class-docstring
# pylint: disable=redefined-outer-name

# Imports - Python Standard Library
import importlib.util
from pathlib import Path
from unittest.mock import Mock

# Imports - Third-Party
import pytest

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
    # output is observable through the mocked printer.
    module.CreateShifts = Mock()
    module.GCALData = Mock()
    module.helpers = Mock()
    return module


def _printed(app_main) -> str:
    # Join every message passed to helpers.printer().
    return '\n'.join(
        call.kwargs.get('message', '')
        for call in app_main.helpers.printer.call_args_list
    )


class TestMainRunModeBanners:
    def test_create_mode_prints_banner_and_runs(self, app_main):
        app_main.argv = [
            'prog', 'mode=create_amplify_shifts', 'input_file=x.csv'
        ]
        app_main.main()

        printed = _printed(app_main)
        assert 'Run mode is "Create Amplify Shifts"' in printed
        app_main.CreateShifts.assert_called_once()

    def test_get_mode_prints_banner_and_runs(self, app_main):
        app_main.argv = ['prog', 'mode=get_gcal_events', 'gcal_name=events']
        app_main.main()

        printed = _printed(app_main)
        assert 'Run mode is "Get Google Calendar Events"' in printed
        app_main.GCALData.assert_called_once()

    def test_invalid_mode_prints_message_and_runs_nothing(self, app_main):
        app_main.argv = ['prog', 'mode=bogus']
        app_main.main()

        printed = _printed(app_main)
        assert 'Invalid or unset' in printed
        app_main.CreateShifts.assert_not_called()
        app_main.GCALData.assert_not_called()
