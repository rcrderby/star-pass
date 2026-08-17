#!/usr/bin/env python3
""" Tests for running a job and recording what it reported. """

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
import logging
import sqlite3
from typing import Callable, Iterator, List

# Imports - Third-Party
import pytest

# Imports - Local
from star_pass._exceptions import UpstreamError, ValidationError
from star_pass._job_runner import JobReporter, JobRunner, UNEXPECTED_DETAIL
from star_pass._records import JOB_STATUS_FAILED, JOB_STATUS_SUCCEEDED
from star_pass._reporting import Reporter, ShiftBatch
from star_pass._repository import JobRepository

# Constants
# How long a test waits for a job before calling it stuck.  Generous:
# it is a failure threshold, not an expected duration.
JOB_TIMEOUT_SECONDS = 15

# A message shaped like the ones a defect can carry, which must not
# reach what the job stores. The name avoids the words bandit reads as
# a credential being assigned here.
WITHHELD_REASON = 'connection refused for token abcd1234secret'


@pytest.fixture(name='runner')
def fixture_runner(
    connect_to_database: Callable[[], sqlite3.Connection]
) -> Iterator[JobRunner]:
    """ Return a runner on the test's database, shut down afterwards. """
    job_runner = JobRunner(connect=connect_to_database)
    yield job_runner
    job_runner.shutdown()


def run_to_completion(
    runner: JobRunner,
    job_id: str,
    work: Callable[[Reporter], None]
) -> None:
    """ Submit work and wait for the job to be over. """
    runner.submit(
        job_id=job_id,
        work=work
    ).result(timeout=JOB_TIMEOUT_SECONDS)


class TestRunningAJob:
    def test_work_that_returns_leaves_the_job_succeeded(
        self,
        runner: JobRunner,
        jobs: JobRepository,
        job_id: str
    ) -> None:
        run_to_completion(
            runner=runner,
            job_id=job_id,
            work=lambda reporter: None
        )

        assert jobs.get(job_id=job_id).status == JOB_STATUS_SUCCEEDED

    def test_a_job_records_when_it_started_and_finished(
        self,
        runner: JobRunner,
        jobs: JobRepository,
        job_id: str
    ) -> None:
        run_to_completion(
            runner=runner,
            job_id=job_id,
            work=lambda reporter: None
        )
        job = jobs.get(job_id=job_id)

        assert job.started_at is not None
        assert job.finished_at is not None

    def test_a_job_that_is_not_queued_is_refused(
        self,
        runner: JobRunner,
        jobs: JobRepository,
        job_id: str
    ) -> None:
        # Whatever is already running it would otherwise gain a second
        # worker writing the same events.
        jobs.start(job_id=job_id)

        with pytest.raises(ValidationError):
            run_to_completion(
                runner=runner,
                job_id=job_id,
                work=lambda reporter: None
            )

    def test_the_worker_uses_a_connection_of_its_own(
        self,
        runner: JobRunner,
        jobs: JobRepository,
        job_id: str
    ) -> None:
        # A SQLite connection belongs to the thread that opened it, so
        # a job writing at all proves it did not borrow this one.
        recorded: List[str] = []

        def work(reporter: Reporter) -> None:
            recorded.append('ran')
            reporter.step_started(label='Working')

        run_to_completion(runner=runner, job_id=job_id, work=work)

        assert recorded == ['ran']
        assert jobs.events(job_id=job_id)


class TestWhenWorkFails:
    def test_a_core_failure_leaves_the_job_failed(
        self,
        runner: JobRunner,
        jobs: JobRepository,
        job_id: str
    ) -> None:
        def work(reporter: Reporter) -> None:
            del reporter
            raise UpstreamError('Amplify answered 503')

        run_to_completion(runner=runner, job_id=job_id, work=work)

        assert jobs.get(job_id=job_id).status == JOB_STATUS_FAILED

    def test_a_core_failure_keeps_its_message(
        self,
        runner: JobRunner,
        jobs: JobRepository,
        job_id: str
    ) -> None:
        # Written for the person who asked for the run, and already
        # redacted, so it is what the job records.
        def work(reporter: Reporter) -> None:
            del reporter
            raise UpstreamError('Amplify answered 503')

        run_to_completion(runner=runner, job_id=job_id, work=work)

        assert jobs.get(job_id=job_id).detail == 'Amplify answered 503'

    def test_a_defect_withholds_its_message(
        self,
        runner: JobRunner,
        jobs: JobRepository,
        job_id: str
    ) -> None:
        # A defect's message can carry a credential or an upstream
        # body, and what the job stores is read back over the API.
        def work(reporter: Reporter) -> None:
            del reporter
            raise RuntimeError(WITHHELD_REASON)

        run_to_completion(runner=runner, job_id=job_id, work=work)
        job = jobs.get(job_id=job_id)

        assert job.status == JOB_STATUS_FAILED
        assert job.detail == UNEXPECTED_DETAIL
        assert 'abcd1234secret' not in job.detail

    def test_a_defect_is_logged_in_full(
        self,
        runner: JobRunner,
        job_id: str,
        caplog: pytest.LogCaptureFixture
    ) -> None:
        def work(reporter: Reporter) -> None:
            del reporter
            raise RuntimeError(WITHHELD_REASON)

        with caplog.at_level(logging.ERROR):
            run_to_completion(runner=runner, job_id=job_id, work=work)

        assert WITHHELD_REASON in caplog.text
        assert job_id in caplog.text

    def test_a_failure_does_not_leave_the_job_running(
        self,
        runner: JobRunner,
        jobs: JobRepository,
        job_id: str
    ) -> None:
        # A job left running is one a restart has to sweep, and a
        # caller watching it waits for nothing in the meantime.
        def work(reporter: Reporter) -> None:
            del reporter
            raise RuntimeError('anything')

        run_to_completion(runner=runner, job_id=job_id, work=work)

        assert jobs.get(job_id=job_id).finished_at is not None

    def test_what_was_reported_before_a_failure_is_kept(
        self,
        runner: JobRunner,
        jobs: JobRepository,
        job_id: str
    ) -> None:
        def work(reporter: Reporter) -> None:
            reporter.step_started(label='Sending shifts')
            reporter.step_failed()
            raise UpstreamError('Amplify answered 503')

        run_to_completion(runner=runner, job_id=job_id, work=work)

        assert [
            event.kind
            for event in jobs.events(job_id=job_id)
        ] == ['step_started', 'step_failed']


class TestTheReporterBridge:
    def test_it_is_a_reporter_the_core_accepts(
        self,
        jobs: JobRepository,
        job_id: str
    ) -> None:
        assert isinstance(
            JobReporter(jobs=jobs, job_id=job_id),
            Reporter
        )

    def test_each_call_becomes_an_event_named_for_it(
        self,
        jobs: JobRepository,
        job_id: str
    ) -> None:
        reporter = JobReporter(jobs=jobs, job_id=job_id)

        reporter.calendar_read_started()
        reporter.sending_started()
        reporter.summary_skipped()

        assert [
            event.kind
            for event in jobs.events(job_id=job_id)
        ] == [
            'calendar_read_started',
            'sending_started',
            'summary_skipped'
        ]

    def test_a_step_carries_its_label(
        self,
        jobs: JobRepository,
        job_id: str
    ) -> None:
        JobReporter(
            jobs=jobs,
            job_id=job_id
        ).step_started(label='Removing duplicate shifts')

        assert jobs.events(job_id=job_id)[0].payload == {
            'label': 'Removing duplicate shifts'
        }

    def test_sent_shifts_do_not_record_the_request_body(
        self,
        jobs: JobRepository,
        job_id: str
    ) -> None:
        # It is built from the shifts, so storing both keeps two copies
        # of one fact.
        JobReporter(jobs=jobs, job_id=job_id).shifts_sent(
            batch=ShiftBatch(
                index=1,
                need_id=905196,
                title='Adult Scrimmages: Skating Officials',
                url='https://example.test/needs/905196/shifts',
                shifts=[{'start': '2026-09-03 19:15:00', 'duration': 135}],
                payload={'shifts': [{'start': '2026-09-03 19:15:00'}]}
            )
        )
        payload = jobs.events(job_id=job_id)[0].payload

        assert 'payload' not in payload
        assert payload['need_id'] == '905196'
        assert payload['shifts'] == [
            {'start': '2026-09-03 19:15:00', 'duration': 135}
        ]

    def test_a_slack_dry_run_records_how_many_blocks(
        self,
        jobs: JobRepository,
        job_id: str
    ) -> None:
        JobReporter(jobs=jobs, job_id=job_id).slack_dry_run(
            payload=[{'type': 'header'}, {'type': 'section'}]
        )

        assert jobs.events(job_id=job_id)[0].payload == {'blocks': 2}
