#!/usr/bin/env python3
""" The reading commands, and which mode they run in.

    What a command shows is pinned here.  Whether the two modes agree
    on what to show it is pinned in 'test_local_client.py', which
    compares the clients directly; a command renders one document and
    does not know which mode produced it.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring
# pylint: disable=too-many-arguments,too-many-positional-arguments

# Imports - Python Standard Library
from pathlib import Path
from typing import Any, Callable

# Imports - Third-Party
import pytest

# Imports - Local
from star_pass._exceptions import ConfigurationError
from star_pass_cli import _mode, _render
from star_pass_cli._commands import run_command, selected
from star_pass_client import Client, LocalClient


@pytest.fixture(name='build_parser')
def fixture_build_parser(
    entry_point: Any
) -> Callable[[], Any]:
    """ Return the entry point's parser builder. """
    return entry_point.build_parser


@pytest.fixture(name='cli')
def fixture_cli(
    build_parser: Callable[[], Any],
    monkeypatch: pytest.MonkeyPatch,
    service_database: Path
) -> Callable[..., int]:
    """ Return a way to run a command against the test's database.

        Nothing is stubbed: the command picks its own client, so the
        mode selection is exercised rather than replaced. The database
        it opens is redirected instead, which is the one thing a test
        cannot let it choose.
    """
    del service_database

    monkeypatch.delenv(_mode.API_URL_VARIABLE, raising=False)

    def run(*argv: str) -> int:
        """ Parse the arguments and run what they selected. """
        return run_command(args=build_parser().parse_args(argv))

    return run


class TestChoosingAMode:
    def test_no_address_reads_the_local_database(
        self,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Local by default, so the command line client never needs a
        # server to be running (D2).
        monkeypatch.delenv(_mode.API_URL_VARIABLE, raising=False)

        assert isinstance(_mode.client_for(), LocalClient)

    def test_an_address_reaches_a_service(
        self,
        monkeypatch: pytest.MonkeyPatch,
        api_credential: str
    ) -> None:
        monkeypatch.setenv(_mode.API_TOKEN_VARIABLE, api_credential)

        client = _mode.client_for(api_url='https://star-pass.test')

        assert isinstance(client, Client)

    def test_the_environment_supplies_an_address(
        self,
        monkeypatch: pytest.MonkeyPatch,
        api_credential: str
    ) -> None:
        monkeypatch.setenv(_mode.API_TOKEN_VARIABLE, api_credential)
        monkeypatch.setenv(
            _mode.API_URL_VARIABLE,
            'https://star-pass.test'
        )

        assert isinstance(_mode.client_for(), Client)

    def test_the_flag_beats_the_environment(
        self,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A flag is what somebody types for one command; the
        # environment is what a shell carries for a session.
        monkeypatch.setenv(_mode.API_URL_VARIABLE, 'https://from-env.test')

        assert _mode.service_url(
            supplied='https://from-flag.test'
        ) == 'https://from-flag.test'

    def test_an_address_without_a_credential_is_refused(
        self,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Refused before the request, so the failure names what is
        # missing rather than arriving as a 401.
        monkeypatch.delenv(_mode.API_TOKEN_VARIABLE, raising=False)

        with pytest.raises(ConfigurationError) as error:
            _mode.client_for(api_url='https://star-pass.test')

        assert _mode.API_TOKEN_VARIABLE in str(error.value)


class TestListingRuns:
    def test_a_run_is_listed(
        self,
        capsys: pytest.CaptureFixture,
        cli: Callable[..., int],
        collected: str
    ) -> None:
        status = cli('runs', 'list')

        assert status == 0
        assert collected in capsys.readouterr().out

    def test_the_table_has_a_header(
        self,
        capsys: pytest.CaptureFixture,
        cli: Callable[..., int],
        collected: str
    ) -> None:
        del collected

        cli('runs', 'list')

        assert 'CALENDAR' in capsys.readouterr().out

    def test_no_runs_says_so_rather_than_showing_a_header(
        self,
        capsys: pytest.CaptureFixture,
        cli: Callable[..., int]
    ) -> None:
        status = cli('runs', 'list')

        assert status == 0
        assert capsys.readouterr().out.strip() == 'No runs yet.'

    def test_a_command_word_without_a_subcommand_fails(
        self,
        capsys: pytest.CaptureFixture,
        cli: Callable[..., int]
    ) -> None:
        status = cli('runs')

        assert status == 1
        assert 'not a complete command' in capsys.readouterr().out


class TestWhatACommandShows:
    def test_the_window_is_shown_by_the_last_day_it_covers(self) -> None:
        # The contract carries an exclusive end because that is what
        # the server stores; a person reading a run means the last day
        # it covers, so the conversion happens where it is displayed.
        assert _render.window_text(
            window={'start': '2026-09-01', 'end': '2026-10-01'}
        ) == '2026-09-01 to 2026-09-30'

    def test_a_one_day_window_shows_one_day(self) -> None:
        assert _render.window_text(
            window={'start': '2026-09-01', 'end': '2026-09-02'}
        ) == '2026-09-01 to 2026-09-01'

    def test_columns_are_aligned_under_their_headers(self) -> None:
        rendered = _render.table(
            headers=('SHORT', 'NAME'),
            rows=[('a', 'first'), ('bbbbbbb', 'second')]
        )
        header, first, second = rendered.split('\n')

        assert header.index('NAME') == first.index('first')
        assert first.index('first') == second.index('second')

    def test_a_run_with_nothing_unmatched_shows_a_dash(
        self,
        make_run_document: Callable[..., Any]
    ) -> None:
        # A zero in that column reads as a count worth checking; the
        # column exists to draw the eye to runs that need attention.
        row = _render.run_row(run=make_run_document(unmatched=0))

        assert row[_render.RUN_HEADERS.index('UNMATCHED')] == '-'

    def test_a_run_with_something_unmatched_shows_the_count(
        self,
        make_run_document: Callable[..., Any]
    ) -> None:
        row = _render.run_row(run=make_run_document(unmatched=3))

        assert row[_render.RUN_HEADERS.index('UNMATCHED')] == '3'


class TestSelectingACommand:
    def test_a_mode_flag_selects_no_command(
        self,
        build_parser: Callable[[], Any]
    ) -> None:
        # The three run modes predate the API and stay local, so a
        # command must not be read out of a run mode's arguments.
        args = build_parser().parse_args(['-g', '-n', 'events'])

        assert selected(args=args) is None

    def test_a_command_word_selects_a_command(
        self,
        build_parser: Callable[[], Any]
    ) -> None:
        args = build_parser().parse_args(['runs', 'list'])

        assert selected(args=args) == ('runs', 'list')
