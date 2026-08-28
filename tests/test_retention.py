#!/usr/bin/env python3
""" Forgetting what a run leaves behind, and keeping what matters.

    Three windows and three different questions, which is the whole
    reason this is not one rule with one number.  What every test here
    is really asking is which of these the policy would get wrong:
    forgetting something a later operation needs, or keeping a
    volunteer's name because nothing said to stop.

    The sent record is the first of those and is checked directly: an
    expiry there would eventually have a run offering to create shifts
    Amplify already holds, which is the failure the whole design is
    arranged around.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, List

# Imports - Third-Party
import pytest

# Imports - Local
from star_pass import _defaults
from star_pass._records import (
    JOB_KIND_SEND,
    JOB_STATUS_SUCCEEDED,
    LogEntry,
    OP_NUDGE,
    OPERATION_EDIT,
    ShiftIdentity
)
from star_pass._repository import (
    IdempotencyRepository,
    ChangeLogRepository,
    JobRepository,
    RevisionRepository,
    RunRepository,
    SentShiftRepository,
    UnmatchedTitleRepository
)
from star_pass._retention import Swept, sweep

# Constants
# Somebody, for the columns that record who did a thing (D13).
SOMEBODY = 'a-principal'

# A title in the 'practices' calendar that no category matches, and
# one that does. The pair is the point: the model is what decides
# whether a title is still worth keeping, so a test using only the
# first could not tell the rule from "delete everything".
UNMATCHED_TITLE = 'Bake Sale Fundraiser'
MATCHED_TITLE = 'Adult Scrimmage'
CALENDAR = 'practices'


def hours_later(hours: int) -> datetime:
    """ Return a moment that many hours from now.

        The abandoned-reservation window is measured in hours, so the
        sweep is told what "now" is rather than the row being written
        with an invented timestamp.
    """
    return datetime.now(timezone.utc) + timedelta(hours=hours)


def later(days: int) -> datetime:
    """ Return a moment that many days from now.

        The windows are measured in months, so the sweep is told what
        "now" is rather than the rows being written with invented
        timestamps. A test cannot wait ninety days, and a row written
        by hand is a row the repository did not write.
    """
    return datetime.now(timezone.utc) + timedelta(days=days)


@pytest.fixture(name='sealed')
def fixture_sealed(
    revisions: RevisionRepository,
    run_id: str
) -> List[int]:
    """ Return a run with four revisions, the last one current. """
    return [
        revisions.create(run_id=run_id).number
        for _number in range(1, 5)
    ]


class TestWhatAJobLogLoses:
    def test_the_log_of_a_job_that_finished_long_ago(
        self,
        connection: sqlite3.Connection,
        finished_job: str,
        jobs: JobRepository
    ) -> None:
        sweep(connection=connection, now=later(days=200))

        assert jobs.events(job_id=finished_job) == []

    def test_but_not_the_job_itself(
        self,
        connection: sqlite3.Connection,
        finished_job: str,
        jobs: JobRepository
    ) -> None:
        # That a send ran on a date and how it ended is not what the
        # window is protecting; the log naming volunteers is.
        sweep(connection=connection, now=later(days=200))

        assert jobs.get(job_id=finished_job).status == (
            JOB_STATUS_SUCCEEDED
        )

    def test_nothing_while_the_window_still_covers_it(
        self,
        connection: sqlite3.Connection,
        finished_job: str,
        jobs: JobRepository
    ) -> None:
        sweep(connection=connection, now=later(days=1))

        assert len(jobs.events(job_id=finished_job)) == 1

    def test_nothing_from_a_job_that_has_not_finished(
        self,
        connection: sqlite3.Connection,
        jobs: JobRepository,
        run_id: str
    ) -> None:
        # However old it looks. A job still running is one somebody
        # may be watching, and its log is what they are watching.
        job = jobs.create(
            run_id=run_id,
            kind=JOB_KIND_SEND,
            principal_id=SOMEBODY
        )
        jobs.start(job_id=job.id)
        jobs.add_event(job_id=job.id, kind='step')

        sweep(connection=connection, now=later(days=2000))

        assert len(jobs.events(job_id=job.id)) == 1


class TestWhichRevisionsAreKept:
    def test_the_middle_ones_go_once_the_run_is_old(
        self,
        connection: sqlite3.Connection,
        revisions: RevisionRepository,
        run_id: str,
        sealed: List[int]
    ) -> None:
        del sealed

        sweep(connection=connection, now=later(days=200))

        kept = [
            revision.number
            for revision in revisions.list_all(run_id=run_id)
        ]
        assert kept == [1, 4]

    def test_the_first_is_never_one_of_them(
        self,
        connection: sqlite3.Connection,
        revisions: RevisionRepository,
        run_id: str,
        sealed: List[int]
    ) -> None:
        # Reverting to it is a published operation, and it is what
        # returns hand-added events to the Not collected list.
        del sealed

        sweep(connection=connection, now=later(days=2000))

        assert revisions.get(run_id=run_id, number=1) is not None

    def test_nor_is_the_current_one(
        self,
        connection: sqlite3.Connection,
        revisions: RevisionRepository,
        run_id: str,
        sealed: List[int]
    ) -> None:
        del sealed

        sweep(connection=connection, now=later(days=2000))

        assert revisions.get(run_id=run_id, number=4) is not None

    def test_none_of_them_while_the_run_is_recent(
        self,
        connection: sqlite3.Connection,
        revisions: RevisionRepository,
        run_id: str,
        sealed: List[int]
    ) -> None:
        sweep(connection=connection, now=later(days=1))

        assert len(revisions.list_all(run_id=run_id)) == len(sealed)

    def test_a_run_changed_recently_counts_as_recent(
        self,
        change_log: ChangeLogRepository,
        connection: sqlite3.Connection,
        monkeypatch: pytest.MonkeyPatch,
        revisions: RevisionRepository,
        run_id: str
    ) -> None:
        # The revisions are old and the run is not: an edit changes a
        # revision in place, so a revision's own timestamp says when
        # the work started rather than when it stopped. Reading that
        # instead would throw away the revisions of a run somebody is
        # working in.
        long_ago = (
            datetime.now(timezone.utc) - timedelta(days=400)
        ).isoformat(timespec='seconds')
        monkeypatch.setattr(
            'star_pass._repository._revisions.utc_now',
            lambda: long_ago
        )
        monkeypatch.setattr(
            'star_pass._repository._change_log.utc_now',
            lambda: long_ago
        )
        for _number in range(1, 4):
            revisions.create(run_id=run_id)
        # Two entries, an old one and a recent one, because the run's
        # age is the *latest* of them. With only one, reading the
        # earliest would give the same answer and the test would not
        # say which was read.
        change_log.add(
            run_id=run_id,
            revision=3,
            principal_id=SOMEBODY,
            recorded=LogEntry(action=OP_NUDGE, minutes=30)
        )
        monkeypatch.undo()
        change_log.add(
            run_id=run_id,
            revision=3,
            principal_id=SOMEBODY,
            recorded=LogEntry(action=OP_NUDGE, minutes=-30)
        )

        sweep(connection=connection)

        assert len(revisions.list_all(run_id=run_id)) == 3

    def test_a_run_sealed_recently_counts_as_recent(
        self,
        connection: sqlite3.Connection,
        monkeypatch: pytest.MonkeyPatch,
        revisions: RevisionRepository,
        runs: RunRepository
    ) -> None:
        # A run somebody has done nothing to but seal. Sealing writes
        # no change-log entry, deliberately, so a run dated by the log
        # alone reads as untouched since it was collected -- and has
        # its middle revisions swept while somebody is working in it.
        #
        # The run is collected long ago rather than taken from the
        # fixture, because collection is itself the floor this date
        # cannot go below: a run collected today is recent whatever
        # else is read, and a test using one could not tell the seal
        # from the collection.
        long_ago = (
            datetime.now(timezone.utc) - timedelta(days=400)
        ).isoformat(timespec='seconds')
        monkeypatch.setattr(
            'star_pass._repository._runs.utc_now',
            lambda: long_ago
        )
        monkeypatch.setattr(
            'star_pass._repository._revisions.utc_now',
            lambda: long_ago
        )
        run_id = runs.create(
            calendar=CALENDAR,
            window_start='2026-09-01',
            window_end='2026-10-01'
        ).id
        for _number in range(1, 4):
            revisions.create(run_id=run_id)
        monkeypatch.undo()
        revisions.create(run_id=run_id)

        sweep(connection=connection)

        assert len(revisions.list_all(run_id=run_id)) == 4

    def test_the_events_in_one_go_with_it(
        self,
        collected: Any,
        connection: sqlite3.Connection,
        events: Any,
        revisions: RevisionRepository,
        run_id: str
    ) -> None:
        # The database removes them, which is worth a test because it
        # is the difference between forgetting a revision and leaving
        # the calendar text that was in it behind.
        del collected
        revisions.create(run_id=run_id)
        revisions.create(run_id=run_id)

        sweep(connection=connection, now=later(days=200))

        assert events.list_all(run_id=run_id, revision=2) == []


class TestWhichUnmatchedTitlesAreKept:
    def test_one_the_model_now_matches_is_forgotten(
        self,
        connection: sqlite3.Connection,
        unmatched: UnmatchedTitleRepository
    ) -> None:
        # Which is what recording it was for. Once the model matches
        # it, the row is a person's name kept for no reason.
        unmatched.record(
            calendar=CALENDAR,
            title=MATCHED_TITLE,
            principal_id=SOMEBODY
        )

        sweep(connection=connection)

        assert unmatched.list_all() == []

    def test_one_it_still_does_not_match_is_kept(
        self,
        connection: sqlite3.Connection,
        unmatched: UnmatchedTitleRepository
    ) -> None:
        unmatched.record(
            calendar=CALENDAR,
            title=UNMATCHED_TITLE,
            principal_id=SOMEBODY
        )

        sweep(connection=connection)

        assert len(unmatched.list_all()) == 1

    def test_until_nothing_has_seen_it_for_a_year(
        self,
        connection: sqlite3.Connection,
        unmatched: UnmatchedTitleRepository
    ) -> None:
        unmatched.record(
            calendar=CALENDAR,
            title=UNMATCHED_TITLE,
            principal_id=SOMEBODY
        )

        sweep(connection=connection, now=later(days=400))

        assert unmatched.list_all() == []

    def test_a_title_is_forgotten_whole(
        self,
        connection: sqlite3.Connection,
        other_run_id: str,
        run_id: str,
        unmatched: UnmatchedTitleRepository
    ) -> None:
        # Never sighting by sighting: the count means the runs a title
        # turned up in, so a title that kept some of its rows would
        # report a smaller number rather than nothing, and a smaller
        # number reads as a title that has stopped recurring.
        for each in (run_id, other_run_id):
            unmatched.record(
                calendar=CALENDAR,
                title=MATCHED_TITLE,
                run_id=each,
                principal_id=SOMEBODY
            )

        swept = sweep(connection=connection)

        assert swept.unmatched_titles == 2
        assert unmatched.list_all() == []

    def test_the_backstop_reads_the_most_recent_sighting(
        self,
        connection: sqlite3.Connection,
        monkeypatch: pytest.MonkeyPatch,
        other_run_id: str,
        run_id: str,
        unmatched: UnmatchedTitleRepository
    ) -> None:
        # Measured per row, a title still turning up would quietly
        # lose its early sightings and report a smaller count, which
        # is the opposite of what is true of it.
        long_ago = (
            datetime.now(timezone.utc) - timedelta(days=400)
        ).isoformat(timespec='seconds')
        monkeypatch.setattr(
            'star_pass._repository._unmatched.utc_now',
            lambda: long_ago
        )
        unmatched.record(
            calendar=CALENDAR,
            title=UNMATCHED_TITLE,
            run_id=run_id,
            principal_id=SOMEBODY
        )
        monkeypatch.undo()
        unmatched.record(
            calendar=CALENDAR,
            title=UNMATCHED_TITLE,
            run_id=other_run_id,
            principal_id=SOMEBODY
        )

        sweep(connection=connection)

        assert unmatched.list_all()[0].times_seen == 2


class TestWhichReservationsAreKept:
    def test_a_reservation_with_no_response_is_forgotten(
        self,
        connection: sqlite3.Connection,
        run_id: str
    ) -> None:
        # Its process died between claiming the key and recording
        # what the write answered, so every replay of that key is
        # told the first request is still running.
        keys = IdempotencyRepository(connection=connection)
        keys.reserve(
            operation=OPERATION_EDIT,
            key='abandoned',
            run_id=run_id,
            fingerprint='op=nudge',
            principal_id=SOMEBODY
        )

        sweep(
            connection=connection,
            now=hours_later(
                _defaults.RETENTION_ABANDONED_KEY_HOURS + 1
            )
        )

        assert keys.get(
            operation=OPERATION_EDIT, key='abandoned'
        ) is None

    def test_a_reservation_that_answered_is_kept(
        self,
        connection: sqlite3.Connection,
        run_id: str
    ) -> None:
        # It is what a replay is answered from.
        keys = IdempotencyRepository(connection=connection)
        keys.reserve(
            operation=OPERATION_EDIT,
            key='answered',
            run_id=run_id,
            fingerprint='op=nudge',
            principal_id=SOMEBODY
        )
        keys.complete(
            operation=OPERATION_EDIT,
            key='answered',
            status_code=200,
            response={'ok': True}
        )

        sweep(
            connection=connection,
            now=hours_later(
                _defaults.RETENTION_ABANDONED_KEY_HOURS + 1
            )
        )

        assert keys.get(
            operation=OPERATION_EDIT, key='answered'
        ) is not None

    def test_a_reservation_inside_the_window_is_kept(
        self,
        connection: sqlite3.Connection,
        run_id: str
    ) -> None:
        # A write still running holds no response either, and the
        # window is what tells the two apart.
        keys = IdempotencyRepository(connection=connection)
        keys.reserve(
            operation=OPERATION_EDIT,
            key='running',
            run_id=run_id,
            fingerprint='op=nudge',
            principal_id=SOMEBODY
        )

        sweep(connection=connection, now=hours_later(1))

        assert keys.get(
            operation=OPERATION_EDIT, key='running'
        ) is not None


class TestWhatIsNeverForgotten:
    def test_the_record_of_what_a_send_created(
        self,
        connection: sqlite3.Connection,
        run_id: str,
        sent: SentShiftRepository,
        shift_identity: ShiftIdentity
    ) -> None:
        # Duplicate safety reads it. A window here would eventually
        # have a run offering to create shifts Amplify already holds.
        sent.record(
            run_id=run_id,
            identities=[shift_identity],
            principal_id=SOMEBODY,
            idempotency_key='a-send-request'
        )

        sweep(connection=connection, now=later(days=4000))

        assert len(sent.list_for_run(run_id=run_id)) == 1


class TestWhatASweepReports:
    def test_nothing_removed_is_falsy(
        self,
        connection: sqlite3.Connection
    ) -> None:
        assert not sweep(connection=connection)

    def test_something_removed_is_truthy(
        self,
        connection: sqlite3.Connection,
        finished_job: str
    ) -> None:
        del finished_job

        assert sweep(connection=connection, now=later(days=200))

    def test_forgetting_only_a_title_still_counts_as_something(
        self,
        connection: sqlite3.Connection,
        unmatched: UnmatchedTitleRepository
    ) -> None:
        # Each of the three has to reach the answer on its own, or a
        # sweep whose only work was forgetting a person's name would
        # report that it had done nothing.
        unmatched.record(
            calendar=CALENDAR,
            title=MATCHED_TITLE,
            principal_id=SOMEBODY
        )

        assert sweep(connection=connection)

    def test_the_counts_are_what_was_removed(
        self,
        connection: sqlite3.Connection,
        finished_job: str,
        sealed: List[int]
    ) -> None:
        del finished_job, sealed

        swept = sweep(connection=connection, now=later(days=200))

        assert swept == Swept(
            job_events=1,
            revisions=2,
            unmatched_titles=0
        )


class TestTheWindowsAreConfigurable:
    def test_a_shorter_job_log_window_takes_effect(
        self,
        connection: sqlite3.Connection,
        finished_job: str,
        jobs: JobRepository,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A deployment whose policy differs changes a setting rather
        # than the code (D12).
        monkeypatch.setattr(_defaults, 'RETENTION_JOB_LOG_DAYS', 1)

        sweep(connection=connection, now=later(days=2))

        assert jobs.events(job_id=finished_job) == []
