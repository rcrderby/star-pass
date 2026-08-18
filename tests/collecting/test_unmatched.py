#!/usr/bin/env python3
""" The titles a collection found the data model had no match for.

    A collection is where the fact is discovered, so a collection is
    what writes it down: an event no category matched is stored under
    the fallback, whose need IDs are empty, and that is an event with
    no roles.  It stops the run being sent, which gets that run seen
    to; the log is what survives it, for the next edit of the model.

    What these pin above all is the count, because the count is what
    the log is read for.  A title is one sighting per run however many
    events carry it and however often the window is collected again --
    recollecting is how a corrected model is picked up, so a count
    that grew with every recollection would report an operator's own
    fixing as the title coming back.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
from typing import Any, Callable

# Imports - Third-Party
import pytest

# Imports - Local
from collecting._arranging import an_item, CALENDAR
from collecting.conftest import COLLECTED_BY
from star_pass._database import query
from star_pass._repository import RunRepository, UnmatchedTitleRepository

# Constants
# A title no category in the arranged model has an alias for.
UNMATCHED_TITLE = 'Quilting Circle Meetup'
OTHER_UNMATCHED_TITLE = 'Board Game Night'

# One the arranged model does match, so a collection storing it has
# roles to store with it.
MATCHED_TITLE = 'Wheels of Justice vs Rose City'


@pytest.fixture(name='recorded')
def fixture_recorded(
    unmatched: UnmatchedTitleRepository
) -> Callable[[], Any]:
    """ Return a way to read the log back, newest first. """

    def read() -> Any:
        """ Return every title recorded, as entries. """
        return unmatched.list_all()

    return read


class TestWhatACollectionWritesDown:
    def test_a_title_no_category_matched_is_recorded(
        self,
        collect_run: Callable[..., Any],
        recorded: Callable[[], Any]
    ) -> None:
        collect_run(items=[an_item(summary=UNMATCHED_TITLE)])

        assert [entry.title for entry in recorded()] == [UNMATCHED_TITLE]

    def test_it_is_recorded_against_the_calendar_it_was_seen_in(
        self,
        collect_run: Callable[..., Any],
        recorded: Callable[[], Any]
    ) -> None:
        # A title is only unmatched with respect to a model, and each
        # calendar has its own.
        collect_run(items=[an_item(summary=UNMATCHED_TITLE)])

        assert recorded()[0].calendar == CALENDAR

    def test_who_asked_for_the_collection_is_recorded(
        self,
        collect_run: Callable[..., Any],
        connection: Any
    ) -> None:
        # Read from the row rather than from what is published: the
        # entry a caller sees counts sightings, and D13 is about what
        # is stored against each one.
        collect_run(items=[an_item(summary=UNMATCHED_TITLE)])

        stored = query(
            connection=connection,
            statement='SELECT principal_id, run_id FROM unmatched_titles'
        )

        assert [row['principal_id'] for row in stored] == [COLLECTED_BY]

    def test_the_run_it_was_seen_in_is_recorded(
        self,
        collect_run: Callable[..., Any],
        collecting: str,
        connection: Any
    ) -> None:
        # Which is what holds a run to one sighting of a title.
        collect_run(items=[an_item(summary=UNMATCHED_TITLE)])

        stored = query(
            connection=connection,
            statement='SELECT run_id FROM unmatched_titles'
        )

        assert [row['run_id'] for row in stored] == [collecting]

    def test_a_title_the_model_matched_is_not_recorded(
        self,
        collect_run: Callable[..., Any],
        recorded: Callable[[], Any]
    ) -> None:
        collect_run(items=[an_item(summary=MATCHED_TITLE)])

        assert recorded() == []

    def test_each_unmatched_title_gets_its_own_entry(
        self,
        collect_run: Callable[..., Any],
        recorded: Callable[[], Any]
    ) -> None:
        collect_run(
            items=[
                an_item(summary=UNMATCHED_TITLE),
                an_item(
                    identifier='gcal-2',
                    summary=OTHER_UNMATCHED_TITLE
                )
            ]
        )

        assert sorted(entry.title for entry in recorded()) == sorted(
            (UNMATCHED_TITLE, OTHER_UNMATCHED_TITLE)
        )


class TestWhatTheCountMeasures:
    def test_a_window_holding_a_title_four_times_saw_it_once(
        self,
        collect_run: Callable[..., Any],
        recorded: Callable[[], Any]
    ) -> None:
        collect_run(
            items=[
                an_item(identifier=f'gcal-{number}', summary=UNMATCHED_TITLE)
                for number in range(1, 5)
            ]
        )

        assert recorded()[0].times_seen == 1

    def test_collecting_the_same_window_again_adds_nothing(
        self,
        collect_run: Callable[..., Any],
        recorded: Callable[[], Any]
    ) -> None:
        # The one this rule exists for. Recollecting is how a
        # corrected model is picked up, so a count that grew with each
        # one would report the operator's own fixing as the title
        # coming back.
        collect_run(items=[an_item(summary=UNMATCHED_TITLE)])

        collect_run(items=[an_item(summary=UNMATCHED_TITLE)])

        assert recorded()[0].times_seen == 1

    def test_a_second_run_seeing_it_counts_again(
        self,
        collect_run: Callable[..., Any],
        recorded: Callable[[], Any],
        runs: RunRepository
    ) -> None:
        # Which is the question the count answers: a title that turns
        # up month after month is a category the model is missing.
        collect_run(items=[an_item(summary=UNMATCHED_TITLE)])
        later = runs.create(
            calendar=CALENDAR,
            window_start='2026-10-01',
            window_end='2026-11-01'
        )

        collect_run(
            items=[an_item(summary=UNMATCHED_TITLE)],
            run_id=later.id
        )

        assert recorded()[0].times_seen == 2

    def test_a_title_that_stops_appearing_keeps_its_entry(
        self,
        collect_run: Callable[..., Any],
        recorded: Callable[[], Any]
    ) -> None:
        # The log outlives what a run holds: an alias added for it is
        # the thing that made it stop appearing.
        collect_run(items=[an_item(summary=UNMATCHED_TITLE)])

        collect_run(items=[an_item(summary=MATCHED_TITLE)])

        assert [entry.title for entry in recorded()] == [UNMATCHED_TITLE]
