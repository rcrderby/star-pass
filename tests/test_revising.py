#!/usr/bin/env python3
""" Sealing the revision a run is working in, and going back to one.

    An edit changes a revision in place, so what a reviewer has at any
    moment is only recoverable if something fixed it first.  Sealing
    is what fixes it; reverting is what going back to it means.

    Two things these pin that nothing else can: that a revert adds one
    revision rather than sealing and then reverting, and that going
    back to the revision a collection filled drops the events somebody
    pulled in by hand.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
import sqlite3
from typing import Any, Callable

# Imports - Third-Party
import pytest

# Imports - Local
from star_pass._exceptions import ValidationError
from star_pass._records import (
    Event,
    REVISION_CONTINUED,
    REVISION_REVERTED
)
from star_pass._repository import EventRepository, RevisionRepository
from star_pass._revising import revert, seal


@pytest.fixture(name='sealing')
def fixture_sealing(
    connection: sqlite3.Connection
) -> Callable[..., Any]:
    """ Return a way to seal one run's current revision. """

    def apply(run_id: str) -> Any:
        """ Seal it and return the revision that was opened. """
        return seal(connection=connection, run_id=run_id)

    return apply


@pytest.fixture(name='reverting')
def fixture_reverting(
    connection: sqlite3.Connection
) -> Callable[..., Any]:
    """ Return a way to take one run back to an earlier revision. """

    def apply(run_id: str, number: int) -> Any:
        """ Go back to it and return the revision that was opened. """
        return revert(
            connection=connection,
            run_id=run_id,
            number=number
        )

    return apply


@pytest.fixture(name='pulled_in')
def fixture_pulled_in(
    events: EventRepository,
    make_event: Callable[..., Event]
) -> Callable[..., None]:
    """ Return a way to put a hand-added event into a revision.

        Written straight into the revision rather than through the
        operation that pulls one in: what these tests ask about is
        what happens to such an event afterwards, and arranging it the
        long way would make the calendar and the search part of the
        arrangement.
    """

    def add(run_id: str, revision: int) -> None:
        """ Add one event, marked as somebody having pulled it in. """
        events.add(
            run_id=run_id,
            revision=revision,
            event=make_event(id='event-2', added_by_hand=True)
        )

    return add


@pytest.fixture(name='numbers')
def fixture_numbers(
    revisions: RevisionRepository
) -> Callable[[str], Any]:
    """ Return a way to read the revisions a run has been through. """

    def listed(run_id: str) -> Any:
        """ Return their numbers, oldest first. """
        return [
            revision.number
            for revision in revisions.list_all(run_id=run_id)
        ]

    return listed


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
        opened = sealing(collected)

        assert opened.kind == REVISION_CONTINUED
        assert opened.source_revision == 1


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
        # it is recorded against the key instead.
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


class TestWhatRevertingOpens:
    def test_it_holds_what_the_revision_reverted_to_held(
        self,
        collected: str,
        events: EventRepository,
        pulled_in: Callable[..., None],
        reverting: Callable[..., Any],
        sealing: Callable[..., Any]
    ) -> None:
        # Revision 2 is where the second event was added, so going
        # back to revision 1 is asking for the run without it.
        sealing(collected)
        pulled_in(collected, 2)

        opened = reverting(collected, 1)

        assert [
            event.id
            for event in events.list_all(
                run_id=collected,
                revision=opened.number
            )
        ] == ['event-1']

    def test_it_becomes_the_revision_the_run_is_working_in(
        self,
        collected: str,
        reverting: Callable[..., Any],
        runs: Any,
        sealing: Callable[..., Any]
    ) -> None:
        sealing(collected)

        opened = reverting(collected, 1)

        assert opened.number == 3
        assert runs.get(run_id=collected).current_revision == 3

    def test_it_says_which_revision_it_went_back_to(
        self,
        collected: str,
        reverting: Callable[..., Any],
        sealing: Callable[..., Any]
    ) -> None:
        sealing(collected)
        sealing(collected)

        opened = reverting(collected, 2)

        assert opened.kind == REVISION_REVERTED
        assert opened.source_revision == 2


class TestHowManyRevisionsARevertAdds:
    def test_one(
        self,
        collected: str,
        numbers: Callable[[str], Any],
        reverting: Callable[..., Any],
        sealing: Callable[..., Any]
    ) -> None:
        # The decision this pins: nothing a revert does is
        # destructive, so the revision it leaves is already safe at
        # its own number and sealing it first would add a second
        # revision holding an identical copy of it.
        sealing(collected)

        reverting(collected, 1)

        assert numbers(collected) == [1, 2, 3]

    def test_the_revision_it_left_keeps_its_events(
        self,
        collected: str,
        events: EventRepository,
        pulled_in: Callable[..., None],
        reverting: Callable[..., Any]
    ) -> None:
        # Which is what makes a revert something that can itself be
        # reverted: what was on the screen is still readable at the
        # number it was under.
        pulled_in(collected, 1)

        reverting(collected, 1)

        assert [
            event.id
            for event in events.list_all(run_id=collected, revision=1)
        ] == ['event-1', 'event-2']

    def test_nothing_is_written_to_the_change_log(
        self,
        change_log: Any,
        collected: str,
        reverting: Callable[..., Any]
    ) -> None:
        # For the reason sealing writes none: the count on a revision
        # is what was done while it was current, and who reverted is
        # recorded against the key instead.
        reverting(collected, 1)

        assert change_log.list_all(run_id=collected) == []


class TestTheEventsSomebodyPulledIn:
    def test_going_back_to_the_collection_drops_them(
        self,
        collected: str,
        events: EventRepository,
        pulled_in: Callable[..., None],
        reverting: Callable[..., Any]
    ) -> None:
        # Revision 1 is the run as the calendar gave it, so an event
        # somebody pulled in is not part of what it holds -- and the
        # row saying the collection left it out was never deleted, so
        # dropping it here is what offers it again.
        pulled_in(collected, 1)

        opened = reverting(collected, 1)

        assert [
            event.id
            for event in events.list_all(
                run_id=collected,
                revision=opened.number
            )
        ] == ['event-1']

    def test_going_back_to_a_later_revision_keeps_them(
        self,
        collected: str,
        events: EventRepository,
        pulled_in: Callable[..., None],
        reverting: Callable[..., Any],
        sealing: Callable[..., Any]
    ) -> None:
        # A later revision holds whatever it held, hand-added or not:
        # what is being asked for is that revision, not the calendar.
        sealing(collected)
        pulled_in(collected, 2)
        sealing(collected)

        opened = reverting(collected, 2)

        assert [
            event.id
            for event in events.list_all(
                run_id=collected,
                revision=opened.number
            )
        ] == ['event-1', 'event-2']

    def test_their_roles_go_with_them(
        self,
        collected: str,
        events: EventRepository,
        pulled_in: Callable[..., None],
        reverting: Callable[..., Any]
    ) -> None:
        # A role left behind would be a row pointing at an event the
        # revision no longer holds.
        pulled_in(collected, 1)

        opened = reverting(collected, 1)

        assert [
            role.need_id
            for event in events.list_all(
                run_id=collected,
                revision=opened.number
            )
            for role in event.roles
        ] == ['905196']


class TestWhatCannotBeRevertedTo:
    def test_a_revision_the_run_has_never_had_is_refused(
        self,
        collected: str,
        reverting: Callable[..., Any]
    ) -> None:
        with pytest.raises(ValidationError) as error:
            reverting(collected, 4)

        assert 'no revision 4' in str(error.value)

    def test_a_refused_run_gains_no_revision(
        self,
        collected: str,
        numbers: Callable[[str], Any],
        reverting: Callable[..., Any]
    ) -> None:
        with pytest.raises(ValidationError):
            reverting(collected, 4)

        assert numbers(collected) == [1]

    def test_a_run_that_has_collected_nothing_has_nowhere_to_go_back_to(
        self,
        reverting: Callable[..., Any],
        run_id: str
    ) -> None:
        with pytest.raises(ValidationError) as error:
            reverting(run_id, 1)

        assert 'no revision 1' in str(error.value)

    def test_an_unknown_run_is_reported_as_nothing(
        self,
        reverting: Callable[..., Any]
    ) -> None:
        # For the reason sealing reports one that way: what a missing
        # run means depends on how it was asked for.
        assert reverting('no-such-run', 1) is None


class TestWhatARevertLogs:
    def test_the_revision_it_went_back_to_reaches_the_log(
        self,
        caplog: pytest.LogCaptureFixture,
        collected: str,
        reverting: Callable[..., Any],
        sealing: Callable[..., Any]
    ) -> None:
        sealing(collected)

        reverting(collected, 1)

        assert 'to revision 1' in caplog.text

    def test_a_refusal_reaches_the_log(
        self,
        caplog: pytest.LogCaptureFixture,
        collected: str,
        reverting: Callable[..., Any]
    ) -> None:
        with pytest.raises(ValidationError):
            reverting(collected, 4)

        assert 'no revision 4' in caplog.text
