#!/usr/bin/env python3
""" Tests for following what a job reports. """

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
import json
import sqlite3
from typing import Any, Callable, Dict, List

# Imports - Third-Party
import pytest
from fastapi.testclient import TestClient

# Imports - Local
from star_pass._records import Job, JOB_STATUS_RUNNING, JOB_STATUS_SUCCEEDED
from star_pass._repository import JobRepository
from star_pass_api import _defaults, _jobs
from star_pass_api._jobs import (
    JOB_FINISHED_EVENT,
    LAST_EVENT_ID_HEADER,
    SSE_MEDIA_TYPE
)
from star_pass_api._problems import PROBLEM_MEDIA_TYPE
from star_pass_api._security import SCOPE_RUNS_READ

# Constants
EVENTS_TEMPLATE = f'{_defaults.API_VERSION_PREFIX}/jobs/{{job_id}}/events'


def events_path(job_id: str) -> str:
    """ Return the address of one job's event stream. """
    return EVENTS_TEMPLATE.format(job_id=job_id)


def frames(body: str) -> List[Dict[str, Any]]:
    """ Return the frames in a stream, as fields.

        Comments are dropped: they carry nothing and exist to keep the
        connection open.
    """
    parsed = []

    for block in body.split('\n\n'):
        fields: Dict[str, Any] = {}

        for line in block.splitlines():
            if not line or line.startswith(':'):
                continue
            name, _, value = line.partition(': ')
            fields[name] = value

        if fields:
            if 'data' in fields:
                fields['data'] = json.loads(fields['data'])
            parsed.append(fields)

    return parsed


@pytest.fixture(name='finished_job')
def fixture_finished_job(
    jobs: JobRepository,
    job_id: str
) -> str:
    """ Return a job that ran, reported two things, and succeeded. """
    jobs.start(job_id=job_id)
    jobs.add_event(
        job_id=job_id,
        kind='step_started',
        payload={'label': 'Reading the calendar'}
    )
    jobs.add_event(job_id=job_id, kind='step_finished')
    jobs.finish(job_id=job_id, status=JOB_STATUS_SUCCEEDED)

    return job_id


class TestFollowingAJob:
    def test_each_report_arrives_as_a_frame(
        self,
        running_client: TestClient,
        finished_job: str
    ) -> None:
        sent = frames(
            running_client.get(events_path(job_id=finished_job)).text
        )

        assert [frame['event'] for frame in sent] == [
            'step_started',
            'step_finished',
            JOB_FINISHED_EVENT
        ]

    def test_a_frame_carries_what_the_report_held(
        self,
        running_client: TestClient,
        finished_job: str
    ) -> None:
        first = frames(
            running_client.get(events_path(job_id=finished_job)).text
        )[0]

        assert first['data'] == {'label': 'Reading the calendar'}

    def test_a_frame_is_identified_so_it_can_be_resumed_from(
        self,
        running_client: TestClient,
        finished_job: str
    ) -> None:
        sent = frames(
            running_client.get(events_path(job_id=finished_job)).text
        )

        assert [frame['id'] for frame in sent[:2]] == ['1', '2']

    def test_the_stream_ends_by_saying_how_the_job_ended(
        self,
        running_client: TestClient,
        finished_job: str
    ) -> None:
        # So a client is not left to ask separately.
        last = frames(
            running_client.get(events_path(job_id=finished_job)).text
        )[-1]

        assert last['event'] == JOB_FINISHED_EVENT
        assert last['data']['status'] == JOB_STATUS_SUCCEEDED

    def test_the_ending_frame_is_not_resumable(
        self,
        running_client: TestClient,
        finished_job: str
    ) -> None:
        # It is not one of the job's own events, so it is not a place
        # a reader can come back to.
        last = frames(
            running_client.get(events_path(job_id=finished_job)).text
        )[-1]

        assert 'id' not in last

    def test_a_job_that_reported_nothing_still_ends(
        self,
        running_client: TestClient,
        jobs: JobRepository,
        job_id: str
    ) -> None:
        jobs.start(job_id=job_id)
        jobs.finish(job_id=job_id, status=JOB_STATUS_SUCCEEDED)

        sent = frames(running_client.get(events_path(job_id=job_id)).text)

        assert [frame['event'] for frame in sent] == [JOB_FINISHED_EVENT]

    def test_the_stream_says_what_it_is(
        self,
        running_client: TestClient,
        finished_job: str
    ) -> None:
        response = running_client.get(events_path(job_id=finished_job))

        assert response.headers['content-type'].startswith(SSE_MEDIA_TYPE)
        assert response.headers['cache-control'] == 'no-cache'


class TestReattaching:
    def test_a_reader_is_given_only_what_it_missed(
        self,
        running_client: TestClient,
        finished_job: str
    ) -> None:
        sent = frames(
            running_client.get(
                events_path(job_id=finished_job),
                headers={LAST_EVENT_ID_HEADER: '1'}
            ).text
        )

        assert [frame['event'] for frame in sent] == [
            'step_finished',
            JOB_FINISHED_EVENT
        ]

    def test_a_reader_up_to_date_gets_only_the_ending(
        self,
        running_client: TestClient,
        finished_job: str
    ) -> None:
        sent = frames(
            running_client.get(
                events_path(job_id=finished_job),
                headers={LAST_EVENT_ID_HEADER: '2'}
            ).text
        )

        assert [frame['event'] for frame in sent] == [JOB_FINISHED_EVENT]

    def test_a_header_that_is_not_an_identifier_starts_over(
        self,
        running_client: TestClient,
        finished_job: str
    ) -> None:
        # Sending everything is the safe reading of a value that says
        # nothing usable; skipping events would lose them silently.
        sent = frames(
            running_client.get(
                events_path(job_id=finished_job),
                headers={LAST_EVENT_ID_HEADER: 'not-a-number'}
            ).text
        )

        assert len(sent) == 3


class TestTheOrderTheLoopReadsIn:
    def test_an_event_written_between_the_two_reads_is_not_missed(
        self,
        monkeypatch: pytest.MonkeyPatch,
        running_client: TestClient,
        connect_to_database: Callable[[], sqlite3.Connection],
        jobs: JobRepository,
        job_id: str
    ) -> None:
        # The loop reads the job's status, then its events.  Read the
        # other way round, an event written between the two would be
        # lost: the events read would not hold it, and the status read
        # after it would end the stream.
        #
        # This widens that gap and writes into it.  The reads are, in
        # order: the check that the job exists, then the status, then
        # the events -- so writing after the second is writing into the
        # gap.
        jobs.start(job_id=job_id)
        real_read = _jobs.read
        reads = {'count': 0}

        async def read_then_write(work: Any) -> Any:
            result = await real_read(work)
            reads['count'] += 1

            if reads['count'] == 2:
                connection = connect_to_database()
                try:
                    repository = JobRepository(connection=connection)
                    repository.add_event(
                        job_id=job_id,
                        kind='step_finished'
                    )
                    repository.finish(
                        job_id=job_id,
                        status=JOB_STATUS_SUCCEEDED
                    )
                finally:
                    connection.close()

            return result

        monkeypatch.setattr(_jobs, 'read', read_then_write)

        sent = frames(running_client.get(events_path(job_id=job_id)).text)

        assert [frame['event'] for frame in sent] == [
            'step_finished',
            JOB_FINISHED_EVENT
        ]

    def test_the_status_is_read_before_the_events(
        self,
        monkeypatch: pytest.MonkeyPatch,
        running_client: TestClient,
        jobs: JobRepository,
        job_id: str
    ) -> None:
        # Stated directly as well, so the order cannot be changed
        # without a test saying so.
        jobs.start(job_id=job_id)
        jobs.finish(job_id=job_id, status=JOB_STATUS_SUCCEEDED)

        real_read = _jobs.read
        results: List[str] = []

        async def note(work: Any) -> Any:
            result = await real_read(work)
            results.append(
                'job' if isinstance(result, Job) else 'events'
            )

            return result

        monkeypatch.setattr(_jobs, 'read', note)
        running_client.get(events_path(job_id=job_id))

        # The first is the check that the job exists; the loop follows.
        assert results[:3] == ['job', 'job', 'events']


class TestWhoMayFollow:
    def test_following_a_job_needs_a_credential(
        self,
        anonymous_client: TestClient,
        finished_job: str
    ) -> None:
        assert anonymous_client.get(
            events_path(job_id=finished_job)
        ).status_code == 401

    def test_an_unknown_job_is_not_found(
        self,
        running_client: TestClient
    ) -> None:
        # Checked before the stream opens, so a mistyped identifier is
        # an error a client can read rather than a stream saying
        # nothing.
        response = running_client.get(events_path(job_id='no-such-job'))

        assert response.status_code == 404
        assert response.headers['content-type'] == PROBLEM_MEDIA_TYPE


class TestWhatTheSpecificationSays:
    def test_following_a_job_declares_the_scope_it_needs(
        self,
        client: TestClient
    ) -> None:
        security = client.get(
            _defaults.API_OPENAPI_PATH
        ).json()['paths']['/v1/jobs/{job_id}/events']['get']['security']

        assert [SCOPE_RUNS_READ] in [
            scopes
            for requirement in security
            for scopes in requirement.values()
        ]

    def test_the_stream_is_published_as_an_event_stream(
        self,
        client: TestClient
    ) -> None:
        responses = client.get(
            _defaults.API_OPENAPI_PATH
        ).json()['paths']['/v1/jobs/{job_id}/events']['get']['responses']

        assert SSE_MEDIA_TYPE in responses['200']['content']


def finish_after(
    monkeypatch: pytest.MonkeyPatch,
    connect_to_database: Callable[[], sqlite3.Connection],
    job_id: str,
    polls: int
) -> Dict[str, int]:
    """ Make the stream finish the job after it has polled 'polls' times.

        The job is finished from inside the loop rather than from the
        test's thread: the test client produces the whole response
        before handing it back, so nothing outside the application can
        act while a stream is open.

        Returns the counter, so a test can assert the stream kept
        looking rather than ending at its first.
    """
    real_read = _jobs.read
    counted = {'count': 0}

    async def read_and_maybe_finish(work: Any) -> Any:
        result = await real_read(work)

        if isinstance(result, Job) and result.status == JOB_STATUS_RUNNING:
            counted['count'] += 1

            if counted['count'] == polls:
                connection = connect_to_database()
                try:
                    JobRepository(connection=connection).finish(
                        job_id=job_id,
                        status=JOB_STATUS_SUCCEEDED
                    )
                finally:
                    connection.close()

        return result

    monkeypatch.setattr(_jobs, 'read', read_and_maybe_finish)

    return counted


class TestARunningJob:
    def test_the_stream_stays_open_while_the_job_runs(
        self,
        monkeypatch: pytest.MonkeyPatch,
        running_client: TestClient,
        connect_to_database: Callable[[], sqlite3.Connection],
        jobs: JobRepository,
        job_id: str
    ) -> None:
        # It ends when the job does, not when it runs out of events to
        # send, which is what makes it worth holding open.
        monkeypatch.setattr(_jobs, 'POLL_SECONDS', 0.01)
        jobs.start(job_id=job_id)
        counted = finish_after(
            monkeypatch=monkeypatch,
            connect_to_database=connect_to_database,
            job_id=job_id,
            polls=3
        )

        sent = frames(running_client.get(events_path(job_id=job_id)).text)

        assert counted['count'] >= 3
        assert sent[-1]['event'] == JOB_FINISHED_EVENT

    def test_a_silent_stream_is_kept_alive(
        self,
        monkeypatch: pytest.MonkeyPatch,
        running_client: TestClient,
        connect_to_database: Callable[[], sqlite3.Connection],
        jobs: JobRepository,
        job_id: str
    ) -> None:
        # A job can be quiet for minutes, and an idle connection is
        # what a proxy in front of the service closes.
        monkeypatch.setattr(_jobs, 'POLL_SECONDS', 0.01)
        monkeypatch.setattr(_jobs, 'HEARTBEAT_SECONDS', 0.02)
        jobs.start(job_id=job_id)
        finish_after(
            monkeypatch=monkeypatch,
            connect_to_database=connect_to_database,
            job_id=job_id,
            polls=6
        )

        body = running_client.get(events_path(job_id=job_id)).text

        assert ': keep-alive' in body
