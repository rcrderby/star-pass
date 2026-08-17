#!/usr/bin/env python3
""" The commands that change something, from the command line.

    A module of its own beside the reading commands, because the two
    are two things: one asks what is stored and one collects a
    calendar, replaces what a run holds, or runs an interrupted job
    again.

    The work itself is replaced throughout.  What collecting and
    resuming do is pinned where each is tested; these ask whether the
    command reaches them with what the operator typed, and shows what
    came back.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
from typing import Any, Callable

# Imports - Third-Party
import pytest

# Imports - Local
from star_pass._records import (
    JOB_HOLDER_LOCAL,
    JOB_KIND_COLLECT,
    JOB_STATUS_INTERRUPTED
)
from star_pass._repository import JobRepository, RunRepository
from star_pass_cli import _render
from star_pass_cli._commands import run_command
from star_pass_client._stream import StreamEvent


@pytest.fixture(name='collecting_locally')
def fixture_collecting_locally(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """ Replace the collecting a local command carries out.

        What a collection does is pinned in 'test_collect.py'.  These
        tests ask whether the command reaches it with what the operator
        typed, and shows the job it ended as.
    """

    def nothing(connection: Any, run_id: str, reporter: Any) -> None:
        """ Stand in for the collection. """
        del connection, run_id, reporter

    monkeypatch.setattr('star_pass_client._local_writes.collect', nothing)

    return None


@pytest.fixture(name='resuming_locally')
def fixture_resuming_locally(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """ Replace the work a locally resumed job runs. """

    def nothing(job: Any, principal_id: str) -> Callable[..., None]:
        """ Stand in for the work. """
        del job, principal_id

        return lambda _connection, _reporter: None

    monkeypatch.setattr(
        'star_pass_client._local_writes.work_for',
        nothing
    )

    return None


@pytest.fixture(name='interrupted_locally')
def fixture_interrupted_locally(
    jobs: JobRepository,
    collected: str
) -> str:
    """ Return a job an earlier command left interrupted. """
    job = jobs.create(
        run_id=collected,
        kind=JOB_KIND_COLLECT,
        principal_id='local-cli',
        held_by=JOB_HOLDER_LOCAL
    )
    jobs.start(job_id=job.id)
    jobs.finish(job_id=job.id, status=JOB_STATUS_INTERRUPTED)

    return job.id


@pytest.fixture(name='watching')
def fixture_watching(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """ Answer a watch with two reports, without a service.

        The stream itself is pinned in 'test_stream_events.py'.  What
        this arranges is a client that hands the dispatcher events, so
        the question is what the dispatcher does with each of them.
    """

    class Watched:
        """ A client that reports twice and stops. """

        @staticmethod
        def stream_job_events(job_id: str) -> Any:
            """ Yield what a job reported. """
            del job_id

            yield StreamEvent(
                kind='step_started',
                payload={'label': 'Reading the calendar'}
            )
            yield StreamEvent(
                kind='job_finished',
                payload={'status': 'succeeded'}
            )

    monkeypatch.setattr(
        'star_pass_cli._commands.client_for',
        lambda api_url: Watched()
    )

    return None


class TestCollectingFromTheCommandLine:
    def test_a_collection_answers_with_the_job_that_did_it(
        self,
        capsys: pytest.CaptureFixture,
        cli: Callable[..., int],
        collecting_locally: None
    ) -> None:
        del collecting_locally

        status = cli(
            'runs', 'collect',
            '--calendar', 'events',
            '--start', '2026-09-01',
            '--last-day', '2026-09-30'
        )
        shown = capsys.readouterr().out

        assert status == 0
        assert 'collect' in shown
        assert 'succeeded' in shown

    @pytest.mark.parametrize('calendar', ('events', 'practices'))
    def test_the_run_collects_the_calendar_it_was_given(
        self,
        cli: Callable[..., int],
        collecting_locally: None,
        runs: RunRepository,
        calendar: str
    ) -> None:
        # Both of them, so that a command line reaching a fixed
        # calendar rather than the one it was given fails on one of
        # the two whichever it was fixed to.
        del collecting_locally

        cli(
            'runs', 'collect',
            '--calendar', calendar,
            '--start', '2026-09-01',
            '--last-day', '2026-09-30'
        )

        assert runs.list_all()[0].calendar == calendar

    def test_a_flag_the_command_needs_is_not_optional(
        self,
        build_parser: Callable[[], Any]
    ) -> None:
        # A write takes what it takes; a flag defaulted here would be
        # the command line deciding what to collect.
        with pytest.raises(SystemExit):
            build_parser().parse_args(
                [
                    'runs', 'collect',
                    '--calendar', 'events',
                    '--start', '2026-09-01'
                ]
            )

    def test_the_window_covers_the_last_day_it_was_given(
        self,
        cli: Callable[..., int],
        collecting_locally: None,
        runs: RunRepository
    ) -> None:
        # The window crosses the wire with an exclusive end and is
        # spoken about by the last day it covers, so a command line
        # asking for the thirtieth means the thirtieth.
        del collecting_locally

        cli(
            'runs', 'collect',
            '--calendar', 'events',
            '--start', '2026-09-01',
            '--last-day', '2026-09-30'
        )
        collected_run = runs.list_all()[0]

        assert collected_run.window_start == '2026-09-01'
        assert collected_run.window_end == '2026-10-01'

    def test_a_date_that_is_not_one_is_reported_and_fails(
        self,
        capsys: pytest.CaptureFixture,
        cli: Callable[..., int],
        collecting_locally: None
    ) -> None:
        del collecting_locally

        status = cli(
            'runs', 'collect',
            '--calendar', 'events',
            '--start', '2026-09-01',
            '--last-day', 'the end of September'
        )

        assert status == 1
        assert 'September' in capsys.readouterr().out


class TestCollectingARunAgain:
    def test_a_recollection_answers_with_the_job_that_did_it(
        self,
        capsys: pytest.CaptureFixture,
        cli: Callable[..., int],
        collecting_locally: None,
        collected: str
    ) -> None:
        del collecting_locally

        status = cli(
            'runs', 'recollect', collected,
            '--expected-changes', '0'
        )

        assert status == 0
        assert 'recollect' in capsys.readouterr().out

    def test_a_change_count_that_has_moved_is_reported_and_fails(
        self,
        capsys: pytest.CaptureFixture,
        cli: Callable[..., int],
        collecting_locally: None,
        collected: str
    ) -> None:
        # The refusal is the service's own words, which is what makes
        # one mode readable to somebody who learned the other (D2).
        del collecting_locally

        status = cli(
            'runs', 'recollect', collected,
            '--expected-changes', '4'
        )

        assert status == 1
        assert '4' in capsys.readouterr().out


class TestReadingWhatAFlagCarries:
    def test_a_count_arrives_as_a_number(
        self,
        build_parser: Callable[[], Any]
    ) -> None:
        # The contract takes a number; a flag left as text would be
        # refused by the service rather than by the person typing it.
        with pytest.raises(SystemExit):
            build_parser().parse_args(
                ['runs', 'recollect', 'a-run', '--expected-changes', 'lots']
            )

    def test_a_count_that_is_a_number_is_read_as_one(
        self,
        build_parser: Callable[[], Any]
    ) -> None:
        args = build_parser().parse_args(
            ['runs', 'recollect', 'a-run', '--expected-changes', '3']
        )

        assert args.expected_changes == 3


class TestFollowingAJob:
    def test_each_report_is_written_as_it_arrives(
        self,
        capsys: pytest.CaptureFixture,
        build_parser: Callable[[], Any],
        watching: None
    ) -> None:
        # Gathered and written at the end, a watch would tell somebody
        # what happened rather than what is happening.
        del watching

        status = run_command(
            args=build_parser().parse_args(['jobs', 'watch', 'a-job'])
        )
        shown = capsys.readouterr().out

        assert status == 0
        assert shown.splitlines() == [
            'Started: Reading the calendar',
            'The job is over: succeeded'
        ]


class TestHowAJobsReportsAreShown:
    def test_a_report_is_worded_for_a_reader(self) -> None:
        # The kinds are named by the reporting methods that produced
        # them, which is right for a program and wrong for a person.
        line = _render.event_line(
            answer=StreamEvent(
                kind='step_started',
                payload={'label': 'Reading the Amplify opportunities'}
            )
        )

        assert line == (
            'Started: Reading the Amplify opportunities'
        )

    def test_a_report_with_no_wording_names_itself(self) -> None:
        # A kind added to the core and not to the list should say what
        # it is rather than vanish.
        line = _render.event_line(
            answer=StreamEvent(kind='something_new', payload={})
        )

        assert line == 'something_new'


class TestWatchingAndResumingAJob:
    def test_watching_says_why_it_has_no_local_answer(
        self,
        capsys: pytest.CaptureFixture,
        cli: Callable[..., int],
        job_id: str
    ) -> None:
        # Nothing is serving in local mode, so there is no stream to
        # hold open; the command says so rather than answering with
        # nothing.
        status = cli('jobs', 'watch', job_id)

        assert status == 1
        assert 'local mode' in capsys.readouterr().out

    def test_an_interrupted_job_is_resumed(
        self,
        capsys: pytest.CaptureFixture,
        cli: Callable[..., int],
        resuming_locally: None,
        interrupted_locally: str
    ) -> None:
        del resuming_locally

        status = cli('jobs', 'resume', interrupted_locally)
        shown = capsys.readouterr().out

        assert status == 0
        assert interrupted_locally in shown
        assert 'succeeded' in shown

    def test_a_job_that_ended_is_reported_and_fails(
        self,
        capsys: pytest.CaptureFixture,
        cli: Callable[..., int],
        resuming_locally: None,
        job_id: str
    ) -> None:
        del resuming_locally

        status = cli('jobs', 'resume', job_id)

        assert status == 1
        assert 'resumed' in capsys.readouterr().out
