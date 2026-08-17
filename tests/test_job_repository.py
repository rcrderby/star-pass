#!/usr/bin/env python3
""" Tests for the job repository. """

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Third-Party
import pytest

# Imports - Local
from star_pass._exceptions import ValidationError
from star_pass._records import (
    JOB_HOLDER_LOCAL,
    JOB_HOLDER_SERVICE,
    JOB_KIND_COLLECT,
    JOB_KIND_SEND,
    JOB_STATUS_FAILED,
    JOB_STATUS_INTERRUPTED,
    JOB_STATUS_QUEUED,
    JOB_STATUS_RUNNING,
    JOB_STATUS_SUCCEEDED
)
from star_pass._repository import JobRepository, RunRepository


@pytest.fixture(name='interrupted_job')
def fixture_interrupted_job(
    jobs: JobRepository,
    job_id: str
) -> str:
    """ Return a job left interrupted by a process that stopped. """
    jobs.start(job_id=job_id)
    jobs.finish(job_id=job_id, status=JOB_STATUS_INTERRUPTED)

    return job_id


class TestAskingForAJob:
    def test_a_new_job_is_queued_and_not_started(
        self,
        jobs: JobRepository,
        job_id: str
    ) -> None:
        job = jobs.get(job_id=job_id)

        assert job.status == JOB_STATUS_QUEUED
        assert job.started_at is None
        assert job.finished_at is None

    def test_a_job_records_who_asked_for_it(
        self,
        jobs: JobRepository,
        job_id: str,
        job_principal: str
    ) -> None:
        assert jobs.get(job_id=job_id).principal_id == job_principal

    def test_ids_are_not_reused_between_jobs(
        self,
        jobs: JobRepository,
        run_id: str,
        job_principal: str
    ) -> None:
        first = jobs.create(
            run_id=run_id,
            kind=JOB_KIND_COLLECT,
            principal_id=job_principal
        )
        second = jobs.create(
            run_id=run_id,
            kind=JOB_KIND_COLLECT,
            principal_id=job_principal
        )

        assert first.id != second.id

    def test_an_unknown_kind_is_refused(
        self,
        jobs: JobRepository,
        run_id: str,
        job_principal: str
    ) -> None:
        with pytest.raises(ValidationError) as error:
            jobs.create(
                run_id=run_id,
                kind='reticulate',
                principal_id=job_principal
            )

        assert 'is not a job kind' in str(error.value)

    def test_a_job_needs_a_run_that_exists(
        self,
        jobs: JobRepository,
        job_principal: str
    ) -> None:
        with pytest.raises(ValidationError):
            jobs.create(
                run_id='no-such-run',
                kind=JOB_KIND_COLLECT,
                principal_id=job_principal
            )

    def test_an_unknown_job_reads_as_nothing(
        self,
        jobs: JobRepository
    ) -> None:
        assert jobs.get(job_id='no-such-job') is None


class TestTheLifeOfAJob:
    def test_starting_a_job_records_when(
        self,
        jobs: JobRepository,
        job_id: str
    ) -> None:
        jobs.start(job_id=job_id)
        job = jobs.get(job_id=job_id)

        assert job.status == JOB_STATUS_RUNNING
        assert job.started_at is not None

    def test_a_job_cannot_be_started_twice(
        self,
        jobs: JobRepository,
        job_id: str
    ) -> None:
        # Two requests arriving together would otherwise both read
        # 'queued' and produce two workers writing the same events.
        jobs.start(job_id=job_id)

        with pytest.raises(ValidationError) as error:
            jobs.start(job_id=job_id)

        assert 'not queued' in str(error.value)

    def test_an_unknown_job_cannot_be_started(
        self,
        jobs: JobRepository
    ) -> None:
        with pytest.raises(ValidationError):
            jobs.start(job_id='no-such-job')

    def test_finishing_a_job_records_when(
        self,
        jobs: JobRepository,
        job_id: str
    ) -> None:
        jobs.start(job_id=job_id)
        jobs.finish(job_id=job_id, status=JOB_STATUS_SUCCEEDED)
        job = jobs.get(job_id=job_id)

        assert job.status == JOB_STATUS_SUCCEEDED
        assert job.finished_at is not None

    def test_a_failure_keeps_its_summary(
        self,
        jobs: JobRepository,
        job_id: str
    ) -> None:
        jobs.start(job_id=job_id)
        jobs.finish(
            job_id=job_id,
            status=JOB_STATUS_FAILED,
            detail='Amplify answered 503'
        )

        assert jobs.get(job_id=job_id).detail == 'Amplify answered 503'

    def test_a_job_that_never_started_cannot_finish(
        self,
        jobs: JobRepository,
        job_id: str
    ) -> None:
        with pytest.raises(ValidationError) as error:
            jobs.finish(job_id=job_id, status=JOB_STATUS_SUCCEEDED)

        assert 'not running' in str(error.value)

    def test_a_status_a_job_does_not_end_in_is_refused(
        self,
        jobs: JobRepository,
        job_id: str
    ) -> None:
        jobs.start(job_id=job_id)

        with pytest.raises(ValidationError) as error:
            jobs.finish(job_id=job_id, status=JOB_STATUS_RUNNING)

        assert 'is not a status a job finishes in' in str(error.value)

    def test_a_runs_jobs_are_listed_newest_first(
        self,
        jobs: JobRepository,
        connection,
        run_id: str,
        job_principal: str
    ) -> None:
        older = jobs.create(
            run_id=run_id,
            kind=JOB_KIND_COLLECT,
            principal_id=job_principal
        )
        newer = jobs.create(
            run_id=run_id,
            kind=JOB_KIND_SEND,
            principal_id=job_principal
        )
        # The two are created in the same second, so the stored time
        # cannot order them on its own.
        connection.execute(
            "UPDATE jobs SET created_at = '2026-01-01T00:00:00+00:00' "
            'WHERE id = ?',
            (older.id,)
        )

        listed = jobs.list_for_run(run_id=run_id)

        assert [job.id for job in listed] == [newer.id, older.id]


class TestARestart:
    def test_a_running_job_is_marked_interrupted(
        self,
        jobs: JobRepository,
        job_id: str
    ) -> None:
        # The process holding it no longer exists, so without this it
        # stays 'running' for good and a caller waits for nothing.
        jobs.start(job_id=job_id)

        assert jobs.interrupt_unfinished() == 1
        assert jobs.get(job_id=job_id).status == JOB_STATUS_INTERRUPTED

    def test_a_queued_job_is_marked_interrupted(
        self,
        jobs: JobRepository,
        job_id: str
    ) -> None:
        # It was waiting on the same process.
        assert jobs.interrupt_unfinished() == 1
        assert jobs.get(job_id=job_id).status == JOB_STATUS_INTERRUPTED

    def test_an_interrupted_job_records_when_it_ended(
        self,
        jobs: JobRepository,
        job_id: str
    ) -> None:
        jobs.start(job_id=job_id)
        jobs.interrupt_unfinished()

        assert jobs.get(job_id=job_id).finished_at is not None

    def test_a_finished_job_is_left_alone(
        self,
        jobs: JobRepository,
        job_id: str
    ) -> None:
        jobs.start(job_id=job_id)
        jobs.finish(job_id=job_id, status=JOB_STATUS_SUCCEEDED)

        assert jobs.interrupt_unfinished() == 0
        assert jobs.get(job_id=job_id).status == JOB_STATUS_SUCCEEDED

    def test_a_second_restart_finds_nothing(
        self,
        jobs: JobRepository,
        job_id: str
    ) -> None:
        jobs.start(job_id=job_id)
        jobs.interrupt_unfinished()

        assert jobs.interrupt_unfinished() == 0

    def test_an_interrupted_job_is_not_resumed_by_the_sweep(
        self,
        jobs: JobRepository,
        job_id: str
    ) -> None:
        # Resuming is a human action: a send that resumed itself would
        # write to a live volunteer system from state rebuilt after a
        # crash (D10).
        jobs.start(job_id=job_id)
        jobs.interrupt_unfinished()

        assert jobs.get(job_id=job_id).status != JOB_STATUS_RUNNING


class TestWhatAJobReported:
    def test_an_event_reads_back_with_what_it_carried(
        self,
        jobs: JobRepository,
        job_id: str
    ) -> None:
        jobs.add_event(
            job_id=job_id,
            kind='step_started',
            payload={'label': 'Reading the calendar'}
        )

        recorded = jobs.events(job_id=job_id)

        assert recorded[0].kind == 'step_started'
        assert recorded[0].payload == {'label': 'Reading the calendar'}

    def test_an_event_without_a_payload_carries_nothing(
        self,
        jobs: JobRepository,
        job_id: str
    ) -> None:
        jobs.add_event(job_id=job_id, kind='step_finished')

        assert jobs.events(job_id=job_id)[0].payload == {}

    def test_events_keep_the_order_they_happened_in(
        self,
        jobs: JobRepository,
        job_id: str
    ) -> None:
        for label in ('first', 'second', 'third'):
            jobs.add_event(
                job_id=job_id,
                kind='step_started',
                payload={'label': label}
            )

        recorded = jobs.events(job_id=job_id)

        assert [event.payload['label'] for event in recorded] == [
            'first',
            'second',
            'third'
        ]

    def test_a_reader_can_continue_from_where_it_stopped(
        self,
        jobs: JobRepository,
        job_id: str
    ) -> None:
        # What makes a stream reattachable: a client that reconnects
        # asks for what came after the last event it saw.
        seen = jobs.add_event(job_id=job_id, kind='step_started')
        missed = jobs.add_event(job_id=job_id, kind='step_finished')

        assert [
            event.id
            for event in jobs.events(job_id=job_id, after=seen.id)
        ] == [missed.id]

    def test_a_reader_that_is_up_to_date_gets_nothing(
        self,
        jobs: JobRepository,
        job_id: str
    ) -> None:
        latest = jobs.add_event(job_id=job_id, kind='step_started')

        assert jobs.events(job_id=job_id, after=latest.id) == []

    def test_an_event_needs_a_job_that_exists(
        self,
        jobs: JobRepository
    ) -> None:
        with pytest.raises(ValidationError):
            jobs.add_event(job_id='no-such-job', kind='step_started')


class TestDeletingTheRun:
    def test_a_deleted_run_takes_its_jobs_and_events_with_it(
        self,
        jobs: JobRepository,
        runs: RunRepository,
        run_id: str,
        job_id: str
    ) -> None:
        jobs.add_event(job_id=job_id, kind='step_started')
        runs.delete(run_id=run_id)

        assert jobs.get(job_id=job_id) is None
        assert jobs.events(job_id=job_id) == []


class TestHoldingAndResumingAJob:
    def test_a_job_says_who_holds_it(
        self,
        jobs: JobRepository,
        job_principal: str,
        run_id: str
    ) -> None:
        job = jobs.create(
            run_id=run_id,
            kind=JOB_KIND_COLLECT,
            principal_id=job_principal,
            held_by=JOB_HOLDER_LOCAL
        )

        assert jobs.get(job_id=job.id).held_by == JOB_HOLDER_LOCAL

    def test_a_holder_nothing_can_hold_a_job_with_is_refused(
        self,
        jobs: JobRepository,
        job_principal: str,
        run_id: str
    ) -> None:
        with pytest.raises(ValidationError):
            jobs.create(
                run_id=run_id,
                kind=JOB_KIND_COLLECT,
                principal_id=job_principal,
                held_by='something-else'
            )

    def test_a_sweep_leaves_alone_what_it_never_held(
        self,
        jobs: JobRepository,
        job_principal: str,
        run_id: str
    ) -> None:
        # The command line and the service write into one database, so
        # a sweep taking everything unfinished would mark a live send
        # interrupted.
        theirs = jobs.create(
            run_id=run_id,
            kind=JOB_KIND_SEND,
            principal_id=job_principal,
            held_by=JOB_HOLDER_SERVICE
        )
        jobs.start(job_id=theirs.id)

        ended = jobs.interrupt_unfinished(held_by=JOB_HOLDER_LOCAL)

        assert ended == 0
        assert jobs.get(job_id=theirs.id).status == JOB_STATUS_RUNNING

    def test_a_sweep_ends_what_its_own_holder_left(
        self,
        jobs: JobRepository,
        job_principal: str,
        run_id: str
    ) -> None:
        mine = jobs.create(
            run_id=run_id,
            kind=JOB_KIND_SEND,
            principal_id=job_principal,
            held_by=JOB_HOLDER_LOCAL
        )
        jobs.start(job_id=mine.id)

        ended = jobs.interrupt_unfinished(held_by=JOB_HOLDER_LOCAL)

        assert ended == 1
        assert jobs.get(job_id=mine.id).status == JOB_STATUS_INTERRUPTED

    def test_an_interrupted_job_is_queued_again(
        self,
        jobs: JobRepository,
        interrupted_job: str
    ) -> None:
        jobs.requeue(job_id=interrupted_job)

        assert jobs.get(job_id=interrupted_job).status == JOB_STATUS_QUEUED

    def test_what_the_interrupted_attempt_said_is_cleared(
        self,
        jobs: JobRepository,
        interrupted_job: str
    ) -> None:
        # When it began and when it stopped described an attempt being
        # made again; leaving them would describe two runs of it at
        # once.
        jobs.requeue(job_id=interrupted_job)
        job = jobs.get(job_id=interrupted_job)

        assert job.started_at is None
        assert job.finished_at is None
        assert job.detail is None

    def test_the_job_passes_to_whoever_is_running_it_now(
        self,
        jobs: JobRepository,
        interrupted_job: str
    ) -> None:
        # It is the new holder a later sweep has to recognize.
        jobs.requeue(
            job_id=interrupted_job,
            held_by=JOB_HOLDER_LOCAL
        )

        assert jobs.get(
            job_id=interrupted_job
        ).held_by == JOB_HOLDER_LOCAL

    def test_a_job_that_is_not_interrupted_is_refused(
        self,
        jobs: JobRepository,
        job_id: str
    ) -> None:
        # Queueing a finished job again would start new work under the
        # identifier of work that already ended.
        with pytest.raises(ValidationError):
            jobs.requeue(job_id=job_id)

    def test_an_unknown_job_is_refused(
        self,
        jobs: JobRepository
    ) -> None:
        with pytest.raises(ValidationError):
            jobs.requeue(job_id='no-such-job')
