#!/usr/bin/env python3
""" The command line client's reading of the deployment's own settings.

    The three 'config' commands: what the service was configured
    with, whether Amplify still takes the credential it is running on,
    and the titles the data model has not matched.  Its own module
    rather than three classes in 'test_cli_commands.py', which is near
    the thousand-line cap the linter holds a module to, and it is the
    natural three to move: the module they exercise is its own module
    for the same reason, since a setting is neither a run nor
    something somebody did to one.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring
# pylint: disable=too-many-arguments,too-many-positional-arguments

# Imports - Python Standard Library
from typing import Any, Callable

# Imports - Third-Party
import pytest

# Imports - Local
from star_pass_cli import _configuration, _render

# Constants
# Where the settings a configuration reports are read, so a test can
# show a value reaching the display from the setting it belongs to.
SETTINGS_READ_IN = 'star_pass_contract._views'


class TestShowingTheConfiguration:
    def test_the_settings_a_collection_runs_under_are_shown(
        self,
        capsys: pytest.CaptureFixture,
        cli: Callable[..., int],
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(SETTINGS_READ_IN + '.GCAL_TIMEZONE', 'UTC')
        monkeypatch.setattr(SETTINGS_READ_IN + '.FUZZY_MATCH_THRESHOLD', 55)

        status = cli('config', 'show')
        shown = capsys.readouterr().out

        assert status == 0
        assert 'Timezone         UTC' in shown
        assert 'Match threshold  55' in shown

    def test_each_calendar_is_shown_with_what_it_is_searched_for(
        self,
        capsys: pytest.CaptureFixture,
        cli: Callable[..., int],
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            SETTINGS_READ_IN + '.GCAL_CALENDARS',
            {
                'practices': {
                    'gcal_id': 'a-calendar',
                    'query_strings': ['officials', 'scrimmage']
                }
            }
        )

        cli('config', 'show')

        assert 'practices  officials, scrimmage' in capsys.readouterr().out

    def test_a_calendar_searched_for_nothing_says_what_that_means(
        self
    ) -> None:
        # The contract publishes the empty query string the deployment
        # configured; what it means to a reader is worded here.
        row = _configuration.calendar_row(
            calendar={'key': 'events', 'searchTerms': ['']}
        )

        assert row[_configuration.CALENDAR_HEADERS.index('SEARCHED FOR')] == (
            _configuration.EVERYTHING
        )

    def test_the_terms_a_title_is_never_collected_under_are_listed(
        self
    ) -> None:
        assert _configuration.excluded_text(
            terms=['derby daze', 'summer camp']
        ) == 'derby daze, summer camp'

    def test_a_deployment_excluding_nothing_shows_a_dash(self) -> None:
        assert _configuration.excluded_text(terms=[]) == _render.NOTHING


class TestTestingTheCredential:
    def test_a_working_credential_is_said_to_be_working(
        self,
        answer_requests: Callable[..., list],
        capsys: pytest.CaptureFixture,
        cli: Callable[..., int]
    ) -> None:
        answer_requests(lambda _request: {'data': []})

        status = cli('config', 'credential')

        assert status == 0
        assert _configuration.WORKING in capsys.readouterr().out

    def test_the_four_characters_are_shown_and_no_more(
        self,
        answer_requests: Callable[..., list],
        capsys: pytest.CaptureFixture,
        cli: Callable[..., int]
    ) -> None:
        answer_requests(lambda _request: {'data': []})

        cli('config', 'credential')
        shown = capsys.readouterr().out

        assert shown.splitlines()[1].endswith('oken')
        assert 'test-amplify-token' not in shown

    def test_a_credential_that_is_not_there_says_so_with_its_reason(
        self,
        capsys: pytest.CaptureFixture,
        cli: Callable[..., int],
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # An answer rather than a failure, so the command succeeds and
        # what it printed is the finding.
        monkeypatch.delenv('AMPLIFY_TOKEN', raising=False)

        status = cli('config', 'credential')
        shown = capsys.readouterr().out

        assert status == 0
        assert _configuration.NOT_WORKING in shown
        assert 'AMPLIFY_TOKEN' in shown


class TestListingUnmatchedTitles:
    def test_each_title_is_shown_with_how_often_it_was_seen(
        self,
        capsys: pytest.CaptureFixture,
        cli: Callable[..., int],
        unmatched: Any
    ) -> None:
        for _sighting in range(2):
            unmatched.record(
                calendar='events',
                title='Jet City vs Cherry City',
                principal_id='static-token'
            )

        status = cli('config', 'unmatched')
        shown = capsys.readouterr().out

        assert status == 0
        assert 'Jet City vs Cherry City' in shown
        assert '  2  ' in shown

    def test_an_empty_log_says_so_rather_than_showing_a_heading(
        self,
        capsys: pytest.CaptureFixture,
        cli: Callable[..., int]
    ) -> None:
        # A finding rather than an empty screen: every title anybody
        # recorded matched a category.
        status = cli('config', 'unmatched')

        assert status == 0
        assert _configuration.NOTHING_UNMATCHED in capsys.readouterr().out
