#!/usr/bin/env python3
""" The two modes write the same way.

    A write is where the two modes could differ and nobody would
    notice: one could refuse what the other carried out, or record a
    different principal, or leave a run in a different state.  So every
    one is asked of both, and what each refuses is compared word for
    word.

    The work itself is replaced throughout.  What collecting, sending
    and resuming do is pinned where each is tested; these ask whether
    the two halves decide the same things about them.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
import sqlite3
from typing import Any, Callable, Tuple

# Imports - Third-Party
import pytest

# Imports - Local
from star_pass._exceptions import ValidationError as CoreValidationError
from star_pass._records import (
    JOB_HOLDER_LOCAL,
    JOB_HOLDER_SERVICE,
    JOB_KIND_COLLECT,
    JOB_KIND_SEND,
    JOB_STATUS_INTERRUPTED,
    JOB_STATUS_RUNNING,
    JOB_STATUS_SUCCEEDED,
    RUN_STATUS_SENT,
    RUN_STATUS_UNSENT
)
from star_pass._repository import JobRepository, RunRepository
from star_pass_api._defaults import API_PRINCIPAL_ID
from star_pass_client import ApiProblem, Client, LocalClient
from two_modes._asked import (
    A_COLLECTION,
    NO_CHANGES,
    NOTHING_TO_SEND
)


class TestTheTwoModesCollectTheSame:
    def test_a_collection_answers_with_the_same_kind_of_job(
        self,
        both: Callable[..., Tuple[Any, Any]],
        collecting_service: None
    ) -> None:
        del collecting_service
        local, remote = both('collect_run', body=A_COLLECTION)

        assert local['kind'] == remote['kind'] == 'collect'
        assert local['runId'] != remote['runId']

    def test_each_collection_produces_a_run_of_its_own(
        self,
        both: Callable[..., Tuple[Any, Any]],
        collecting_service: None,
        local_client: LocalClient
    ) -> None:
        del collecting_service
        both('collect_run', body=A_COLLECTION)

        assert len(local_client.list_runs()) == 2

    def test_a_local_collection_records_who_asked(
        self,
        local_client: LocalClient,
        collecting_service: None,
        connection: sqlite3.Connection
    ) -> None:
        # The column exists so that two writers can be told apart
        # (D13), and a local run is not the service acting.
        del collecting_service
        answered = local_client.collect_run(body=A_COLLECTION)

        recorded = JobRepository(connection=connection).get(
            job_id=answered['id']
        ).principal_id

        assert recorded == 'local-cli'
        assert recorded != API_PRINCIPAL_ID

    def test_a_local_collection_is_over_when_it_answers(
        self,
        local_client: LocalClient,
        collecting_service: None
    ) -> None:
        # The process that would run the job is the one about to
        # return, so the work happens in the call.
        del collecting_service
        answered = local_client.collect_run(body=A_COLLECTION)

        assert answered['status'] == 'succeeded'
        assert answered['finishedAt'] is not None

    def test_a_local_run_whose_job_cannot_be_written_is_not_created(
        self,
        local_client: LocalClient,
        collecting_service: None,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        del collecting_service

        def refuse(*_: Any, **__: Any) -> None:
            raise CoreValidationError('The job could not be written.')

        monkeypatch.setattr(JobRepository, 'create', refuse)

        with pytest.raises(CoreValidationError):
            local_client.collect_run(body=A_COLLECTION)

        assert local_client.list_runs() == []

    def test_a_calendar_neither_mode_reads_fails_the_same(
        self,
        local_client: LocalClient,
        remote_client: Client,
        problem_from: Callable[..., ApiProblem],
    ) -> None:
        asked = {**A_COLLECTION, 'calendar': 'knitting'}
        local = problem_from(local_client, 'collect_run', body=asked)
        remote = problem_from(remote_client, 'collect_run', body=asked)

        assert local.status == remote.status == 422
        assert local.detail == remote.detail
        assert 'knitting' in local.detail

    def test_a_window_neither_mode_accepts_fails_the_same(
        self,
        local_client: LocalClient,
        remote_client: Client,
        problem_from: Callable[..., ApiProblem],
    ) -> None:
        asked = {
            **A_COLLECTION,
            'window': {'start': '2026-10-01', 'end': '2026-09-01'}
        }
        local = problem_from(local_client, 'collect_run', body=asked)
        remote = problem_from(remote_client, 'collect_run', body=asked)

        assert local.status == remote.status == 422
        assert local.detail == remote.detail

    def test_a_refused_collection_creates_no_run_in_either_mode(
        self,
        local_client: LocalClient,
        remote_client: Client
    ) -> None:
        asked = {**A_COLLECTION, 'calendar': 'knitting'}

        for client in (local_client, remote_client):
            with pytest.raises(ApiProblem):
                client.collect_run(body=asked)

        assert local_client.list_runs() == []


class TestTheTwoModesCollectAgainTheSame:
    def test_a_recollection_answers_with_a_job_on_the_same_run(
        self,
        both: Callable[..., Tuple[Any, Any]],
        collecting_service: None,
        collected_in_both: Tuple[str, str]
    ) -> None:
        # One question, not two: a recollection answers with a job of
        # the right kind, working on the run it was asked about, and
        # a mode that got either wrong would be answering about
        # something else.
        del collecting_service
        local_run, remote_run = collected_in_both

        local, remote = both.asked(
            operation='recollect_run',
            local={'run_id': local_run, 'body': NO_CHANGES},
            remote={'run_id': remote_run, 'body': NO_CHANGES}
        )

        assert local['kind'] == remote['kind'] == 'recollect'
        assert local['runId'] == local_run
        assert remote['runId'] == remote_run

    def test_a_run_neither_mode_has_fails_the_same(
        self,
        local_client: LocalClient,
        remote_client: Client,
        problem_from: Callable[..., ApiProblem],
    ) -> None:
        local = problem_from(
            local_client,
            'recollect_run',
            run_id='no-such-run',
            body=NO_CHANGES
        )
        remote = problem_from(
            remote_client,
            'recollect_run',
            run_id='no-such-run',
            body=NO_CHANGES
        )

        assert local.status == remote.status == 404
        assert local.detail == remote.detail

    def test_a_change_count_that_has_moved_fails_the_same(
        self,
        both_refuse: Callable[..., int],
        collecting_service: None,
        collected_in_both: Tuple[str, str]
    ) -> None:
        del collecting_service
        moved = {'expectedChangeCount': 3}

        assert both_refuse(
            collected=collected_in_both,
            body=moved
        ) == 409

    def test_a_sent_run_fails_the_same(
        self,
        both_refuse: Callable[..., int],
        collecting_service: None,
        collected_in_both: Tuple[str, str],
        runs: RunRepository
    ) -> None:
        del collecting_service

        for run_id in collected_in_both:
            runs.set_status(run_id=run_id, status=RUN_STATUS_SENT)

        assert both_refuse(
            collected=collected_in_both,
            body=NO_CHANGES
        ) == 409


@pytest.fixture(name='sending_service')
def fixture_sending_service(
    monkeypatch: pytest.MonkeyPatch,
    amplify_holds: Callable[..., list]
) -> None:
    """ Replace the sending itself in both modes.

        What a send does is pinned in 'test_send.py'.  What these tests
        ask is whether the two modes claim the key, refuse the same
        requests and answer with the same job -- which writing into a
        stand-in for Amplify would only obscure.  The opportunity read
        each mode makes before deciding is still answered, because that
        read is what the expected count is checked against.
    """
    amplify_holds()

    def nothing(**parameters: Any) -> None:
        """ Stand in for the send. """
        del parameters

    monkeypatch.setattr('star_pass_api._sending.send', nothing)
    monkeypatch.setattr('star_pass_client._local_writes.send', nothing)

    return None


@pytest.fixture(name='send_asked_of_both')
def fixture_send_asked_of_both(
    sendable_in_both: Tuple[str, str]
) -> dict:
    """ Return the per-mode parameters for sending each mode's run.

        A key each, because one database holds both modes and a key
        claims one send, not one send per mode.
    """
    local_run, remote_run = sendable_in_both

    return {
        'operation': 'send_run',
        'local': {
            'run_id': local_run,
            'body': NOTHING_TO_SEND,
            'idempotency_key': 'local-attempt'
        },
        'remote': {
            'run_id': remote_run,
            'body': NOTHING_TO_SEND,
            'idempotency_key': 'remote-attempt'
        }
    }


@pytest.fixture(name='resuming_service')
def fixture_resuming_service(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """ Replace what a resumed job runs, in both modes.

        What the work does is pinned where that work is tested.  These
        tests ask whether the two modes queue the job again, hand it to
        the same kind of worker, and refuse the same things.
    """

    def nothing(job: Any, principal_id: str) -> Callable[..., None]:
        """ Stand in for the work a resumed job runs. """
        del job, principal_id

        return lambda _connection, _reporter: None

    monkeypatch.setattr('star_pass_api._jobs.work_for', nothing)
    monkeypatch.setattr('star_pass_client._local_writes.work_for', nothing)

    return None


@pytest.fixture(name='ended_job')
def fixture_ended_job(
    resuming_service: None,
    jobs: JobRepository,
    collected: str
) -> str:
    """ Return a job that succeeded, which no resume applies to. """
    del resuming_service

    job = jobs.create(
        run_id=collected,
        kind=JOB_KIND_SEND,
        principal_id=API_PRINCIPAL_ID
    )
    jobs.start(job_id=job.id)
    jobs.finish(job_id=job.id, status=JOB_STATUS_SUCCEEDED)

    return job.id


@pytest.fixture(name='interrupted_in_both')
def fixture_interrupted_in_both(
    jobs: JobRepository,
    collected: str,
    other_run_id: str
) -> Tuple[str, str]:
    """ Return an interrupted job for each mode to resume.

        One each, because resuming a job changes it: a pair asked
        about one job would have the second mode refusing what the
        first had already queued.
    """
    made = []

    for run_id, holder in (
        (collected, JOB_HOLDER_LOCAL),
        (other_run_id, JOB_HOLDER_SERVICE)
    ):
        job = jobs.create(
            run_id=run_id,
            kind=JOB_KIND_COLLECT,
            principal_id=API_PRINCIPAL_ID,
            held_by=holder
        )
        jobs.start(job_id=job.id)
        jobs.finish(job_id=job.id, status=JOB_STATUS_INTERRUPTED)
        made.append(job.id)

    return made[0], made[1]


@pytest.fixture(name='sendable_in_both')
def fixture_sendable_in_both(
    both: Callable[..., Tuple[Any, Any]],
    runs: RunRepository,
    collected_in_both: Tuple[str, str]
) -> Tuple[str, str]:
    """ Return a run each mode may send, holding nothing to create.

        A run with no events, so the count both modes confirm against
        is zero in either.  What is compared is the claiming and the
        refusing, not the calendar.
    """
    del both

    for run_id in collected_in_both:
        runs.set_status(run_id=run_id, status=RUN_STATUS_UNSENT)

    return collected_in_both


class TestSendingInEitherMode:
    def test_a_send_answers_with_the_same_job(
        self,
        both: Callable[..., Tuple[Any, Any]],
        sending_service: None,
        send_asked_of_both: dict,
        sendable_in_both: Tuple[str, str]
    ) -> None:
        del sending_service
        local_run, remote_run = sendable_in_both

        local, remote = both.asked(**send_asked_of_both)

        assert local['kind'] == remote['kind'] == JOB_KIND_SEND
        assert local['runId'] == local_run
        assert remote['runId'] == remote_run

    def test_a_local_collection_is_held_by_the_command_line(
        self,
        both: Callable[..., Tuple[Any, Any]],
        collecting_service: None,
        jobs: JobRepository
    ) -> None:
        # It is the holder that lets each half sweep up after itself
        # without ending the other's work.
        del collecting_service

        local, remote = both('collect_run', body=A_COLLECTION)

        assert jobs.get(job_id=local['id']).held_by == JOB_HOLDER_LOCAL
        assert jobs.get(
            job_id=remote['id']
        ).held_by == JOB_HOLDER_SERVICE

    def test_a_local_send_is_recorded_as_the_command_line(
        self,
        both: Callable[..., Tuple[Any, Any]],
        sending_service: None,
        jobs: JobRepository,
        send_asked_of_both: dict
    ) -> None:
        # Two writers into one live volunteer system are two different
        # people acting (D13).
        del sending_service

        local, remote = both.asked(**send_asked_of_both)

        assert jobs.get(job_id=local['id']).principal_id == 'local-cli'
        assert jobs.get(
            job_id=remote['id']
        ).principal_id != 'local-cli'

    def test_both_refuse_a_count_that_has_moved_the_same_way(
        self,
        both_refuse: Callable[..., int],
        sending_service: None,
        sendable_in_both: Tuple[str, str]
    ) -> None:
        del sending_service

        assert both_refuse(
            collected=sendable_in_both,
            operation='send_run',
            body={'expectedShiftCount': 5},
            idempotency_key='a-key'
        ) == 409

    def test_both_answer_a_replay_with_the_job_they_started(
        self,
        both: Callable[..., Tuple[Any, Any]],
        sending_service: None,
        send_asked_of_both: dict
    ) -> None:
        del sending_service
        first = both.asked(**send_asked_of_both)

        again = both.asked(**send_asked_of_both)

        assert again == first


class TestSweepingUpAfterACommandThatStopped:
    def test_a_write_ends_what_an_earlier_command_left_unfinished(
        self,
        local_client: LocalClient,
        collecting_service: None,
        jobs: JobRepository,
        collected: str
    ) -> None:
        # A run with a job still saying it is running is one nothing
        # can be done with until somebody says what became of the job.
        del collecting_service
        stranded = jobs.create(
            run_id=collected,
            kind=JOB_KIND_SEND,
            principal_id='local-cli',
            held_by=JOB_HOLDER_LOCAL
        )
        jobs.start(job_id=stranded.id)

        local_client.recollect_run(run_id=collected, body=NO_CHANGES)

        assert jobs.get(
            job_id=stranded.id
        ).status == JOB_STATUS_INTERRUPTED

    def test_a_write_leaves_alone_what_the_service_is_holding(
        self,
        local_client: LocalClient,
        collecting_service: None,
        jobs: JobRepository,
        collected: str,
        other_run_id: str
    ) -> None:
        # The two write into one database (D2).  Ended here, a live
        # send would look finished and the run would take a second one
        # while the first was still writing into Amplify.
        del collecting_service
        theirs = jobs.create(
            run_id=other_run_id,
            kind=JOB_KIND_SEND,
            principal_id=API_PRINCIPAL_ID,
            held_by=JOB_HOLDER_SERVICE
        )
        jobs.start(job_id=theirs.id)

        local_client.recollect_run(run_id=collected, body=NO_CHANGES)

        assert jobs.get(job_id=theirs.id).status == JOB_STATUS_RUNNING

    def test_a_read_sweeps_nothing(
        self,
        local_client: LocalClient,
        jobs: JobRepository,
        collected: str
    ) -> None:
        # Reading a run is not a reason to decide something else is
        # over.
        stranded = jobs.create(
            run_id=collected,
            kind=JOB_KIND_SEND,
            principal_id='local-cli',
            held_by=JOB_HOLDER_LOCAL
        )
        jobs.start(job_id=stranded.id)

        local_client.get_run(run_id=collected)

        assert jobs.get(job_id=stranded.id).status == JOB_STATUS_RUNNING


class TestResumingInEitherMode:
    def test_an_interrupted_job_is_resumed_the_same_way(
        self,
        both: Callable[..., Tuple[Any, Any]],
        resuming_service: None,
        interrupted_in_both: Tuple[str, str]
    ) -> None:
        del resuming_service
        local_job, remote_job = interrupted_in_both

        local, remote = both.asked(
            operation='resume_job',
            local={'job_id': local_job},
            remote={'job_id': remote_job}
        )

        assert local['id'] == local_job
        assert remote['id'] == remote_job
        assert local['kind'] == remote['kind']

    def test_a_resumed_job_passes_into_the_hands_running_it(
        self,
        both: Callable[..., Tuple[Any, Any]],
        resuming_service: None,
        jobs: JobRepository,
        interrupted_in_both: Tuple[str, str]
    ) -> None:
        # It is the new holder a later sweep has to recognize.
        del resuming_service
        local_job, remote_job = interrupted_in_both

        both.asked(
            operation='resume_job',
            local={'job_id': local_job},
            remote={'job_id': remote_job}
        )

        assert jobs.get(job_id=local_job).held_by == JOB_HOLDER_LOCAL
        assert jobs.get(job_id=remote_job).held_by == JOB_HOLDER_SERVICE

    def test_both_refuse_a_job_that_ended_the_same_way(
        self,
        local_client: LocalClient,
        remote_client: Client,
        problem_from: Callable[..., ApiProblem],
        ended_job: str
    ) -> None:
        local = problem_from(local_client, 'resume_job', job_id=ended_job)
        remote = problem_from(
            remote_client,
            'resume_job',
            job_id=ended_job
        )

        assert local.status == remote.status == 409
        assert local.detail == remote.detail
