#!/usr/bin/env python3
""" Tests for the figures a run's own row cannot state.

    Every one of them is derived rather than stored -- the counts over
    the current revision, and the job still working on the run -- so
    each test here arranges the state the figure is read from and
    reads it back through the repository, which is the only thing that
    knows how it is derived.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring
# pylint: disable=too-many-arguments,too-many-positional-arguments

# Imports - Python Standard Library
from typing import Callable

# Imports - Third-Party
import pytest

# Imports - Local
from star_pass._records import (
    Event,
    EventRole,
    JOB_KIND_SEND,
    JOB_STATUS_FAILED,
    JOB_STATUS_SUCCEEDED,
    UncollectedEvent,
    UNCOLLECTED_ALL_DAY,
    UNCOLLECTED_SEARCH
)
from star_pass._repository import (
    EventRepository,
    JobRepository,
    RunRepository,
    UncollectedRepository
)


@pytest.fixture(name='job_that_succeeded')
def fixture_job_that_succeeded(
    jobs: JobRepository,
    job_id: str
) -> str:
    """ Return the run's job, run to completion.

        Arranged once for the two figures read off it: nothing is
        working on the run any more, and the last thing that happened
        to it was not interrupted.  Two arrangements would be two
        statements of one state, and the duplicate check says so.
    """
    jobs.start(job_id=job_id)
    jobs.finish(job_id=job_id, status=JOB_STATUS_SUCCEEDED)

    return job_id


class TestRunFigures:
    def test_a_run_with_no_revision_counts_nothing(
        self,
        runs: RunRepository,
        run_id: str
    ) -> None:
        run = runs.get(run_id=run_id)

        assert run.event_count == 0
        assert run.shift_count == 0
        assert run.unmatched_count == 0
        assert run.uncollected_count == 0

    def test_what_the_window_held_and_the_run_left_out_is_counted(
        self,
        runs: RunRepository,
        uncollected: UncollectedRepository,
        run_id: str
    ) -> None:
        uncollected.replace(
            run_id=run_id,
            uncollected=[
                UncollectedEvent(id='gcal-1', reason=UNCOLLECTED_SEARCH),
                UncollectedEvent(id='gcal-2', reason=UNCOLLECTED_ALL_DAY)
            ]
        )

        assert runs.get(run_id=run_id).uncollected_count == 2

    def test_that_count_does_not_follow_the_current_revision(
        self,
        events: EventRepository,
        runs: RunRepository,
        uncollected: UncollectedRepository,
        edited: str,
        make_event: Callable[..., Event]
    ) -> None:
        # It describes the window the collection read, so editing the
        # events cannot change it.
        uncollected.replace(
            run_id=edited,
            uncollected=[
                UncollectedEvent(id='gcal-1', reason=UNCOLLECTED_SEARCH)
            ]
        )
        events.add(
            run_id=edited,
            revision=2,
            event=make_event(id='event-2')
        )

        assert runs.get(run_id=edited).uncollected_count == 1

    def test_another_runs_window_is_not_counted_against_this_one(
        self,
        runs: RunRepository,
        uncollected: UncollectedRepository,
        run_id: str,
        other_run_id: str
    ) -> None:
        uncollected.replace(
            run_id=other_run_id,
            uncollected=[
                UncollectedEvent(id='gcal-1', reason=UNCOLLECTED_SEARCH)
            ]
        )

        assert runs.get(run_id=run_id).uncollected_count == 0

    def test_the_events_of_the_current_revision_are_counted(
        self,
        runs: RunRepository,
        collected: str
    ) -> None:
        run = runs.get(run_id=collected)

        assert run.event_count == 1

    def test_a_shift_is_counted_per_role_and_not_per_event(
        self,
        runs: RunRepository,
        collected: str,
        add_second_event: Callable[..., None]
    ) -> None:
        # An event serving both skating and non-skating officials
        # creates two shifts, so counting events would report two where
        # a send would create three.
        add_second_event(
            roles=(
                EventRole(need_id='905196', slots=4),
                EventRole(need_id='905197', slots=2)
            )
        )

        run = runs.get(run_id=collected)

        assert run.event_count == 2
        assert run.shift_count == 3

    def test_an_event_with_no_role_counts_as_unmatched(
        self,
        runs: RunRepository,
        collected: str,
        add_second_event: Callable[..., None]
    ) -> None:
        add_second_event(category=None, roles=())

        run = runs.get(run_id=collected)

        assert run.event_count == 2
        assert run.shift_count == 1
        assert run.unmatched_count == 1

    def test_an_event_with_a_role_is_not_unmatched(
        self,
        runs: RunRepository,
        collected: str
    ) -> None:
        run = runs.get(run_id=collected)

        assert run.unmatched_count == 0

    def test_the_figures_follow_the_current_revision(
        self,
        events: EventRepository,
        runs: RunRepository,
        edited: str,
        make_event: Callable[..., Event]
    ) -> None:
        # Revision 1 keeps the one event it was collected with; the
        # second belongs to revision 2 alone, so a figure counting the
        # wrong revision reports one event rather than two.
        events.add(
            run_id=edited,
            revision=2,
            event=make_event(id='event-2')
        )

        run = runs.get(run_id=edited)

        assert run.current_revision == 2
        assert run.event_count == 2
        assert run.shift_count == 2

    def test_a_run_reports_the_job_still_working_on_it(
        self,
        runs: RunRepository,
        run_id: str,
        job_id: str
    ) -> None:
        assert runs.get(run_id=run_id).active_job_id == job_id

    def test_a_running_job_is_still_the_active_one(
        self,
        jobs: JobRepository,
        runs: RunRepository,
        run_id: str,
        job_id: str
    ) -> None:
        jobs.start(job_id=job_id)

        assert runs.get(run_id=run_id).active_job_id == job_id

    def test_a_finished_job_leaves_the_run_with_none(
        self,
        runs: RunRepository,
        run_id: str,
        job_that_succeeded: str
    ) -> None:
        del job_that_succeeded

        assert runs.get(run_id=run_id).active_job_id is None

    def test_an_interrupted_job_leaves_the_run_with_none(
        self,
        jobs: JobRepository,
        runs: RunRepository,
        run_id: str,
        job_id: str
    ) -> None:
        # Interrupted is finished as far as a run is concerned: nothing
        # is working on it, and offering the identifier as active would
        # send a client to watch a stream that ends at once.
        assert runs.get(run_id=run_id).active_job_id == job_id

        jobs.interrupt_unfinished()

        assert runs.get(run_id=run_id).active_job_id is None

    def test_the_newest_unfinished_job_is_the_active_one(
        self,
        jobs: JobRepository,
        runs: RunRepository,
        run_id: str,
        job_id: str,
        job_principal: str
    ) -> None:
        # Both are asked for inside the same second, so a tiebreak on
        # the stamp or on the identifier would answer at random.
        newer = jobs.create(
            run_id=run_id,
            kind=JOB_KIND_SEND,
            principal_id=job_principal
        )

        assert newer.id != job_id
        assert runs.get(run_id=run_id).active_job_id == newer.id

    def test_another_runs_job_is_not_this_runs_active_one(
        self,
        runs: RunRepository,
        run_id: str,
        job_id: str
    ) -> None:
        other = runs.create(
            calendar='events',
            window_start='2026-09-01',
            window_end='2026-10-01'
        )

        assert runs.get(run_id=run_id).active_job_id == job_id
        assert runs.get(run_id=other.id).active_job_id is None


class TestTheInterruptedJob:
    def test_a_run_nothing_has_happened_to_reports_none(
        self,
        runs: RunRepository,
        run_id: str
    ) -> None:
        assert runs.get(run_id=run_id).interrupted_job_id is None

    def test_a_queued_job_is_not_reported(
        self,
        runs: RunRepository,
        run_id: str,
        job_id: str
    ) -> None:
        # Both states a job is in hand under are checked, and neither
        # covers the other: a job asked for and not yet picked up is
        # the 'activeJobId', and a caller offered a resume for one
        # would be offered a second worker for it.
        del job_id

        assert runs.get(run_id=run_id).interrupted_job_id is None

    def test_a_running_job_is_not_reported(
        self,
        jobs: JobRepository,
        runs: RunRepository,
        run_id: str,
        job_id: str
    ) -> None:
        jobs.start(job_id=job_id)

        assert runs.get(run_id=run_id).interrupted_job_id is None

    def test_an_interrupted_job_is_reported(
        self,
        jobs: JobRepository,
        runs: RunRepository,
        run_id: str,
        job_id: str
    ) -> None:
        # The whole point of the field: an interrupted job is finished,
        # so it is never the active one, and nothing else names it.
        jobs.interrupt_unfinished()

        assert runs.get(run_id=run_id).interrupted_job_id == job_id

    def test_a_job_that_succeeded_is_not_reported(
        self,
        runs: RunRepository,
        run_id: str,
        job_that_succeeded: str
    ) -> None:
        del job_that_succeeded

        assert runs.get(run_id=run_id).interrupted_job_id is None

    def test_a_job_that_failed_is_not_reported(
        self,
        jobs: JobRepository,
        runs: RunRepository,
        run_id: str,
        job_id: str
    ) -> None:
        # A failure is a thing that happened, not a thing left in the
        # middle. Retrying it is sending the run again, which is its
        # own request.
        jobs.start(job_id=job_id)
        jobs.finish(job_id=job_id, status=JOB_STATUS_FAILED)

        assert runs.get(run_id=run_id).interrupted_job_id is None

    def test_a_later_job_takes_the_interrupted_one_off_the_run(
        self,
        jobs: JobRepository,
        runs: RunRepository,
        run_id: str,
        job_id: str,
        job_principal: str
    ) -> None:
        # The question is whether the *last* thing that happened to
        # this run was interrupted. A send somebody has since carried
        # out is not something to go on offering to resume.
        del job_id

        jobs.interrupt_unfinished()
        later = jobs.create(
            run_id=run_id,
            kind=JOB_KIND_SEND,
            principal_id=job_principal
        )
        jobs.start(job_id=later.id)
        jobs.finish(job_id=later.id, status=JOB_STATUS_SUCCEEDED)

        assert runs.get(run_id=run_id).interrupted_job_id is None

    def test_the_newer_of_two_interrupted_jobs_is_the_one_reported(
        self,
        jobs: JobRepository,
        runs: RunRepository,
        run_id: str,
        job_id: str,
        job_principal: str
    ) -> None:
        # Both are asked for inside the same second, so a tiebreak on
        # the stamp would answer at random.
        newer = jobs.create(
            run_id=run_id,
            kind=JOB_KIND_SEND,
            principal_id=job_principal
        )
        jobs.interrupt_unfinished()

        assert newer.id != job_id
        assert runs.get(run_id=run_id).interrupted_job_id == newer.id

    def test_another_runs_interrupted_job_is_not_this_runs(
        self,
        jobs: JobRepository,
        runs: RunRepository,
        run_id: str,
        job_id: str
    ) -> None:
        del job_id

        other = runs.create(
            calendar='events',
            window_start='2026-09-01',
            window_end='2026-10-01'
        )
        jobs.interrupt_unfinished()

        assert runs.get(run_id=run_id).interrupted_job_id is not None
        assert runs.get(run_id=other.id).interrupted_job_id is None


class TestOneStatementForBoth:
    def test_the_list_reports_what_a_single_read_reports(
        self,
        jobs: JobRepository,
        runs: RunRepository,
        collected: str,
        job_principal: str
    ) -> None:
        # The list and the single read derive the same figures from the
        # same statement, and a caller that opened a run from the list
        # would see them change for no reason if they did not.
        jobs.create(
            run_id=collected,
            kind=JOB_KIND_SEND,
            principal_id=job_principal
        )

        listed = runs.list_all()

        assert listed == [runs.get(run_id=collected)]
