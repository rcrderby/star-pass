#!/usr/bin/env python3
""" Tests for what a run's window held and the run left out. """

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
from typing import Any, Callable

# Imports - Third-Party
import pytest

# Imports - Local
from star_pass._exceptions import ValidationError
from star_pass._records import (
    UncollectedEvent,
    UNCOLLECTED_ALL_DAY,
    UNCOLLECTED_EXCLUDED,
    UNCOLLECTED_SEARCH,
    UNCOLLECTED_UNTITLED
)
from star_pass._repository import RunRepository, UncollectedRepository


@pytest.fixture(name='make_uncollected')
def fixture_make_uncollected() -> Callable[..., UncollectedEvent]:
    """ Return a factory building one thing a run left out. """

    def build(**overrides: Any) -> UncollectedEvent:
        """ Return the record, replacing any overridden field. """
        fields: dict = {
            'id': 'gcal-1',
            'reason': UNCOLLECTED_SEARCH,
            'title': 'Board Meeting',
            'date': '2026-09-04',
            'calendar_start': '18:00',
            'calendar_end': '19:00'
        }
        fields.update(overrides)

        return UncollectedEvent(**fields)

    return build


class TestStoringWhatWasNotCollected:
    def test_a_stored_row_comes_back_as_it_went_in(
        self,
        uncollected: UncollectedRepository,
        run_id: str,
        make_uncollected: Callable[..., UncollectedEvent]
    ) -> None:
        left_out = make_uncollected()

        uncollected.replace(run_id=run_id, uncollected=[left_out])

        assert uncollected.list_all(run_id=run_id) == [left_out]

    def test_a_run_whose_window_held_nothing_else_reads_empty(
        self,
        uncollected: UncollectedRepository,
        run_id: str
    ) -> None:
        assert uncollected.list_all(run_id=run_id) == []

    def test_every_field_but_the_reason_may_be_absent(
        self,
        uncollected: UncollectedRepository,
        run_id: str,
        make_uncollected: Callable[..., UncollectedEvent]
    ) -> None:
        # The reasons name exactly the events that are missing
        # something, so a row that stored none of it is ordinary.
        bare = make_uncollected(
            reason=UNCOLLECTED_UNTITLED,
            title=None,
            date=None,
            calendar_start=None,
            calendar_end=None
        )

        uncollected.replace(run_id=run_id, uncollected=[bare])

        assert uncollected.list_all(run_id=run_id) == [bare]

    def test_the_rows_come_back_earliest_first(
        self,
        uncollected: UncollectedRepository,
        run_id: str,
        make_uncollected: Callable[..., UncollectedEvent]
    ) -> None:
        uncollected.replace(
            run_id=run_id,
            uncollected=[
                make_uncollected(id='late', date='2026-09-20'),
                make_uncollected(id='early', date='2026-09-02'),
                make_uncollected(
                    id='same-day-earlier',
                    date='2026-09-20',
                    calendar_start='08:00'
                )
            ]
        )

        assert [
            row.id for row in uncollected.list_all(run_id=run_id)
        ] == ['early', 'same-day-earlier', 'late']

    def test_a_second_collection_replaces_the_first_answer(
        self,
        uncollected: UncollectedRepository,
        run_id: str,
        make_uncollected: Callable[..., UncollectedEvent]
    ) -> None:
        # A collection reads the whole window, so what it found is the
        # whole truth about that window; merging would keep rows
        # describing events the calendar no longer has.
        uncollected.replace(
            run_id=run_id,
            uncollected=[make_uncollected(id='gone')]
        )
        uncollected.replace(
            run_id=run_id,
            uncollected=[make_uncollected(id='there-now')]
        )

        assert [
            row.id for row in uncollected.list_all(run_id=run_id)
        ] == ['there-now']

    def test_another_runs_rows_are_left_alone(
        self,
        uncollected: UncollectedRepository,
        run_id: str,
        other_run_id: str,
        make_uncollected: Callable[..., UncollectedEvent]
    ) -> None:
        # The same calendar event can be in two runs' windows, and
        # replacing one run's answer must not empty the other's.
        uncollected.replace(
            run_id=other_run_id,
            uncollected=[make_uncollected()]
        )
        uncollected.replace(run_id=run_id, uncollected=[])

        assert len(uncollected.list_all(run_id=other_run_id)) == 1

    def test_a_reason_the_layer_does_not_know_is_refused(
        self,
        uncollected: UncollectedRepository,
        run_id: str,
        make_uncollected: Callable[..., UncollectedEvent]
    ) -> None:
        with pytest.raises(ValidationError) as error:
            uncollected.replace(
                run_id=run_id,
                uncollected=[make_uncollected(reason='bored')]
            )

        assert 'bored' in str(error.value)

    def test_a_refused_reason_leaves_what_was_there(
        self,
        uncollected: UncollectedRepository,
        run_id: str,
        make_uncollected: Callable[..., UncollectedEvent]
    ) -> None:
        # The reasons are checked before anything is deleted, so a bad
        # value in the last row does not empty the run's answer.
        uncollected.replace(
            run_id=run_id,
            uncollected=[make_uncollected(reason=UNCOLLECTED_EXCLUDED)]
        )

        with pytest.raises(ValidationError):
            uncollected.replace(
                run_id=run_id,
                uncollected=[
                    make_uncollected(id='fine', reason=UNCOLLECTED_ALL_DAY),
                    make_uncollected(id='not-fine', reason='bored')
                ]
            )

        assert [
            row.reason for row in uncollected.list_all(run_id=run_id)
        ] == [UNCOLLECTED_EXCLUDED]

    def test_a_row_for_a_run_that_is_not_there_is_refused(
        self,
        uncollected: UncollectedRepository,
        make_uncollected: Callable[..., UncollectedEvent]
    ) -> None:
        with pytest.raises(ValidationError):
            uncollected.replace(
                run_id='no-such-run',
                uncollected=[make_uncollected()]
            )

    def test_deleting_a_run_takes_its_rows_with_it(
        self,
        runs: RunRepository,
        uncollected: UncollectedRepository,
        run_id: str,
        make_uncollected: Callable[..., UncollectedEvent]
    ) -> None:
        # Nothing depends on this record once the run is gone, so it
        # cascades rather than holding the deletion up.
        uncollected.replace(
            run_id=run_id,
            uncollected=[make_uncollected()]
        )

        runs.delete(run_id=run_id)

        assert uncollected.list_all(run_id=run_id) == []
