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
from typing import Any, Callable

# Imports - Third-Party
import pytest

# Imports - Local
from star_pass._records import (
    Event,
    EventRole,
    JOB_KIND_SEND,
    JOB_STATUS_SUCCEEDED
)
from star_pass._repository import (
    EventRepository,
    JobRepository,
    RunRepository
)


@pytest.fixture(name='add_second_event')
def fixture_add_second_event(
    events: EventRepository,
    collected: str,
    revision: int,
    make_event: Callable[..., Event]
) -> Callable[..., None]:
    """ Return a way to add one more event to the collected run.

        A count is only interesting once there is more than one thing
        to count, so most of these tests want a second event differing
        from the first in the one respect under test.
    """

    def add(**overrides: Any) -> None:
        """ Add an event, replacing any field named in 'overrides'. """
        events.add(
            run_id=collected,
            revision=revision,
            event=make_event(id='event-2', **overrides)
        )

    return add


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
        jobs: JobRepository,
        runs: RunRepository,
        run_id: str,
        job_id: str
    ) -> None:
        jobs.start(job_id=job_id)
        jobs.finish(job_id=job_id, status=JOB_STATUS_SUCCEEDED)

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
