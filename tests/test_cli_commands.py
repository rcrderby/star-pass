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
from typing import Any, Callable, List, Tuple

# Imports - Third-Party
import pytest

# Imports - Local
from star_pass._exceptions import ConfigurationError
from star_pass._preview import BLOCKER_NO_OPPORTUNITY, BLOCKER_REASONS
from star_pass._records import (
    JOB_KIND_SEND,
    UNCOLLECTED_EXCLUDED,
    UNCOLLECTED_REASONS,
    UNCOLLECTED_SEARCH
)
from star_pass._repository import JobRepository
from star_pass_cli import _mode, _render, _sending
from star_pass_cli._commands import COMMANDS, GROUPS, selected
from star_pass_client import Client, LocalClient
from star_pass_contract import EventView

# Constants
# The opportunity every fixture's events send to, and so the row a
# preview's tables are found by.
NEED_ID = '905196'

# What a run calls the job a stopped service left behind, which is
# the line a resume's identifier is read off, and what it calls the
# count of what its window held and it left out.
INTERRUPTED_LABEL = 'Interrupted job'
UNCOLLECTED_LABEL = 'Not collected'

# A value for each flag a command takes, so a test about whether a
# command is reachable can supply what it insists on without also
# describing it.
EXAMPLE_VALUES = {
    'calendar': 'events',
    'start': '2026-09-01',
    'last_day': '2026-09-30',
    'expected_changes': '0'
}


@pytest.fixture(name='previewed')
def fixture_previewed(
    capsys: pytest.CaptureFixture,
    cli: Callable[..., int]
) -> Callable[[str], Tuple[str, list]]:
    """ Return a way to preview a run and read the rows about an
        opportunity.

        The rows are the displayed lines split into their columns, in
        the order the preview shows them: the opportunity's own row
        first, then any shift Amplify already has.
    """

    def read(run_id: str) -> Tuple[str, list]:
        """ Preview the run and return the output and those rows. """
        cli('runs', 'preview', run_id)
        shown = capsys.readouterr().out

        return shown, [
            line.split()
            for line in shown.splitlines()
            if line.startswith(NEED_ID)
        ]

    return read


@pytest.fixture(name='holding_nothing')
def fixture_holding_nothing(
    amplify_holds: Callable[..., None]
) -> None:
    """ Answer every opportunity read with an opportunity holding none.

        A preview reads them live, so a test about how a preview is
        displayed still has to say what Amplify holds.
    """
    amplify_holds()

    return None


class TestChoosingAMode:
    def test_no_address_reads_the_local_database(
        self,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Local by default, so the command line client never needs a
        # server to be running.
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


def labelled_value(
        shown: str,
        label: str
) -> str:
    """ Return what one labelled line says.

        The line rather than the whole output, because a run
        identifier and a job identifier are both random and a test
        looking for one anywhere would pass on the wrong line as
        readily as the right one.  Split on whitespace rather than
        matched with the padding written in, because the names are
        aligned on the longest of them -- a test carrying the padding
        fails when a longer name is added beside it, which says
        nothing about what it was checking.
    """
    for row in shown.splitlines():
        if row.startswith(label):
            return row.split()[-1]

    raise AssertionError(f'No "{label}" line was shown')


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

    def test_a_run_shows_the_job_a_stopped_service_left_behind(
        self,
        capsys: pytest.CaptureFixture,
        cli: Callable[..., int],
        jobs: JobRepository,
        job_principal: str,
        populated: str
    ) -> None:
        # This is where the identifier 'jobs resume' takes is read.
        # Resuming is a deliberate act, so nothing hands it over
        # unasked, and an interrupted job is never the active one.
        job = jobs.create(
            run_id=populated,
            kind=JOB_KIND_SEND,
            principal_id=job_principal
        )
        jobs.interrupt_unfinished()

        cli('runs', 'show', populated)

        assert labelled_value(
            capsys.readouterr().out,
            label=INTERRUPTED_LABEL
        ) == job.id

    def test_a_run_with_nothing_left_behind_shows_no_such_job(
        self,
        capsys: pytest.CaptureFixture,
        cli: Callable[..., int],
        populated: str
    ) -> None:
        cli('runs', 'show', populated)

        assert labelled_value(
            capsys.readouterr().out,
            label=INTERRUPTED_LABEL
        ) == _render.NOTHING

    def test_an_unknown_run_says_so_and_fails(
        self,
        capsys: pytest.CaptureFixture,
        cli: Callable[..., int]
    ) -> None:
        status = cli('runs', 'show', 'no-such-run')

        assert status == 1
        assert 'no-such-run' in capsys.readouterr().out


class TestPreviewingARun:
    def test_a_preview_shows_what_each_opportunity_receives(
        self,
        capsys: pytest.CaptureFixture,
        cli: Callable[..., int],
        holding_nothing: None,
        populated: str
    ) -> None:
        del holding_nothing

        status = cli('runs', 'preview', populated)
        shown = capsys.readouterr().out

        assert status == 0
        assert 'Would create' in shown
        assert 'Adult Scrimmages: Skating Officials' in shown

    def test_a_blocked_event_is_named_with_its_reason(
        self,
        capsys: pytest.CaptureFixture,
        cli: Callable[..., int],
        holding_nothing: None,
        populated: str
    ) -> None:
        # The identifier the contract publishes is written for a
        # program to branch on; a person is told what it means.
        del holding_nothing

        cli('runs', 'preview', populated)
        shown = capsys.readouterr().out

        assert 'event-3' in shown
        assert _sending.BLOCKER_PHRASES[BLOCKER_NO_OPPORTUNITY] in shown

    def test_a_blocked_run_says_nothing_can_be_sent(
        self,
        capsys: pytest.CaptureFixture,
        cli: Callable[..., int],
        holding_nothing: None,
        populated: str
    ) -> None:
        # A reader skimming the totals should not think the blocked
        # events below cost them only those shifts.
        del holding_nothing

        cli('runs', 'preview', populated)

        assert _sending.NOTHING_SENDABLE in capsys.readouterr().out

    def test_a_shift_amplify_already_has_is_shown_as_skipped(
        self,
        previewed: Callable[[str], Tuple[str, list]],
        amplify_holds: Callable[..., None],
        make_amplify_shift: Callable[..., dict],
        populated: str
    ) -> None:
        # Named per shift rather than only counted, so a reader can
        # check that the right rows are being left out.
        amplify_holds({NEED_ID: [make_amplify_shift()]})

        shown, (opportunity, skipped) = previewed(populated)

        assert 'Already in Amplify' in shown
        # The last five columns are what would be created, what is
        # already there, the volunteers wanted, and the days.
        assert opportunity[-5:] == [
            '1',
            '1',
            '4',
            '2026-09-03',
            '2026-09-03'
        ]
        assert skipped == [NEED_ID, '2026-09-03', '19:15', '21:30']

    def test_a_row_names_the_first_and_last_day_in_that_order(
        self,
        previewed: Callable[[str], Tuple[str, list]],
        holding_nothing: None,
        collected: str,
        add_second_event: Callable[..., None]
    ) -> None:
        del holding_nothing

        add_second_event(date='2026-09-10')
        _shown, (row,) = previewed(collected)

        assert row[-2:] == ['2026-09-03', '2026-09-10']

    def test_a_row_creating_nothing_shows_no_days(
        self,
        previewed: Callable[[str], Tuple[str, list]],
        amplify_holds: Callable[..., None],
        make_amplify_shift: Callable[..., dict],
        collected: str
    ) -> None:
        # The dates are the days about to arrive in Amplify, and none
        # are; a blank column would read as a rendering fault.
        amplify_holds({NEED_ID: [make_amplify_shift()]})

        _shown, (row, _skipped) = previewed(collected)

        assert row[-2:] == [_render.NOTHING, _render.NOTHING]


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
        # the server stores, and the last day beside it because every
        # client showing a window means that one.  What is pinned here
        # is that the published day is what reaches a reader; that it
        # is the right day is pinned where it is worked out.
        assert _render.window_text(
            window={
                'start': '2026-09-01',
                'end': '2026-10-01',
                'lastDay': '2026-09-30'
            }
        ) == '2026-09-01 to 2026-09-30'

    def test_the_exclusive_end_is_never_what_is_shown(self) -> None:
        # The failure this catches is a client falling back to 'end'
        # when 'lastDay' is what it means, which reads as a run
        # covering a day it does not.
        assert _render.window_text(
            window={
                'start': '2026-09-01',
                'end': '2026-09-02',
                'lastDay': '2026-09-01'
            }
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

    def test_a_role_shows_the_volunteers_it_wants_and_its_timing(
        self,
        make_event_document: Callable[..., Any]
    ) -> None:
        # The timing is the role's, so it is shown with the role: two
        # events in one run can send to one listing on different
        # offsets, and there is nowhere else to see that.
        assert _render.roles_text(
            event=make_event_document()
        ) == '905196 (4) +15/+30'


class TestWhatAnEventShowsAboutItsTiming:
    def test_the_offsets_are_signed(
        self,
        make_event_document: Callable[..., Any]
    ) -> None:
        # A bare number leaves a reader guessing which way the shift
        # moved from the event.
        event = make_event_document()
        event['roles'][0]['offsetEnd'] = -30

        assert _render.roles_text(event=event).endswith('+15/-30')

    def test_two_roles_show_their_own_timings(
        self,
        make_event_document: Callable[..., Any]
    ) -> None:
        # One Amplify listing named by two categories, which is what a
        # reader sees here.
        event = make_event_document()
        first = event['roles'][0]
        event['roles'] = [
            first,
            {**first, 'offsetStart': -15, 'offsetEnd': 15}
        ]

        assert _render.roles_text(event=event) == (
            '905196 (4) +15/+30, 905196 (4) -15/+15'
        )


class TestWhatAnOpportunityShows:
    def test_an_opportunity_shows_what_amplify_says_and_no_timing(
        self
    ) -> None:
        # How a shift is timed under a listing is the role's, so an
        # opportunity that named offsets would be claiming one set for
        # a listing that can be timed several ways.
        assert _render.OPPORTUNITY_HEADERS == ('NEED', 'TITLE')
        assert _render.opportunity_row(
            opportunity={
                'needId': '905196',
                'title': 'Adult Scrimmages'
            }
        ) == ['905196', 'Adult Scrimmages']


class TestShowingWhatARunLeftOut:
    @pytest.fixture(name='listed')
    def fixture_listed(
        self,
        capsys: pytest.CaptureFixture,
        cli: Callable[..., int],
        not_collected: Callable[[str], list],
        populated: str
    ) -> str:
        """ Return what the command shows for a run that left things out.

            One arrangement, because every question below is a
            different reading of the same displayed answer.
        """
        not_collected(populated)

        assert cli('runs', 'uncollected', populated) == 0

        return capsys.readouterr().out

    @pytest.fixture(name='rows')
    def fixture_rows(
        self,
        listed: str
    ) -> List[List[str]]:
        """ Return the displayed event rows, split into their columns. """
        return [
            line.split()
            for line in listed.splitlines()
            if line.startswith('gcal-')
        ]

    def test_the_groups_are_headed_by_what_the_reason_means(
        self,
        listed: str
    ) -> None:
        assert _render.UNCOLLECTED_PHRASES[UNCOLLECTED_SEARCH] in listed
        assert _render.UNCOLLECTED_PHRASES[UNCOLLECTED_EXCLUDED] in listed

    def test_an_event_shows_what_the_calendar_said_about_it(
        self,
        listed: str
    ) -> None:
        assert 'Junior Bout' in listed
        assert '2026-09-11' in listed
        assert '18:00-20:00' in listed

    def test_an_all_day_event_shows_no_times_rather_than_empty_ones(
        self,
        rows: List[List[str]]
    ) -> None:
        when = _render.UNCOLLECTED_HEADERS.index('WHEN')

        assert [row[when] for row in rows] == [
            '18:00-20:00',
            '19:00-21:00',
            _render.NOTHING,
            '08:00-09:00'
        ]

    def test_only_an_event_that_may_be_pulled_in_is_marked(
        self,
        rows: List[List[str]]
    ) -> None:
        assert [row[-1] for row in rows] == [
            _render.ADDABLE,
            _render.NOTHING,
            _render.NOTHING,
            _render.NOTHING
        ]

    def test_a_run_that_left_nothing_out_says_so(
        self,
        capsys: pytest.CaptureFixture,
        cli: Callable[..., int],
        populated: str
    ) -> None:
        # A heading over a table of nothing but column names reads as
        # an answer that failed rather than as one that is empty.
        status = cli('runs', 'uncollected', populated)

        assert status == 0
        assert 'was collected' in capsys.readouterr().out

    def test_every_reason_the_core_publishes_is_worded(self) -> None:
        # A reason with no wording heads its group as its identifier,
        # which is written for a program to branch on.
        assert set(_render.UNCOLLECTED_PHRASES) == set(UNCOLLECTED_REASONS)

    def test_a_run_showing_one_counts_what_it_left_out(
        self,
        capsys: pytest.CaptureFixture,
        cli: Callable[..., int],
        not_collected: Callable[[str], list],
        populated: str
    ) -> None:
        left_out = not_collected(populated)

        cli('runs', 'show', populated)

        assert labelled_value(
            capsys.readouterr().out,
            label=UNCOLLECTED_LABEL
        ) == str(len(left_out))


class TestWhyAnEventCannotBeSent:
    def test_every_reason_the_core_publishes_is_worded(self) -> None:
        # A reason with no wording shows as its identifier, which is
        # written for a program to branch on rather than to be read.
        assert set(_sending.BLOCKER_PHRASES) == set(BLOCKER_REASONS)

    def test_a_reason_with_no_wording_shows_as_itself(self) -> None:
        row = _sending.blocker_row(
            blocker={'eventId': 'event-1', 'reason': 'invented_later'}
        )

        assert row[_sending.BLOCKER_HEADERS.index('REASON')] == (
            'invented_later'
        )


def words_for(command: Any) -> List[str]:
    """ Return the shortest command line that selects one command.

        Every value it insists on, and nothing else: a test about
        whether a command is reachable should not also be a test of
        what each of them takes.
    """
    words = [command.group, command.word]

    if command.argument is not None:
        words.append('a-value')

    for option in command.options:
        words += [option.flag, EXAMPLE_VALUES[option.name]]

    return words


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
            args = build_parser().parse_args(words_for(command=command))

            assert selected(args=args) == (command.group, command.word)

    def test_every_command_takes_the_address_of_a_service(
        self,
        build_parser: Callable[[], Any]
    ) -> None:
        # Held on a parent parser, so a command added later cannot be
        # the one that forgets to offer the remote mode.
        for command in COMMANDS:
            args = build_parser().parse_args(
                words_for(command=command)
                + ['--api-url', 'https://star-pass.test']
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
                words_for(command=command)
            )

            assert getattr(args, command.argument) == 'a-value'


class TestSelectingACommand:
    def test_a_mode_flag_selects_no_command(
        self,
        build_parser: Callable[[], Any]
    ) -> None:
        # The Slack summary is the one run mode left, and it is the one
        # the API deliberately does not publish, so a command must not
        # be read out of its arguments.
        args = build_parser().parse_args(['-s', '-N', '5'])

        assert selected(args=args) is None

    def test_a_command_word_selects_a_command(
        self,
        build_parser: Callable[[], Any]
    ) -> None:
        args = build_parser().parse_args(['runs', 'list'])

        assert selected(args=args) == ('runs', 'list')


class TestWhatEveryCommandDeclares:
    def test_every_flag_a_command_takes_has_an_example_value(
        self
    ) -> None:
        # The list above is what lets a test supply what a command
        # insists on; a flag added without one would leave the tests
        # of reachability silently describing fewer commands.
        assert {
            option.name
            for command in COMMANDS
            for option in command.options
        } <= set(EXAMPLE_VALUES)

    def test_a_command_that_is_sent_something_says_what(self) -> None:
        # A body with no flags to build it from, or flags with nothing
        # to build, would be a command that could not be carried out.
        for command in COMMANDS:
            assert bool(command.options) == bool(command.body)
