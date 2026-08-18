#!/usr/bin/env python3
""" Sealing the revision a run is working in.

    An edit changes a revision in place, so what a reviewer has at any
    moment is only recoverable if something fixed it first.  These
    tests pin what sealing leaves behind, which is the half of
    reverting that has to be true before reverting is worth having.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
import sqlite3
from typing import Any, Callable

# Imports - Third-Party
import pytest

# Imports - Local
from star_pass._exceptions import ValidationError
from star_pass._records import Event
from star_pass._repository import EventRepository, RevisionRepository
from star_pass._revising import seal


@pytest.fixture(name='sealing')
def fixture_sealing(
    connection: sqlite3.Connection
) -> Callable[..., Any]:
    """ Return a way to seal one run's current revision. """

    def apply(run_id: str) -> Any:
        """ Seal it and return the revision that was opened. """
        return seal(connection=connection, run_id=run_id)

    return apply


class TestWhatSealingOpens:
    def test_the_next_revision_becomes_the_current_one(
        self,
        collected: str,
        runs: Any,
        sealing: Callable[..., Any]
    ) -> None:
        opened = sealing(collected)

        assert opened.number == 2
        assert runs.get(run_id=collected).current_revision == 2

    def test_it_holds_a_copy_of_what_was_sealed(
        self,
        collected: str,
        events: EventRepository,
        sealing: Callable[..., Any]
    ) -> None:
        # Sealing marks where the work has got to. The work carries
        # on in the revision it opened, so that revision starts as
        # what the reviewer was looking at.
        opened = sealing(collected)

        assert [
            event.id
            for event in events.list_all(
                run_id=collected,
                revision=opened.number
            )
        ] == ['event-1']

    def test_it_says_which_revision_it_continues_from(
        self,
        collected: str,
        sealing: Callable[..., Any]
    ) -> None:
        assert sealing(collected).label == 'Continued from revision 1'


class TestWhatSealingLeavesAlone:
    def test_the_sealed_revision_keeps_its_events(
        self,
        collected: str,
        events: EventRepository,
        make_event: Callable[..., Event],
        sealing: Callable[..., Any]
    ) -> None:
        # Which is the whole point: what a revision held is still
        # there to go back to after the work has moved on.
        sealing(collected)
        events.add(
            run_id=collected,
            revision=2,
            event=make_event(id='event-2')
        )

        assert [
            event.id
            for event in events.list_all(run_id=collected, revision=1)
        ] == ['event-1']

    def test_nothing_is_written_to_the_change_log(
        self,
        change_log: Any,
        collected: str,
        sealing: Callable[..., Any]
    ) -> None:
        # The change count on a revision is what was done while it was
        # current, so an entry written as one opens would have every
        # sealed revision starting at a change nobody made. Who sealed
        # it is recorded against the key instead (D13).
        sealing(collected)

        assert change_log.list_all(run_id=collected) == []

    def test_the_revisions_before_it_are_all_still_there(
        self,
        collected: str,
        revisions: RevisionRepository,
        sealing: Callable[..., Any]
    ) -> None:
        sealing(collected)
        sealing(collected)

        assert [
            revision.number
            for revision in revisions.list_all(run_id=collected)
        ] == [1, 2, 3]


class TestWhatCannotBeSealed:
    def test_a_run_that_has_collected_nothing_is_refused(
        self,
        run_id: str,
        sealing: Callable[..., Any]
    ) -> None:
        # The first revision belongs to the collection, which labels
        # it for what filled it.
        with pytest.raises(ValidationError) as error:
            sealing(run_id)

        assert 'collected nothing' in str(error.value)

    def test_a_refused_run_gains_no_revision(
        self,
        revisions: RevisionRepository,
        run_id: str,
        sealing: Callable[..., Any]
    ) -> None:
        with pytest.raises(ValidationError):
            sealing(run_id)

        assert revisions.list_all(run_id=run_id) == []

    def test_an_unknown_run_is_reported_as_nothing(
        self,
        sealing: Callable[..., Any]
    ) -> None:
        # A run that is not there is the caller's to report, because
        # what it means depends on how it was asked for.
        assert sealing('no-such-run') is None


class TestWhatIsLogged:
    def test_the_seal_reaches_the_log(
        self,
        caplog: pytest.LogCaptureFixture,
        collected: str,
        sealing: Callable[..., Any]
    ) -> None:
        sealing(collected)

        assert collected in caplog.text

    def test_a_refusal_reaches_the_log(
        self,
        caplog: pytest.LogCaptureFixture,
        run_id: str,
        sealing: Callable[..., Any]
    ) -> None:
        with pytest.raises(ValidationError):
            sealing(run_id)

        assert 'collected nothing' in caplog.text
