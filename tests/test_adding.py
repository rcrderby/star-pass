#!/usr/bin/env python3
""" Pulling an event the search missed into a run.

    What a shift's times are worked out from is pinned in
    'test_shift_timing.py' and what a collection produces in
    'tests/collecting'.  These tests ask a different question: that a
    pulled-in event is the event the collection would have produced,
    that only an event nobody looked for may be pulled in, and that a
    refusal writes nothing.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring
# pylint: disable=too-many-arguments,too-many-positional-arguments

# Imports - Python Standard Library
import sqlite3
from typing import Any, Callable

# Imports - Third-Party
import pytest

# Imports - Local
from star_pass._adding import add_event
from star_pass._exceptions import ValidationError
from star_pass._records import (
    Opportunity,
    UncollectedEvent,
    UNCOLLECTED_ALL_DAY,
    UNCOLLECTED_EXCLUDED,
    UNCOLLECTED_SEARCH,
    UNCOLLECTED_UNTITLED
)
from star_pass._repository import (
    ChangeLogRepository,
    EventRepository,
    RunRepository,
    UncollectedRepository
)

# Constants
# A title the "events" calendar's data model matches, so a test about
# pulling one in exercises the real match rather than a stub.  Its
# category takes fifteen minutes off the start and adds thirty to the
# end, which is what makes the shift times worth asserting.
MATCHING_TITLE = 'Petals Scrimmage'
NEED_IDS = ('905196', '905197')

# What the calendar said about the event nobody searched for.
EVENT_ID = 'gcal-missed'
EVENT_DATE = '2026-09-11'
EVENT_START = '18:00'
EVENT_END = '19:00'

# What its category makes of those times.
SHIFT_START = '17:45'
SHIFT_END = '19:30'

# Who pulled it in.
SOMEBODY = 'static-token'


@pytest.fixture(name='uncollected')
def fixture_uncollected(
    connection: sqlite3.Connection
) -> UncollectedRepository:
    return UncollectedRepository(connection=connection)


@pytest.fixture(name='run')
def fixture_run(
    revisions: Any,
    other_run_id: str
) -> str:
    """ Return a run on the calendar whose model matches the title.

        The "events" calendar, because that is where the category
        with offsets lives; a run on the other one would match
        nothing and could not show the times being worked out.
    """
    revisions.create(run_id=other_run_id, replacing=True)

    return other_run_id


@pytest.fixture(name='missed')
def fixture_missed(
    uncollected: UncollectedRepository,
    run: str
) -> Callable[..., str]:
    """ Return a way to record one thing the run's window left out. """

    def record(**overrides: Any) -> str:
        """ Store the row, replacing any overridden field. """
        fields: dict = {
            'id': EVENT_ID,
            'reason': UNCOLLECTED_SEARCH,
            'title': MATCHING_TITLE,
            'date': EVENT_DATE,
            'calendar_start': EVENT_START,
            'calendar_end': EVENT_END
        }
        fields.update(overrides)
        uncollected.replace(
            run_id=run,
            uncollected=[UncollectedEvent(**fields)]
        )

        return fields['id']

    return record


@pytest.fixture(name='add')
def fixture_add(
    connection: sqlite3.Connection,
    amplify_holds: Callable[..., list],
    run: str
) -> Callable[..., Any]:
    """ Return a way to pull one event into the run.

        Amplify answers every opportunity read, because a pulled-in
        event may name one the run has never read and the run has to
        be able to label it.
    """
    asked = amplify_holds()

    def pull(event_id: str = EVENT_ID, run_id: str = '') -> Any:
        """ Pull the event in and return what was added. """
        return add_event(
            connection=connection,
            run_id=run_id or run,
            event_id=event_id,
            principal_id=SOMEBODY
        )

    pull.asked = asked

    return pull


class TestWhatIsPulledIn:
    def test_the_event_joins_the_current_revision(
        self,
        add: Callable[..., Any],
        events: EventRepository,
        missed: Callable[..., str],
        run: str
    ) -> None:
        missed()

        add()

        assert [
            event.id for event in events.list_all(run_id=run, revision=1)
        ] == [EVENT_ID]

    def test_the_event_is_marked_as_added_by_hand(
        self,
        add: Callable[..., Any],
        missed: Callable[..., str]
    ) -> None:
        # Reverting to the first revision drops these, so they have to
        # be distinguishable from what the calendar search found.
        missed()

        event, _ = add()

        assert event.added_by_hand is True

    def test_the_shift_times_are_the_ones_its_category_produces(
        self,
        add: Callable[..., Any],
        missed: Callable[..., str]
    ) -> None:
        # The offsets are applied to the calendar's times the same way
        # a collection applies them, because both go through one
        # builder.  A hand-added event timed a second way would reach
        # Amplify as a different shift.
        missed()

        event, _ = add()

        assert (event.calendar_start, event.calendar_end) == (
            EVENT_START,
            EVENT_END
        )
        assert (event.shift_start, event.shift_end) == (
            SHIFT_START,
            SHIFT_END
        )

    def test_the_event_carries_a_role_for_each_need_it_serves(
        self,
        add: Callable[..., Any],
        missed: Callable[..., str]
    ) -> None:
        missed()

        event, _ = add()

        assert tuple(
            role.need_id for role in event.roles
        ) == NEED_IDS

    def test_the_change_log_says_what_was_added_and_why_it_was_not(
        self,
        add: Callable[..., Any],
        change_log: ChangeLogRepository,
        missed: Callable[..., str],
        run: str
    ) -> None:
        missed()

        _, entry = add()

        assert MATCHING_TITLE in entry.entry
        assert 'search' in entry.entry
        assert entry.principal_id == SOMEBODY
        assert [
            written.entry for written in change_log.list_all(run_id=run)
        ] == [entry.entry]

    def test_the_record_of_what_was_left_out_is_not_deleted(
        self,
        add: Callable[..., Any],
        missed: Callable[..., str],
        run: str,
        uncollected: UncollectedRepository
    ) -> None:
        # What keeps it off the Not collected list is the revision
        # holding it, not the row being gone -- which is what lets
        # reverting to the first revision give it back.
        missed()

        add()

        assert [
            row.id for row in uncollected.list_all(run_id=run)
        ] == [EVENT_ID]


class TestTheOpportunityItNames:
    def test_the_run_gains_an_opportunity_it_did_not_hold(
        self,
        add: Callable[..., Any],
        missed: Callable[..., str],
        run: str,
        runs: RunRepository
    ) -> None:
        # Nobody searched for this event, so its category is not
        # necessarily one the collection met, and a row the run cannot
        # label is a row a reviewer cannot read.
        missed()

        add()

        assert tuple(
            opportunity.need_id
            for opportunity in runs.get_opportunities(run_id=run)
        ) == NEED_IDS

    def test_the_gained_opportunity_carries_what_amplify_calls_it(
        self,
        add: Callable[..., Any],
        missed: Callable[..., str],
        run: str,
        runs: RunRepository
    ) -> None:
        missed()

        add()

        assert [
            opportunity.title
            for opportunity in runs.get_opportunities(run_id=run)
        ] == [f'Need {need_id}' for need_id in NEED_IDS]

    def test_an_opportunity_the_run_holds_is_not_read_again(
        self,
        add: Callable[..., Any],
        missed: Callable[..., str],
        make_opportunity: Callable[..., Opportunity],
        run: str,
        runs: RunRepository
    ) -> None:
        # The titles it already has were read when it was collected,
        # and reading them again would spend a request to learn what
        # is already stored.
        runs.set_opportunities(
            run_id=run,
            opportunities=[
                make_opportunity(need_id=NEED_IDS[0])
            ]
        )
        missed()

        add()

        assert [
            request['url'].rsplit('/', 1)[-1] for request in add.asked
        ] == [NEED_IDS[1]]

    def test_the_opportunities_the_run_already_held_are_kept(
        self,
        add: Callable[..., Any],
        missed: Callable[..., str],
        make_opportunity: Callable[..., Opportunity],
        run: str,
        runs: RunRepository
    ) -> None:
        # A run records its opportunities as a set, so gaining one
        # means writing the set again -- and a write that carried only
        # what was gained would leave the collected events unlabelled.
        runs.set_opportunities(
            run_id=run,
            opportunities=[
                make_opportunity(
                    need_id=NEED_IDS[0],
                    title='Read when the run was collected'
                )
            ]
        )
        missed()

        add()

        assert [
            opportunity.title
            for opportunity in runs.get_opportunities(run_id=run)
        ] == [
            'Read when the run was collected',
            f'Need {NEED_IDS[1]}'
        ]

    def test_an_event_may_time_a_listing_the_run_holds_its_own_way(
        self,
        add: Callable[..., Any],
        events: EventRepository,
        make_opportunity: Callable[..., Opportunity],
        missed: Callable[..., str],
        run: str,
        runs: RunRepository
    ) -> None:
        # It used to be refused, because the run recorded one set of
        # offsets per opportunity. The timing is the role's now, so an
        # event pulled in brings its own and nothing disagrees (D25).
        runs.set_opportunities(
            run_id=run,
            opportunities=[make_opportunity(need_id=NEED_IDS[0])]
        )
        missed()

        add()

        added = events.list_all(run_id=run, revision=1)[0]

        assert [role.need_id for role in added.roles] == list(NEED_IDS)


class TestWhatMayNotBePulledIn:
    @pytest.mark.parametrize(
        'reason',
        (UNCOLLECTED_EXCLUDED, UNCOLLECTED_ALL_DAY, UNCOLLECTED_UNTITLED)
    )
    def test_only_an_event_nobody_searched_for_may_be_pulled_in(
        self,
        add: Callable[..., Any],
        missed: Callable[..., str],
        reason: str
    ) -> None:
        # Refused here rather than by a disabled button: a button and
        # the operation behind it would eventually disagree.
        missed(reason=reason)

        with pytest.raises(ValidationError) as error:
            add()

        assert reason in str(error.value)

    def test_an_identifier_the_run_left_nothing_out_under_is_refused(
        self,
        add: Callable[..., Any],
        missed: Callable[..., str]
    ) -> None:
        missed()

        with pytest.raises(ValidationError) as error:
            add(event_id='gcal-nothing')

        assert 'gcal-nothing' in str(error.value)

    def test_a_row_another_run_left_out_is_not_addable_to_this_one(
        self,
        add: Callable[..., Any],
        run_id: str,
        uncollected: UncollectedRepository
    ) -> None:
        # The identifier is the calendar's, so two runs whose windows
        # overlap hold rows for the same event. Pulling one in has to
        # read the row belonging to the run being added to.
        uncollected.replace(
            run_id=run_id,
            uncollected=[
                UncollectedEvent(
                    id=EVENT_ID,
                    reason=UNCOLLECTED_SEARCH,
                    title=MATCHING_TITLE,
                    date=EVENT_DATE,
                    calendar_start=EVENT_START,
                    calendar_end=EVENT_END
                )
            ]
        )

        with pytest.raises(ValidationError) as error:
            add()

        assert 'left nothing out' in str(error.value)

    def test_an_event_the_revision_already_holds_is_refused(
        self,
        add: Callable[..., Any],
        missed: Callable[..., str]
    ) -> None:
        # Which is what makes pulling one in twice a refusal rather
        # than two rows for one event.
        missed()
        add()

        with pytest.raises(ValidationError) as error:
            add()

        assert 'already holds' in str(error.value)

    def test_a_row_without_times_is_refused(
        self,
        add: Callable[..., Any],
        missed: Callable[..., str]
    ) -> None:
        missed(calendar_start=None, calendar_end=None)

        with pytest.raises(ValidationError) as error:
            add()

        assert 'nothing to build a shift from' in str(error.value)

    def test_a_row_without_a_title_is_refused(
        self,
        add: Callable[..., Any],
        missed: Callable[..., str]
    ) -> None:
        missed(title=None)

        with pytest.raises(ValidationError) as error:
            add()

        assert 'no title' in str(error.value)

    def test_a_run_that_has_collected_nothing_is_refused(
        self,
        connection: sqlite3.Connection,
        runs: RunRepository,
        uncollected: UncollectedRepository
    ) -> None:
        # A run still collecting has no revision to add to, and a
        # revision minted here would be one the collection then
        # replaced.
        empty = runs.create(
            calendar='events',
            window_start='2026-09-01',
            window_end='2026-10-01'
        ).id
        uncollected.replace(
            run_id=empty,
            uncollected=[
                UncollectedEvent(
                    id=EVENT_ID,
                    reason=UNCOLLECTED_SEARCH,
                    title=MATCHING_TITLE,
                    date=EVENT_DATE,
                    calendar_start=EVENT_START,
                    calendar_end=EVENT_END
                )
            ]
        )

        with pytest.raises(ValidationError) as error:
            add_event(
                connection=connection,
                run_id=empty,
                event_id=EVENT_ID,
                principal_id=SOMEBODY
            )

        assert 'collected nothing yet' in str(error.value)

    def test_an_unknown_run_is_reported_as_nothing_rather_than_refused(
        self,
        add: Callable[..., Any]
    ) -> None:
        # A run that is not there is the caller's to report, because
        # what it means depends on how it was asked for.
        assert add(run_id='no-such-run') is None


class TestARefusalWritesNothing:
    @pytest.fixture(name='refused')
    def fixture_refused(
        self,
        add: Callable[..., Any],
        missed: Callable[..., str]
    ) -> None:
        """ Refuse one event, for a test about what was left behind. """
        missed(reason=UNCOLLECTED_EXCLUDED)

        with pytest.raises(ValidationError):
            add()

        return None

    def test_no_event_is_added(
        self,
        events: EventRepository,
        refused: None,
        run: str
    ) -> None:
        del refused

        assert events.list_all(run_id=run, revision=1) == []

    def test_nothing_is_written_to_the_change_log(
        self,
        change_log: ChangeLogRepository,
        refused: None,
        run: str
    ) -> None:
        del refused

        assert change_log.list_all(run_id=run) == []

    def test_the_run_gains_no_opportunity(
        self,
        refused: None,
        run: str,
        runs: RunRepository
    ) -> None:
        del refused

        assert runs.get_opportunities(run_id=run) == []


class TestWhatIsLogged:
    def test_a_refusal_reaches_the_log(
        self,
        add: Callable[..., Any],
        caplog: pytest.LogCaptureFixture,
        missed: Callable[..., str]
    ) -> None:
        # The core logs its own cause before raising, which is what
        # lets a caller show the reason once rather than twice.
        missed(reason=UNCOLLECTED_ALL_DAY)

        with pytest.raises(ValidationError):
            add()

        assert UNCOLLECTED_ALL_DAY in caplog.text

    def test_what_was_pulled_in_reaches_the_log(
        self,
        add: Callable[..., Any],
        caplog: pytest.LogCaptureFixture,
        missed: Callable[..., str],
        run: str
    ) -> None:
        missed()

        add()

        assert EVENT_ID in caplog.text
        assert run in caplog.text


class TestTheEventsAlreadyThere:
    def test_what_the_revision_held_is_left_alone(
        self,
        add: Callable[..., Any],
        events: EventRepository,
        make_event: Callable[..., Any],
        missed: Callable[..., str],
        run: str
    ) -> None:
        # Adding is not editing: the events the collection found are
        # not touched, and the new one joins them.
        events.add(
            run_id=run,
            revision=1,
            event=make_event()
        )
        held = events.list_all(run_id=run, revision=1)
        missed()

        add()

        assert events.list_all(run_id=run, revision=1)[:1] == held

    def test_the_events_it_joins_are_read_in_order(
        self,
        add: Callable[..., Any],
        events: EventRepository,
        make_event: Callable[..., Any],
        missed: Callable[..., str],
        run: str
    ) -> None:
        # A revision reads back in the order its events happen, so an
        # event pulled in for a later day comes after the ones the
        # collection found.
        events.add(
            run_id=run,
            revision=1,
            event=make_event(date='2026-09-01')
        )
        missed()

        add()

        assert [
            event.date
            for event in events.list_all(run_id=run, revision=1)
        ] == ['2026-09-01', EVENT_DATE]
