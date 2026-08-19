#!/usr/bin/env python3
""" Tests for the repository layer. """

# pylint: disable=missing-function-docstring,missing-class-docstring
# pylint: disable=too-many-arguments,too-many-positional-arguments

# Imports - Python Standard Library
import sqlite3
from typing import Callable

# Imports - Third-Party
import pytest

# Imports - Local
from star_pass._database import query
from star_pass._exceptions import UpstreamError, ValidationError
from star_pass._records import (
    Event,
    EventRole,
    Match,
    Opportunity,
    REVISION_COLLECTED,
    RUN_STATUS_COLLECTING
)
from star_pass._repository import (
    ChangeLogRepository,
    EventRepository,
    RevisionRepository,
    RunRepository
)
from star_pass._repository._common import copy_statement, insert_statement


class TestRuns:
    def test_a_new_run_is_stored_with_a_minted_id(
        self,
        runs: RunRepository
    ) -> None:
        run = runs.create(
            calendar='events',
            window_start='2026-09-01',
            window_end='2026-10-01'
        )

        assert run.id
        assert runs.get(run_id=run.id) == run

    def test_ids_are_not_reused_between_runs(
        self,
        runs: RunRepository
    ) -> None:
        first = runs.create(
            calendar='events',
            window_start='2026-09-01',
            window_end='2026-10-01'
        )
        second = runs.create(
            calendar='events',
            window_start='2026-09-01',
            window_end='2026-10-01'
        )

        assert first.id != second.id

    def test_a_new_run_is_collecting_with_no_revision(
        self,
        runs: RunRepository,
        run_id: str
    ) -> None:
        run = runs.get(run_id=run_id)

        assert run.status == RUN_STATUS_COLLECTING
        assert run.current_revision == 0
        assert run.sent_at is None

    def test_a_new_run_was_last_revised_when_it_was_collected(
        self,
        runs: RunRepository,
        run_id: str
    ) -> None:
        run = runs.get(run_id=run_id)

        assert run.revised_at == run.collected_at

    def test_an_unknown_run_reads_as_nothing(
        self,
        runs: RunRepository
    ) -> None:
        assert runs.get(run_id='no-such-run') is None

    def test_runs_are_listed_newest_first(
        self,
        runs: RunRepository,
        connection: sqlite3.Connection
    ) -> None:
        older = runs.create(
            calendar='events',
            window_start='2026-08-01',
            window_end='2026-09-01'
        )
        newer = runs.create(
            calendar='practices',
            window_start='2026-09-01',
            window_end='2026-10-01'
        )
        # The two are created in the same second, so the stored time
        # cannot order them on its own.
        connection.execute(
            "UPDATE runs SET collected_at = '2026-01-01T00:00:00+00:00' "
            'WHERE id = ?',
            (older.id,)
        )

        assert [run.id for run in runs.list_all()] == [newer.id, older.id]

    def test_a_status_is_recorded(
        self,
        runs: RunRepository,
        run_id: str
    ) -> None:
        runs.set_status(run_id=run_id, status='unsent')

        assert runs.get(run_id=run_id).status == 'unsent'

    def test_a_send_time_is_recorded_with_the_status(
        self,
        runs: RunRepository,
        run_id: str
    ) -> None:
        runs.set_status(
            run_id=run_id,
            status='sent',
            sent_at='2026-09-02T01:00:00+00:00'
        )

        assert runs.get(run_id=run_id).sent_at == '2026-09-02T01:00:00+00:00'

    def test_a_later_status_keeps_the_send_time(
        self,
        runs: RunRepository,
        run_id: str
    ) -> None:
        # Nothing un-sends a run, so a status set without a send time
        # must not erase the one already recorded.
        runs.set_status(
            run_id=run_id,
            status='sent',
            sent_at='2026-09-02T01:00:00+00:00'
        )
        runs.set_status(run_id=run_id, status='partly_sent')

        assert runs.get(run_id=run_id).sent_at == '2026-09-02T01:00:00+00:00'

    def test_an_unknown_status_is_refused(
        self,
        runs: RunRepository,
        run_id: str
    ) -> None:
        with pytest.raises(ValidationError) as error:
            runs.set_status(run_id=run_id, status='finished')

        assert 'is not a run status' in str(error.value)

    def test_a_status_for_an_unknown_run_is_refused(
        self,
        runs: RunRepository
    ) -> None:
        with pytest.raises(ValidationError) as error:
            runs.set_status(run_id='no-such-run', status='unsent')

        assert 'no run with the ID' in str(error.value)


class TestOpportunities:
    def test_opportunities_are_stored_with_the_run(
        self,
        runs: RunRepository,
        run_id: str,
        make_opportunity: Callable[..., Opportunity]
    ) -> None:
        opportunity = make_opportunity()
        runs.set_opportunities(
            run_id=run_id,
            opportunities=[opportunity]
        )

        assert runs.get_opportunities(run_id=run_id) == [opportunity]

    def test_opportunities_replace_the_previous_set(
        self,
        runs: RunRepository,
        run_id: str,
        make_opportunity: Callable[..., Opportunity]
    ) -> None:
        # They are read from Amplify together, so one that disappeared
        # between reads has to disappear here too.
        runs.set_opportunities(
            run_id=run_id,
            opportunities=[
                make_opportunity(need_id='111111'),
                make_opportunity(need_id='222222')
            ]
        )
        runs.set_opportunities(
            run_id=run_id,
            opportunities=[make_opportunity(need_id='222222')]
        )

        stored = runs.get_opportunities(run_id=run_id)

        assert [item.need_id for item in stored] == ['222222']

    def test_an_opportunity_without_a_maximum_is_stored(
        self,
        runs: RunRepository,
        run_id: str,
        make_opportunity: Callable[..., Opportunity]
    ) -> None:
        runs.set_opportunities(
            run_id=run_id,
            opportunities=[make_opportunity(max_length=None)]
        )

        assert runs.get_opportunities(run_id=run_id)[0].max_length is None

    def test_opportunities_need_a_run_that_exists(
        self,
        runs: RunRepository,
        make_opportunity: Callable[..., Opportunity]
    ) -> None:
        with pytest.raises(ValidationError):
            runs.set_opportunities(
                run_id='no-such-run',
                opportunities=[make_opportunity()]
            )


class TestRevisions:
    def test_the_first_revision_is_numbered_one_and_is_empty(
        self,
        revisions: RevisionRepository,
        events: EventRepository,
        run_id: str
    ) -> None:
        revision = revisions.create(run_id=run_id, replacing=True)

        assert revision.number == 1
        assert events.list_all(run_id=run_id, revision=1) == []

    def test_a_revision_becomes_the_run_current_one(
        self,
        runs: RunRepository,
        revisions: RevisionRepository,
        run_id: str
    ) -> None:
        revisions.create(run_id=run_id, replacing=True)
        revisions.create(run_id=run_id)

        assert runs.get(run_id=run_id).current_revision == 2

    def test_a_revision_copies_the_events_of_the_one_before_it(
        self,
        revisions: RevisionRepository,
        events: EventRepository,
        collected: str
    ) -> None:
        revisions.create(run_id=collected)

        copied = events.list_all(run_id=collected, revision=2)

        assert copied == events.list_all(run_id=collected, revision=1)

    def test_editing_a_revision_leaves_the_earlier_one_alone(
        self,
        events: EventRepository,
        edited: str
    ) -> None:
        first = events.list_all(run_id=edited, revision=1)[0]
        second = events.list_all(run_id=edited, revision=2)[0]

        assert first.shift_start == '19:15'
        assert second.shift_start == '19:45'

    def test_revisions_are_listed_oldest_first(
        self,
        revisions: RevisionRepository,
        run_id: str
    ) -> None:
        revisions.create(run_id=run_id, replacing=True)
        revisions.create(run_id=run_id)

        listed = revisions.list_all(run_id=run_id)

        assert [item.number for item in listed] == [1, 2]

    def test_a_revision_reads_back_by_number(
        self,
        revisions: RevisionRepository,
        run_id: str,
        revision: int
    ) -> None:
        assert revisions.get(
            run_id=run_id,
            number=revision
        ).kind == REVISION_COLLECTED

    def test_an_unknown_revision_reads_as_nothing(
        self,
        revisions: RevisionRepository,
        run_id: str
    ) -> None:
        assert revisions.get(run_id=run_id, number=9) is None

    def test_reverting_adds_a_copy_rather_than_deleting(
        self,
        revisions: RevisionRepository,
        events: EventRepository,
        edited: str
    ) -> None:
        reverted = revisions.revert_to(run_id=edited, number=1)
        listed = revisions.list_all(run_id=edited)

        assert reverted.number == 3
        assert [item.number for item in listed] == [1, 2, 3]
        assert events.list_all(
            run_id=edited,
            revision=3
        )[0].shift_start == '19:15'

    def test_reverting_to_an_unknown_revision_is_refused(
        self,
        revisions: RevisionRepository,
        run_id: str,
        revision: int
    ) -> None:
        with pytest.raises(ValidationError) as error:
            revisions.revert_to(run_id=run_id, number=revision + 5)

        assert 'no revision' in str(error.value)

    def test_deleting_a_revision_takes_its_events_with_it(
        self,
        revisions: RevisionRepository,
        events: EventRepository,
        connection: sqlite3.Connection,
        run_id: str,
        revision: int,
        make_event: Callable[..., Event]
    ) -> None:
        events.add(
            run_id=run_id,
            revision=revision,
            event=make_event()
        )
        revisions.delete(run_id=run_id, number=revision)

        assert events.list_all(run_id=run_id, revision=revision) == []
        assert query(
            connection=connection,
            statement='SELECT * FROM event_roles'
        ) == []


class TestEvents:
    def test_an_event_reads_back_with_its_roles(
        self,
        events: EventRepository,
        run_id: str,
        revision: int,
        make_event: Callable[..., Event]
    ) -> None:
        event = make_event(
            roles=(
                EventRole(need_id='111111', slots=4),
                EventRole(need_id='222222', slots=2, edited=True)
            )
        )
        events.add(run_id=run_id, revision=revision, event=event)

        assert events.get(
            run_id=run_id,
            revision=revision,
            event_id=event.id
        ) == event

    def test_a_match_reads_back_whole(
        self,
        events: EventRepository,
        run_id: str,
        revision: int,
        make_event: Callable[..., Event]
    ) -> None:
        event = make_event(
            match=Match(kind='fuzzy', score=87)
        )
        events.add(run_id=run_id, revision=revision, event=event)

        stored = events.get(
            run_id=run_id,
            revision=revision,
            event_id=event.id
        )

        assert stored.match == Match(kind='fuzzy', keyword=None, score=87)

    def test_an_unmatched_event_has_no_match(
        self,
        events: EventRepository,
        run_id: str,
        revision: int,
        make_event: Callable[..., Event]
    ) -> None:
        event = make_event(category=None)
        events.add(run_id=run_id, revision=revision, event=event)

        stored = events.get(
            run_id=run_id,
            revision=revision,
            event_id=event.id
        )

        assert stored.match is None
        assert stored.category is None

    def test_an_event_added_by_hand_stays_distinguishable(
        self,
        events: EventRepository,
        run_id: str,
        revision: int,
        make_event: Callable[..., Event]
    ) -> None:
        # Reverting to the first revision drops them, so the flag has
        # to survive a write and a read.
        events.add(
            run_id=run_id,
            revision=revision,
            event=make_event(added_by_hand=True)
        )

        assert events.list_all(
            run_id=run_id,
            revision=revision
        )[0].added_by_hand is True

    def test_events_are_listed_in_the_order_they_happen(
        self,
        events: EventRepository,
        run_id: str,
        revision: int,
        make_event: Callable[..., Event]
    ) -> None:
        events.add_all(
            run_id=run_id,
            revision=revision,
            events=(
                make_event(
                    id='later',
                    date='2026-09-04',
                    shift_start='18:00'
                ),
                make_event(
                    id='earlier-same-day',
                    date='2026-09-03',
                    shift_start='17:00'
                ),
                make_event(id='first', date='2026-09-03', shift_start='09:00')
            )
        )

        listed = events.list_all(run_id=run_id, revision=revision)

        assert [event.id for event in listed] == [
            'first',
            'earlier-same-day',
            'later'
        ]

    def test_an_unknown_event_reads_as_nothing(
        self,
        events: EventRepository,
        run_id: str,
        revision: int
    ) -> None:
        assert events.get(
            run_id=run_id,
            revision=revision,
            event_id='no-such-event'
        ) is None

    def test_replacing_an_event_rewrites_its_roles(
        self,
        events: EventRepository,
        run_id: str,
        revision: int,
        make_event: Callable[..., Event]
    ) -> None:
        events.add(
            run_id=run_id,
            revision=revision,
            event=make_event(
                roles=(EventRole(need_id='111111', slots=4),)
            )
        )
        events.replace(
            run_id=run_id,
            revision=revision,
            event=make_event(
                roles=(EventRole(need_id='222222', slots=6, edited=True),)
            )
        )

        stored = events.list_all(run_id=run_id, revision=revision)[0]

        assert stored.roles == (
            EventRole(need_id='222222', slots=6, edited=True),
        )

    def test_replacing_an_unknown_event_is_refused(
        self,
        events: EventRepository,
        run_id: str,
        revision: int,
        make_event: Callable[..., Event]
    ) -> None:
        with pytest.raises(ValidationError) as error:
            events.replace(
                run_id=run_id,
                revision=revision,
                event=make_event(id='no-such-event')
            )

        assert 'no event' in str(error.value)

    def test_removing_an_event_takes_its_roles_with_it(
        self,
        events: EventRepository,
        connection: sqlite3.Connection,
        run_id: str,
        revision: int,
        make_event: Callable[..., Event]
    ) -> None:
        event = make_event()
        events.add(run_id=run_id, revision=revision, event=event)
        events.remove(
            run_id=run_id,
            revision=revision,
            event_id=event.id
        )

        assert events.list_all(run_id=run_id, revision=revision) == []
        assert query(
            connection=connection,
            statement='SELECT * FROM event_roles'
        ) == []

    def test_removing_an_unknown_event_is_refused(
        self,
        events: EventRepository,
        run_id: str,
        revision: int
    ) -> None:
        with pytest.raises(ValidationError) as error:
            events.remove(
                run_id=run_id,
                revision=revision,
                event_id='no-such-event'
            )

        assert 'no event' in str(error.value)

    def test_an_event_needs_a_revision_that_exists(
        self,
        events: EventRepository,
        run_id: str,
        make_event: Callable[..., Event]
    ) -> None:
        with pytest.raises(ValidationError):
            events.add(
                run_id=run_id,
                revision=99,
                event=make_event()
            )

    def test_an_event_id_is_used_once_per_revision(
        self,
        events: EventRepository,
        run_id: str,
        revision: int,
        make_event: Callable[..., Event]
    ) -> None:
        events.add(
            run_id=run_id,
            revision=revision,
            event=make_event()
        )

        with pytest.raises(ValidationError):
            events.add(
                run_id=run_id,
                revision=revision,
                event=make_event()
            )

    def test_a_failed_batch_adds_nothing(
        self,
        events: EventRepository,
        run_id: str,
        revision: int,
        make_event: Callable[..., Event]
    ) -> None:
        # The second event repeats the first one's ID, so the batch is
        # refused; a half-written revision would be worse than none.
        with pytest.raises(ValidationError):
            events.add_all(
                run_id=run_id,
                revision=revision,
                events=(
                    make_event(id='same'),
                    make_event(id='same', shift_start='20:00')
                )
            )

        assert events.list_all(run_id=run_id, revision=revision) == []


class TestChangeLog:
    def test_an_entry_reads_back_with_who_made_it(
        self,
        change_log: ChangeLogRepository,
        run_id: str,
        revision: int
    ) -> None:
        entry = change_log.add(
            run_id=run_id,
            revision=revision,
            principal_id='static-token',
            entry='Start moved to 7:45 pm'
        )

        assert change_log.list_all(run_id=run_id) == [entry]
        assert entry.principal_id == 'static-token'

    def test_entries_keep_the_order_they_were_written_in(
        self,
        change_log: ChangeLogRepository,
        run_id: str,
        revision: int
    ) -> None:
        # Entries made in the same second are ordered by identifier,
        # because the timestamp cannot separate them.
        for text in ('first', 'second', 'third'):
            change_log.add(
                run_id=run_id,
                revision=revision,
                principal_id='static-token',
                entry=text
            )

        listed = change_log.list_all(run_id=run_id)

        assert [item.entry for item in listed] == [
            'first',
            'second',
            'third'
        ]

    def test_a_log_entry_dates_the_run(
        self,
        runs: RunRepository,
        change_log: ChangeLogRepository,
        run_id: str,
        revision: int
    ) -> None:
        entry = change_log.add(
            run_id=run_id,
            revision=revision,
            principal_id='static-token',
            entry='Slots raised to six'
        )

        assert runs.get(run_id=run_id).revised_at == entry.logged_at

    def test_an_entry_needs_a_run_that_exists(
        self,
        change_log: ChangeLogRepository
    ) -> None:
        with pytest.raises(ValidationError):
            change_log.add(
                run_id='no-such-run',
                revision=1,
                principal_id='static-token',
                entry='Start moved'
            )

    def test_a_run_with_no_entries_has_an_empty_log(
        self,
        change_log: ChangeLogRepository,
        run_id: str
    ) -> None:
        assert change_log.list_all(run_id=run_id) == []


class TestDeletingARun:
    def test_deleting_a_run_removes_everything_below_it(
        self,
        runs: RunRepository,
        events: EventRepository,
        change_log: ChangeLogRepository,
        connection: sqlite3.Connection,
        run_id: str,
        revision: int
    ) -> None:
        change_log.add(
            run_id=run_id,
            revision=revision,
            principal_id='static-token',
            entry='Collected'
        )
        runs.delete(run_id=run_id)

        assert runs.get(run_id=run_id) is None
        assert events.list_all(run_id=run_id, revision=revision) == []
        assert change_log.list_all(run_id=run_id) == []
        assert query(
            connection=connection,
            statement='SELECT * FROM revisions'
        ) == []

    def test_deleting_an_unknown_run_is_not_an_error(
        self,
        runs: RunRepository
    ) -> None:
        # Retention deletes what is past its window; a run already gone
        # is the outcome it wanted.
        runs.delete(run_id='no-such-run')


class TestStatementBuilding:
    def test_a_statement_binds_every_value(self) -> None:
        statement = insert_statement(
            table='runs',
            columns=('id', 'calendar')
        )

        assert statement == (
            'INSERT INTO runs (id, calendar) VALUES (?, ?)'
        )

    def test_a_copy_replaces_only_the_revision(self) -> None:
        statement = copy_statement(
            table='events',
            columns=('run_id', 'revision', 'id')
        )

        assert statement == (
            'INSERT INTO events (run_id, revision, id) '
            'SELECT run_id, ?, id FROM events '
            'WHERE run_id = ? AND revision = ?'
        )

    @pytest.mark.parametrize(
        'name',
        (
            'runs; DROP TABLE runs',
            'runs WHERE 1=1',
            'Runs',
            '',
            'run-id'
        )
    )
    def test_a_name_that_is_not_an_identifier_is_refused(
        self,
        name: str
    ) -> None:
        # A table or column name cannot be a bound parameter, so it is
        # interpolated; nothing but a plain identifier may reach one.
        with pytest.raises(ValidationError):
            insert_statement(table=name, columns=('id',))

    def test_a_column_that_is_not_an_identifier_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            copy_statement(
                table='events',
                columns=('run_id', 'id = 1 OR 1=1')
            )


class TestAClosedConnection:
    def test_a_closed_connection_reports_upstream(
        self,
        runs: RunRepository,
        connection: sqlite3.Connection
    ) -> None:
        connection.close()

        with pytest.raises(UpstreamError):
            runs.list_all()
