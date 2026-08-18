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
from typing import Any, Callable, Dict, List, Tuple

# Imports - Third-Party
import pytest

# Imports - Local
from star_pass._records import (
    JOB_HOLDER_LOCAL,
    JOB_KIND_COLLECT,
    JOB_STATUS_INTERRUPTED
)
from star_pass._reporting import (
    STEP_READ_CALENDAR,
    STEP_READ_OPPORTUNITIES,
    STEP_READ_OPPORTUNITY,
    STEP_STORE_EVENTS,
    STEPS
)
from star_pass._repository import JobRepository, RunRepository
from star_pass_cli import _sending
from star_pass_cli._commands import run_command
from star_pass_client._stream import StreamEvent

# Constants
# The opportunity every fixture's events send to.
NEED_ID = '905196'


@pytest.fixture(name='collecting_locally')
def fixture_collecting_locally(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """ Replace the collecting a local command carries out.

        What a collection does is pinned in 'test_collect.py'.  These
        tests ask whether the command reaches it with what the operator
        typed, and shows the job it ended as.
    """

    def nothing(
        connection: Any,
        run_id: str,
        reporter: Any,
        principal_id: str
    ) -> None:
        """ Stand in for the collection. """
        del connection, run_id, reporter, principal_id

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
                payload={'step': STEP_READ_CALENDAR, 'subject': ''}
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
            f'Started: {_sending.step_text(step=STEP_READ_CALENDAR)}',
            'The job is over: succeeded'
        ]


class TestHowAJobsReportsAreShown:
    def test_a_report_is_worded_for_a_reader(self) -> None:
        # The kinds are named by the reporting methods that produced
        # them, which is right for a program and wrong for a person.
        line = _sending.event_line(
            answer=StreamEvent(
                kind='step_started',
                payload={
                    'step': STEP_READ_OPPORTUNITIES,
                    'subject': ''
                }
            )
        )

        assert line == (
            'Started: Reading the Amplify opportunities'
        )

    def test_a_step_is_worded_with_what_it_is_working_on(self) -> None:
        # The send reads each opportunity before writing to it, and
        # the stream names which one as a value beside the step rather
        # than as words inside it.
        line = _sending.event_line(
            answer=StreamEvent(
                kind='step_started',
                payload={
                    'step': STEP_READ_OPPORTUNITY,
                    'subject': '905196'
                }
            )
        )

        assert line == (
            'Started: Reading what opportunity 905196 already holds'
        )

    def test_a_finished_opportunity_names_itself(self) -> None:
        # Reported for every opportunity, including one Amplify
        # already held every shift for.
        line = _sending.event_line(
            answer=StreamEvent(
                kind='opportunity_sent',
                payload={
                    'needId': '905196',
                    'title': 'Adult Scrimmages: Skating Officials',
                    'shifts': [],
                    'skipped': 2
                }
            )
        )

        assert line == (
            'Sent to: Adult Scrimmages: Skating Officials'
        )

    def test_a_report_with_no_wording_names_itself(self) -> None:
        # A kind added to the core and not to the list should say what
        # it is rather than vanish.
        line = _sending.event_line(
            answer=StreamEvent(kind='something_new', payload={})
        )

        assert line == 'something_new'


class TestWhatEachStepIsCalled:
    def test_every_step_the_core_publishes_is_worded(self) -> None:
        # A step with no wording shows as its identifier, which is
        # written for a program to branch on rather than to be read.
        assert set(_sending.STEP_PHRASES) == set(STEPS)

    def test_no_wording_is_for_a_step_that_does_not_exist(self) -> None:
        # The direction that catches a step being renamed rather than
        # added: the wording would survive, and nothing would say it
        # is now unreachable.
        for step in _sending.STEP_PHRASES:
            assert step in STEPS

    def test_a_step_with_no_wording_shows_as_itself(self) -> None:
        assert _sending.step_text(step='invented_later') == (
            'invented_later'
        )

    def test_a_step_says_what_it_is_working_on(self) -> None:
        # The send reads each opportunity before it writes to it, and
        # a screen drawing a row per opportunity has to know which one
        # a read is about.
        assert '106280' in _sending.step_text(
            step=STEP_READ_OPPORTUNITY,
            subject='106280'
        )

    def test_a_step_that_asks_for_nothing_is_left_alone(self) -> None:
        # A subject nothing asked for is not appended anywhere.
        assert _sending.step_text(
            step=STEP_STORE_EVENTS,
            subject='106280'
        ) == _sending.STEP_PHRASES[STEP_STORE_EVENTS]


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


@pytest.fixture(name='sending_locally')
def fixture_sending_locally(
    monkeypatch: pytest.MonkeyPatch,
    amplify_holds: Callable[..., list]
) -> None:
    """ Replace the sending a local command carries out.

        What a send does is pinned in 'test_send.py'.  These tests ask
        what the command puts to the operator before it, and what it
        does with each answer.  The opportunity read the endpoint makes
        before deciding is still answered, because that read is what
        the confirmed count comes from.
    """
    amplify_holds()

    def nothing(**parameters: Any) -> None:
        """ Stand in for the send. """
        del parameters

    monkeypatch.setattr('star_pass_client._local_writes.send', nothing)

    return None


@pytest.fixture(name='asking_to_send')
def fixture_asking_to_send(
    capsys: pytest.CaptureFixture,
    cli: Callable[..., int],
    sending_locally: None,
    collected: str
) -> Callable[[], Tuple[int, str]]:
    """ Return a way to ask for a send of the collected run.

        One fixture rather than four on every test: the arrangement is
        a single thing -- a run that could be sent, and a send that
        does not reach Amplify -- and what each test varies is only the
        answer given to the question.
    """
    del sending_locally

    def ask() -> Tuple[int, str]:
        """ Ask, and return how it went and what was written. """
        return cli('runs', 'send', collected), capsys.readouterr().out

    return ask


@pytest.fixture(name='asked_to_send')
def fixture_asked_to_send(
    monkeypatch: pytest.MonkeyPatch,
    window_document: dict
) -> List[Dict[str, Any]]:
    """ Answer a send without a service, keeping what it was asked.

        A client rather than a database, because what these tests ask
        is what the command puts to the operator and what it passes on
        afterwards -- not what the send then does, which is pinned in
        'test_send.py'.
    """
    asked: List[Dict[str, Any]] = []

    class Sending:
        """ A client with one run, three shifts to create, and a memory. """

        @staticmethod
        def get_run(run_id: str) -> Dict[str, Any]:
            """ Return the run being sent. """
            return {
                'id': run_id,
                'calendar': 'events',
                'window': dict(window_document)
            }

        @staticmethod
        def get_preview(run_id: str) -> Dict[str, Any]:
            """ Return what sending it would create. """
            del run_id

            return {
                'totals': {
                    'willCreate': 3,
                    'alreadyInAmplify': 1,
                    'repeatedRows': 0,
                    'blockingEvents': 0
                },
                'rows': [],
                'skipped': [],
                'blockers': []
            }

        @staticmethod
        def send_run(**parameters: Any) -> Dict[str, Any]:
            """ Record what the send was asked for. """
            asked.append(parameters)

            return {
                'id': 'a-job',
                'runId': parameters['run_id'],
                'kind': 'send',
                'status': 'queued',
                'createdAt': '2026-09-01T00:00:00+00:00',
                'startedAt': None,
                'finishedAt': None,
                'detail': None
            }

    monkeypatch.setattr(
        'star_pass_cli._commands.client_for',
        lambda api_url: Sending()
    )

    return asked


@pytest.fixture(name='answering')
def fixture_answering(
    monkeypatch: pytest.MonkeyPatch
) -> Callable[[str], None]:
    """ Return a way to sit a person at a terminal with an answer. """

    def sits(answer: str) -> None:
        """ Answer the next question with that. """
        monkeypatch.setattr(
            'star_pass_cli._confirm.sys.stdin.isatty',
            lambda: True
        )
        monkeypatch.setattr('builtins.input', lambda: answer)

    return sits


class TestConfirmingASend:
    def test_what_is_about_to_happen_is_restated(
        self,
        asking_to_send: Callable[[], Tuple[int, str]],
        answering: Callable[[str], None]
    ) -> None:
        # The confirmation's job is to make somebody read the summary
        # (D11), so it says the count, the window and the
        # opportunities before it asks.
        answering('n')

        _status, shown = asking_to_send()

        assert 'Would create' in shown
        assert '2026-09-01' in shown
        assert NEED_ID in shown

    def test_an_answer_of_yes_sends(
        self,
        asking_to_send: Callable[[], Tuple[int, str]],
        answering: Callable[[str], None]
    ) -> None:
        answering('y')

        status, shown = asking_to_send()

        assert status == 0
        assert 'send' in shown
        assert 'succeeded' in shown

    def test_an_answer_of_no_sends_nothing(
        self,
        asking_to_send: Callable[[], Tuple[int, str]],
        answering: Callable[[str], None],
        jobs: JobRepository,
        collected: str
    ) -> None:
        answering('n')

        status, shown = asking_to_send()

        assert status == 0
        assert 'Nothing was sent' in shown
        assert jobs.list_for_run(run_id=collected) == []

    def test_pressing_return_sends_nothing(
        self,
        asking_to_send: Callable[[], Tuple[int, str]],
        answering: Callable[[str], None],
        jobs: JobRepository,
        collected: str
    ) -> None:
        # The safe answer is the one somebody gets without reading.
        answering('')

        _status, shown = asking_to_send()

        assert 'Nothing was sent' in shown
        assert jobs.list_for_run(run_id=collected) == []

    def test_no_terminal_is_not_a_yes(
        self,
        asking_to_send: Callable[[], Tuple[int, str]],
        jobs: JobRepository,
        collected: str
    ) -> None:
        # A gate with a way around it is a gate somebody eventually
        # goes around, and what is behind this one cannot be undone.
        status, shown = asking_to_send()

        assert status == 1
        assert 'no terminal' in shown
        assert jobs.list_for_run(run_id=collected) == []

    def test_a_run_with_nothing_left_to_send_is_not_asked_about(
        self,
        asking_to_send: Callable[[], Tuple[int, str]],
        amplify_holds: Callable[..., list],
        make_amplify_shift: Callable[..., dict]
    ) -> None:
        # There is nothing to confirm, and asking whether to do
        # something irreversible that is not going to happen reads as
        # a warning about nothing.
        amplify_holds({NEED_ID: [make_amplify_shift()]})

        status, shown = asking_to_send()

        assert status == 0
        assert 'already has every shift' in shown

    def test_the_count_restated_is_the_count_that_would_arrive(
        self,
        capsys: pytest.CaptureFixture,
        build_parser: Callable[[], Any],
        asked_to_send: List[Dict[str, Any]],
        answering: Callable[[str], None]
    ) -> None:
        # The number somebody reads is the number of rows that will
        # arrive, net of what Amplify already holds; a restatement
        # saying anything else is a warning about the wrong thing.
        del asked_to_send
        answering('n')

        run_command(
            args=build_parser().parse_args(['runs', 'send', 'a-run'])
        )
        said = [
            line.split()[-1]
            for line in capsys.readouterr().out.splitlines()
            if line.startswith(('Would create', 'Already in Amplify'))
        ]

        assert said == ['3', '1']

    def test_the_count_confirmed_is_the_count_sent(
        self,
        build_parser: Callable[[], Any],
        asked_to_send: List[Dict[str, Any]],
        answering: Callable[[str], None]
    ) -> None:
        # The service checks it again against its own reading, which
        # is what catches a run that moved between the question and
        # the answer.
        answering('y')

        run_command(
            args=build_parser().parse_args(['runs', 'send', 'a-run'])
        )

        assert asked_to_send[0]['body'] == {'expectedShiftCount': 3}

    def test_each_attempt_is_claimed_under_a_key_of_its_own(
        self,
        build_parser: Callable[[], Any],
        asked_to_send: List[Dict[str, Any]],
        answering: Callable[[str], None]
    ) -> None:
        # The key stops one request being carried out twice; what
        # stops a row being created twice is the live read the send
        # makes, which holds however many attempts there are.
        answering('y')
        words = ['runs', 'send', 'a-run']

        run_command(args=build_parser().parse_args(words))
        run_command(args=build_parser().parse_args(words))

        keys = [asked['idempotency_key'] for asked in asked_to_send]

        assert all(keys)
        assert len(set(keys)) == 2
