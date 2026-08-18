#!/usr/bin/env python3
""" Titles the data model did not match, and how often.

    A sighting is stored and an entry is read back, so what these pin
    is mostly the difference between the two: that recording the same
    title twice counts to two rather than overwriting anything, that a
    calendar is part of what a title is, and that the log belongs to
    no run and survives one being deleted.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
from typing import Any, Callable

# Imports - Third-Party
import pytest

# Imports - Local
from star_pass._repository import RunRepository, UnmatchedTitleRepository

# Constants
# A title the model has no alias for, and the calendar it turned up
# in.  Two calendars, because the categories a title is matched
# against belong to one.
TITLE = 'Jet City vs Cherry City'
OTHER_TITLE = 'Rat City Invitational'
CALENDAR = 'events'
OTHER_CALENDAR = 'practices'

# Who recorded it (D13).
RECORDED_BY = 'static-token'

# Two moments a month apart.  Written rather than waited for: the
# times this layer records are whole seconds, so two sightings a test
# takes to record are the same instant, and an entry that reported the
# latest as its earliest would read as correct.
EARLIER = '2026-01-01T00:00:00+00:00'
LATER = '2026-02-01T00:00:00+00:00'


@pytest.fixture(name='record')
def fixture_record(
    unmatched: UnmatchedTitleRepository
) -> Callable[..., Any]:
    """ Return a way to record one sighting of a title. """

    def sighting(
        title: str = TITLE,
        calendar: str = CALENDAR,
        run_id: Any = None
    ) -> Any:
        """ Record it and return the entry as the log now holds it. """
        return unmatched.record(
            calendar=calendar,
            title=title,
            run_id=run_id,
            principal_id=RECORDED_BY
        )

    return sighting


@pytest.fixture(name='at')
def fixture_at(
    monkeypatch: pytest.MonkeyPatch
) -> Callable[[str], None]:
    """ Return a way to say when the next sighting is recorded. """

    def moment(recorded_at: str) -> None:
        """ Have the layer record that time. """
        monkeypatch.setattr(
            'star_pass._repository._unmatched.utc_now',
            lambda: recorded_at
        )

    return moment


class TestRecordingASighting:
    def test_the_title_is_kept_as_it_was_given(
        self,
        record: Callable[..., Any]
    ) -> None:
        # What the model has to match is the thing somebody typed.
        assert record().title == TITLE

    def test_the_first_sighting_counts_one(
        self,
        record: Callable[..., Any]
    ) -> None:
        assert record().times_seen == 1

    def test_the_answer_counts_every_sighting_so_far(
        self,
        record: Callable[..., Any]
    ) -> None:
        # Read back rather than assembled from the row just written:
        # what the caller is given is the count over all of them.
        record()

        assert record().times_seen == 2

    def test_the_same_title_stays_one_entry(
        self,
        record: Callable[..., Any],
        unmatched: UnmatchedTitleRepository
    ) -> None:
        # A list showing the same title eleven times is a list nobody
        # works through.
        record()
        record()

        assert len(unmatched.list_all()) == 1

    def test_the_first_and_most_recent_sightings_are_both_kept(
        self,
        at: Callable[[str], None],
        record: Callable[..., Any]
    ) -> None:
        # The pair says how long a title has been turning up, which is
        # a different question from how often.
        at(EARLIER)
        record()
        at(LATER)

        entry = record()

        assert entry.first_seen == EARLIER
        assert entry.last_seen == LATER


class TestWhatMakesTwoTitlesDifferent:
    def test_a_different_title_is_a_different_entry(
        self,
        record: Callable[..., Any],
        unmatched: UnmatchedTitleRepository
    ) -> None:
        record()

        record(title=OTHER_TITLE)

        assert len(unmatched.list_all()) == 2

    def test_the_same_title_in_another_calendar_is_another_entry(
        self,
        record: Callable[..., Any],
        unmatched: UnmatchedTitleRepository
    ) -> None:
        # The categories a title is matched against belong to a
        # calendar, so the same title can be matched in one and
        # unmatched in the other.
        record()

        record(calendar=OTHER_CALENDAR)

        assert [
            entry.calendar for entry in unmatched.list_all()
        ] == [OTHER_CALENDAR, CALENDAR]

    def test_one_title_is_read_on_its_own(
        self,
        record: Callable[..., Any],
        unmatched: UnmatchedTitleRepository
    ) -> None:
        record()
        record(calendar=OTHER_CALENDAR)

        entry = unmatched.get(calendar=CALENDAR, title=TITLE)

        assert entry.calendar == CALENDAR
        assert entry.times_seen == 1

    def test_a_title_nothing_recorded_reads_as_nothing(
        self,
        unmatched: UnmatchedTitleRepository
    ) -> None:
        assert unmatched.get(calendar=CALENDAR, title=TITLE) is None


class TestReadingTheLog:
    def test_an_empty_log_reads_as_nothing(
        self,
        unmatched: UnmatchedTitleRepository
    ) -> None:
        assert unmatched.list_all() == []

    def test_the_most_recently_seen_title_comes_first(
        self,
        record: Callable[..., Any],
        unmatched: UnmatchedTitleRepository
    ) -> None:
        # A title that has just started turning up is read before one
        # somebody has already decided about.
        record()
        record(title=OTHER_TITLE)

        assert [
            entry.title for entry in unmatched.list_all()
        ] == [OTHER_TITLE, TITLE]


class TestWhatTheLogOutlives:
    def test_it_belongs_to_no_run(
        self,
        record: Callable[..., Any],
        unmatched: UnmatchedTitleRepository
    ) -> None:
        # Recorded without one, because a title can be noticed
        # somewhere other than in a run.
        record()

        assert unmatched.list_all()[0].times_seen == 1

    def test_deleting_the_run_it_was_noticed_in_leaves_it(
        self,
        record: Callable[..., Any],
        run_id: str,
        runs: RunRepository,
        unmatched: UnmatchedTitleRepository
    ) -> None:
        # The whole reason it is stored outside a run: what the model
        # is missing outlives the window that showed it.
        record(run_id=run_id)

        runs.delete(run_id=run_id)

        assert len(unmatched.list_all()) == 1
