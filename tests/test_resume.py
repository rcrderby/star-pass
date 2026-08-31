#!/usr/bin/env python3
""" What running an interrupted job again actually runs.

    The endpoint tests replace this, because what they ask is whether a
    job is queued again and handed over.  What is handed over is asked
    here: a resumed collection has to collect and a resumed send has to
    send, and a half that ran the wrong one would put a revision where
    a volunteer system was expecting shifts, or the other way round.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
import sqlite3
from typing import Any, Callable, List, Tuple

# Imports - Third-Party
import pytest

# Imports - Local
from star_pass._records import (
    JOB_KIND_COLLECT,
    JOB_KIND_RECOLLECT,
    JOB_KIND_SEND
)
from star_pass._reporting import Reporter
from star_pass._repository import JobRepository
from star_pass._resume import resume_key, work_for

# Constants
# Who asked for the resume.
PRINCIPAL_ID = 'whoever-clicked'


@pytest.fixture(name='recorded')
def fixture_recorded(
    monkeypatch: pytest.MonkeyPatch
) -> List[Tuple[str, dict]]:
    """ Replace the work itself, keeping what each was asked for.

        What collecting and sending do is pinned where each is tested;
        this is about which of them a job reaches and with what.
    """
    seen: List[Tuple[str, dict]] = []

    def collecting(**parameters: Any) -> None:
        """ Stand in for a collection. """
        seen.append((JOB_KIND_COLLECT, parameters))

    def sending(**parameters: Any) -> None:
        """ Stand in for a send. """
        seen.append((JOB_KIND_SEND, parameters))

    monkeypatch.setattr('star_pass._resume.collect', collecting)
    monkeypatch.setattr('star_pass._resume.send', sending)

    return seen


@pytest.fixture(name='resuming')
def fixture_resuming(
    jobs: JobRepository,
    connection: sqlite3.Connection,
    run_id: str
) -> Callable[..., Any]:
    """ Return a way to run what resuming a job of one kind runs. """

    def run(kind: str) -> Any:
        """ Build a job of that kind and run what resuming it runs. """
        job = jobs.create(
            run_id=run_id,
            kind=kind,
            principal_id='whoever-asked-first'
        )
        work_for(job=job, principal_id=PRINCIPAL_ID)(
            connection,
            Reporter()
        )

        return job

    return run


class TestWhichWorkAJobReaches:
    def test_a_collection_collects(
        self,
        recorded: List[Tuple[str, dict]],
        resuming: Callable[..., Any]
    ) -> None:
        job = resuming(JOB_KIND_COLLECT)

        assert [kind for kind, _asked in recorded] == [JOB_KIND_COLLECT]
        assert recorded[0][1]['run_id'] == job.run_id

    def test_a_recollection_collects_too(
        self,
        recorded: List[Tuple[str, dict]],
        resuming: Callable[..., Any]
    ) -> None:
        # Collecting again is the same work; what differed was only
        # whether anything was there before.
        resuming(JOB_KIND_RECOLLECT)

        assert [kind for kind, _asked in recorded] == [JOB_KIND_COLLECT]

    def test_a_send_sends(
        self,
        recorded: List[Tuple[str, dict]],
        resuming: Callable[..., Any]
    ) -> None:
        job = resuming(JOB_KIND_SEND)

        assert [kind for kind, _asked in recorded] == [JOB_KIND_SEND]
        assert recorded[0][1]['run_id'] == job.run_id


class TestWhatAResumedSendIsRecordedAs:
    def test_it_is_recorded_against_whoever_asked_to_resume(
        self,
        recorded: List[Tuple[str, dict]],
        resuming: Callable[..., Any]
    ) -> None:
        # They caused this work, not whoever asked for the attempt that
        # was interrupted.
        resuming(JOB_KIND_SEND)

        assert recorded[0][1]['principal_id'] == PRINCIPAL_ID

    def test_the_rows_it_creates_name_the_resume_that_made_them(
        self,
        recorded: List[Tuple[str, dict]],
        resuming: Callable[..., Any]
    ) -> None:
        job = resuming(JOB_KIND_SEND)

        assert recorded[0][1]['idempotency_key'] == f'resume-{job.id}'
        assert resume_key(job=job) == f'resume-{job.id}'
