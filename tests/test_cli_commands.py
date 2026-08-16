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
from star_pass._preview import BLOCKER_NO_OPPORTUNITY, BLOCKER_REASONS
from star_pass_cli import _mode, _render
from star_pass_cli._commands import COMMANDS, GROUPS, run_command, selected
from star_pass_client import Client, LocalClient
from star_pass_contract import EventView


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


class TestShowingARun:
    def test_a_run_shows_what_it_is(
        self,
        capsys: pytest.CaptureFixture,
        cli: Callable[..., int],
        populated: str
    ) -> None:
        status = cli('runs', 'show', populated)

        assert status == 0
        assert populated in capsys.readouterr().out

    def test_a_run_shows_its_events(
        self,
        capsys: pytest.CaptureFixture,
        cli: Callable[..., int],
        populated: str
    ) -> None:
        cli('runs', 'show', populated)
        shown = capsys.readouterr().out

        assert 'EVENTS' in shown
        assert 'Adult Scrimmages' in shown

    def test_a_run_shows_its_opportunities_and_change_log(
        self,
        capsys: pytest.CaptureFixture,
        cli: Callable[..., int],
        populated: str
    ) -> None:
        # All three arrive in one answer because a reader looking at
        # one is looking at all three, so all three are shown.
        cli('runs', 'show', populated)
        shown = capsys.readouterr().out

        assert 'OPPORTUNITIES' in shown
        assert 'Adult Scrimmages: Skating Officials' in shown
        assert 'CHANGE LOG' in shown
        assert 'Nudged Adult Scrimmages by 30 minutes' in shown

    def test_an_unknown_run_says_so_and_fails(
        self,
        capsys: pytest.CaptureFixture,
        cli: Callable[..., int]
    ) -> None:
        status = cli('runs', 'show', 'no-such-run')

        assert status == 1
        assert 'no-such-run' in capsys.readouterr().out


class TestListingRevisions:
    def test_the_revisions_are_listed_oldest_first(
        self,
        capsys: pytest.CaptureFixture,
        cli: Callable[..., int],
        populated: str
    ) -> None:
        status = cli('runs', 'revisions', populated)
        shown = capsys.readouterr().out

        assert status == 0
        assert shown.index('As collected') < shown.index('Edited')

    def test_the_revision_being_edited_is_marked(
        self,
        capsys: pytest.CaptureFixture,
        cli: Callable[..., int],
        populated: str
    ) -> None:
        cli('runs', 'revisions', populated)

        assert _render.CURRENT in capsys.readouterr().out

    def test_a_run_with_no_revisions_says_so(
        self,
        capsys: pytest.CaptureFixture,
        cli: Callable[..., int],
        run_id: str
    ) -> None:
        status = cli('runs', 'revisions', run_id)

        assert status == 0
        assert 'no revisions yet' in capsys.readouterr().out


class TestPreviewingARun:
    def test_a_preview_shows_what_each_opportunity_receives(
        self,
        capsys: pytest.CaptureFixture,
        cli: Callable[..., int],
        populated: str
    ) -> None:
        status = cli('runs', 'preview', populated)
        shown = capsys.readouterr().out

        assert status == 0
        assert 'Would create' in shown
        assert 'Adult Scrimmages: Skating Officials' in shown

    def test_a_blocked_event_is_named_with_its_reason(
        self,
        capsys: pytest.CaptureFixture,
        cli: Callable[..., int],
        populated: str
    ) -> None:
        # The identifier the contract publishes is written for a
        # program to branch on; a person is told what it means.
        cli('runs', 'preview', populated)
        shown = capsys.readouterr().out

        assert 'event-3' in shown
        assert _render.BLOCKER_PHRASES[BLOCKER_NO_OPPORTUNITY] in shown

    def test_a_blocked_run_says_nothing_can_be_sent(
        self,
        capsys: pytest.CaptureFixture,
        cli: Callable[..., int],
        populated: str
    ) -> None:
        # A reader skimming the totals should not think the blocked
        # events below cost them only those shifts.
        cli('runs', 'preview', populated)

        assert _render.NOTHING_SENDABLE in capsys.readouterr().out


class TestShowingAJob:
    def test_a_job_shows_where_it_has_got_to(
        self,
        capsys: pytest.CaptureFixture,
        cli: Callable[..., int],
        job_id: str
    ) -> None:
        status = cli('jobs', 'show', job_id)
        shown = capsys.readouterr().out

        assert status == 0
        assert job_id in shown
        assert 'queued' in shown

    def test_an_unknown_job_says_so_and_fails(
        self,
        capsys: pytest.CaptureFixture,
        cli: Callable[..., int]
    ) -> None:
        status = cli('jobs', 'show', 'no-such-job')

        assert status == 1
        assert 'no-such-job' in capsys.readouterr().out


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

    def test_a_value_an_answer_did_not_carry_shows_a_dash(self) -> None:
        assert _render.shown(value=None) == _render.NOTHING

    def test_a_value_an_answer_carried_shows_itself(self) -> None:
        # Including zero, which is a value and not an absence.
        assert _render.shown(value=0) == '0'

    def test_named_values_are_aligned_on_their_names(self) -> None:
        first, second = _render.labelled(
            pairs=(('Job', 'j-1'), ('Status', 'queued'))
        ).split('\n')

        assert first.index('j-1') == second.index('queued')

    def test_a_section_with_no_rows_says_so(self) -> None:
        # A heading over nothing but column names reads as an answer
        # that failed rather than as one that is empty.
        rendered = _render.section(
            heading='EVENTS',
            headers=('ID',),
            rows=[],
            empty='Nothing here.'
        )

        assert rendered == 'EVENTS\nNothing here.'

    def test_a_section_with_rows_shows_them_under_the_heading(
        self
    ) -> None:
        rendered = _render.section(
            heading='EVENTS',
            headers=('ID',),
            rows=[('event-1',)],
            empty='Nothing here.'
        )

        assert rendered == 'EVENTS\nID\nevent-1'


class TestWhatAnEventShows:
    def test_the_written_event_holds_what_the_contract_publishes(
        self,
        make_event_document: Callable[..., Any]
    ) -> None:
        # The tests below set one field of a written document rather
        # than arranging a database to produce it, which is only safe
        # while the document is the shape a client really answers with.
        assert set(make_event_document()) == set(
            EventView.model_json_schema(by_alias=True)['properties']
        )

    def test_an_ordinary_event_is_not_noted(
        self,
        make_event_document: Callable[..., Any]
    ) -> None:
        # A note on every row would bury the rows worth reading twice.
        assert _render.event_notes(
            event=make_event_document()
        ) == _render.NOTHING

    def test_an_event_with_no_opportunity_is_noted(
        self,
        make_event_document: Callable[..., Any]
    ) -> None:
        assert 'blocks the send' in _render.event_notes(
            event=make_event_document(blocking=True)
        )

    def test_an_event_repeating_another_names_it(
        self,
        make_event_document: Callable[..., Any]
    ) -> None:
        assert 'repeats event-1' in _render.event_notes(
            event=make_event_document(duplicateOf='event-1')
        )

    def test_a_shortened_shift_names_the_maximum(
        self,
        make_event_document: Callable[..., Any]
    ) -> None:
        assert 'capped at 120' in _render.event_notes(
            event=make_event_document(cappedAt=120)
        )

    def test_a_fuzzy_match_is_noted_with_its_score(
        self,
        make_event_document: Callable[..., Any]
    ) -> None:
        assert 'scored 71' in _render.event_notes(
            event=make_event_document(
                match={'kind': 'fuzzy', 'keyword': None, 'score': 71}
            )
        )

    def test_a_keyword_match_is_not_noted(
        self,
        make_event_document: Callable[..., Any]
    ) -> None:
        assert _render.event_notes(
            event=make_event_document(
                match={
                    'kind': 'keyword',
                    'keyword': 'scrimmage',
                    'score': None
                }
            )
        ) == _render.NOTHING

    def test_an_event_pulled_in_by_hand_is_noted(
        self,
        make_event_document: Callable[..., Any]
    ) -> None:
        assert 'added by hand' in _render.event_notes(
            event=make_event_document(addedByHand=True)
        )

    def test_an_event_with_no_role_shows_a_dash(
        self,
        make_event_document: Callable[..., Any]
    ) -> None:
        assert _render.roles_text(
            event=make_event_document(roles=[])
        ) == _render.NOTHING

    def test_a_role_shows_the_volunteers_it_wants(
        self,
        make_event_document: Callable[..., Any]
    ) -> None:
        assert _render.roles_text(
            event=make_event_document()
        ) == '905196 (4)'


class TestWhatAnOpportunityShows:
    def test_the_offsets_are_signed(self) -> None:
        # A bare number leaves a reader guessing which way the shift
        # moved from the event.
        row = _render.opportunity_row(
            opportunity={
                'needId': '905196',
                'title': 'Adult Scrimmages',
                'maxLength': None,
                'offsetStart': 15,
                'offsetEnd': -30,
                'defaultSlots': 4
            }
        )

        assert row[_render.OPPORTUNITY_HEADERS.index('OFFSETS')] == (
            '+15/-30'
        )


class TestWhyAnEventCannotBeSent:
    def test_every_reason_the_core_publishes_is_worded(self) -> None:
        # A reason with no wording shows as its identifier, which is
        # written for a program to branch on rather than to be read.
        assert set(_render.BLOCKER_PHRASES) == set(BLOCKER_REASONS)

    def test_a_reason_with_no_wording_shows_as_itself(self) -> None:
        row = _render.blocker_row(
            blocker={'eventId': 'event-1', 'reason': 'invented_later'}
        )

        assert row[_render.BLOCKER_HEADERS.index('REASON')] == (
            'invented_later'
        )


class TestTheCommandsOnOffer:
    def test_every_command_asks_an_operation_both_clients_offer(
        self
    ) -> None:
        # Both clients inherit the generated surface, so a command
        # naming an operation neither has is a typo the parser would
        # not catch.
        for command in COMMANDS:
            assert callable(getattr(LocalClient, command.operation))
            assert callable(getattr(Client, command.operation))

    def test_every_command_belongs_to_a_described_group(self) -> None:
        for command in COMMANDS:
            assert command.group in GROUPS

    def test_every_command_is_reachable_from_the_command_line(
        self,
        build_parser: Callable[[], Any]
    ) -> None:
        for command in COMMANDS:
            words = [command.group, command.word]

            if command.argument is not None:
                words.append('a-value')

            args = build_parser().parse_args(words)

            assert selected(args=args) == (command.group, command.word)

    def test_every_command_takes_the_address_of_a_service(
        self,
        build_parser: Callable[[], Any]
    ) -> None:
        # Held on a parent parser, so a command added later cannot be
        # the one that forgets to offer the remote mode (D2).
        for command in COMMANDS:
            words = [command.group, command.word]

            if command.argument is not None:
                words.append('a-value')

            args = build_parser().parse_args(
                words + ['--api-url', 'https://star-pass.test']
            )

            assert args.api_url == 'https://star-pass.test'

    def test_a_command_addresses_what_its_operation_addresses(
        self,
        build_parser: Callable[[], Any]
    ) -> None:
        # The name argparse stores it under is the name the operation
        # takes, which is what lets one dispatcher pass it on.
        for command in COMMANDS:
            if command.argument is None:
                continue

            args = build_parser().parse_args(
                [command.group, command.word, 'a-value']
            )

            assert getattr(args, command.argument) == 'a-value'


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
