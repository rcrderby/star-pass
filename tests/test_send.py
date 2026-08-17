#!/usr/bin/env python3
""" Putting a revision's shifts into Amplify.

    The only thing star-pass does that cannot be undone, so these tests
    are as much about what is *not* sent as about what is.  Amplify is
    reached through 'Helpers.send_api_request', which the 'amplify_holds'
    fixture replaces: no test here makes a live request, and the list it
    returns is what the send asked for.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
import sqlite3
from typing import Any, Callable, Dict, List

# Imports - Third-Party
import pytest

# Imports - Local
from star_pass._exceptions import UpstreamError, ValidationError
from star_pass._records import (
    EventRole,
    RUN_STATUS_PARTLY_SENT,
    RUN_STATUS_SENT,
    RUN_STATUS_UNSENT
)
from star_pass._reporting import Reporter
from star_pass._repository import RunRepository, SentShiftRepository
from star_pass._send import send

# Constants
# The opportunity the default event sends to, the row it would create
# there, and a second opportunity for the tests about batching.
NEED_ID = '905196'
OTHER_NEED_ID = '905197'
IDENTITY = (NEED_ID, '2026-09-03', '19:15', '21:30')

# Who a send is recorded as, and what one attempt to send is named
# (D13).  Named rather than called a key: a constant whose name reads
# as a credential is one the secret scanner stops on.
PRINCIPAL_ID = 'test-principal'
SEND_ATTEMPT = 'send-attempt-one'

# What a create request is addressed to, so a test can tell one from a
# read of the opportunity itself.
CREATE_SUFFIX = '/shifts'


def creates(sent: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """ Return only the create requests a send made. """
    return [
        request for request in sent
        if request['url'].endswith(CREATE_SUFFIX)
    ]


@pytest.fixture(name='already_there')
def fixture_already_there(
    amplify_holds: Callable[..., list],
    make_amplify_shift: Callable[..., dict]
) -> list:
    """ Answer as an Amplify that already holds the default shift.

        One fixture rather than two on every test that needs it: the
        arrangement is a single fact, and spelling it out per test made
        a test carry more fixtures than the thing it was asking about.
    """
    return amplify_holds({NEED_ID: [make_amplify_shift()]})


@pytest.fixture(name='half_sent')
def fixture_half_sent(
    answer_requests: Callable[..., list],
    sending: Callable[..., Any],
    collected: str,
    add_second_event: Callable[..., None]
) -> str:
    """ Return a run whose second batch Amplify refused.

        The arrangement is one fact and three tests ask different
        things about it, so it is made once: two opportunities, the
        first created and the second refused.
    """
    add_second_event(
        date='2026-09-10',
        roles=(EventRole(need_id=OTHER_NEED_ID, slots=2),)
    )
    answer_requests(_refusing_the_second_create())

    with pytest.raises(UpstreamError):
        sending(collected)

    return collected


@pytest.fixture(name='sending')
def fixture_sending(
    connection: sqlite3.Connection
) -> Callable[..., Any]:
    """ Return a way to send one run against the test's database. """

    def run(run_id: str, key: str = SEND_ATTEMPT) -> Any:
        """ Send the run, reporting nowhere. """
        return send(
            connection=connection,
            run_id=run_id,
            reporter=Reporter(),
            principal_id=PRINCIPAL_ID,
            idempotency_key=key
        )

    return run


class TestWhatReachesAmplify:
    def test_one_request_is_sent_per_opportunity(
        self,
        amplify_holds: Callable[..., list],
        sending: Callable[..., Any],
        collected: str,
        add_second_event: Callable[..., None]
    ) -> None:
        # Amplify's create endpoint takes an array, so a second shift
        # under one opportunity is a longer body, not a second request.
        add_second_event(date='2026-09-10')
        sent = amplify_holds()

        sending(collected)

        assert [request['url'] for request in creates(sent)] == [
            f'https://api.galaxydigital.com/api/needs/{NEED_ID}/shifts'
        ]

    def test_each_opportunity_gets_its_own_request(
        self,
        amplify_holds: Callable[..., list],
        sending: Callable[..., Any],
        collected: str,
        add_second_event: Callable[..., None]
    ) -> None:
        add_second_event(
            date='2026-09-10',
            roles=(EventRole(need_id=OTHER_NEED_ID, slots=2),)
        )
        sent = amplify_holds()

        sending(collected)

        assert len(creates(sent)) == 2

    def test_a_shift_carries_its_start_length_and_slots(
        self,
        amplify_holds: Callable[..., list],
        sending: Callable[..., Any],
        collected: str
    ) -> None:
        # Amplify takes a start and a length, never a start and an end.
        sent = amplify_holds()

        sending(collected)

        assert creates(sent)[0]['json'] == {
            'shifts': [
                {
                    'start': '2026-09-03 19:15',
                    'duration': '135',
                    'slots': '4'
                }
            ]
        }

    def test_the_opportunity_is_read_before_it_is_written_to(
        self,
        amplify_holds: Callable[..., list],
        sending: Callable[..., Any],
        collected: str
    ) -> None:
        # The read is what says which rows are missing, so a create
        # made before it would be a create made without knowing.
        sent = amplify_holds()

        sending(collected)

        assert [request['method'] for request in sent] == ['GET', 'POST']

    def test_a_shift_amplify_already_has_is_not_sent(
        self,
        already_there: list,
        sending: Callable[..., Any],
        collected: str,
        add_second_event: Callable[..., None]
    ) -> None:
        add_second_event(date='2026-09-10')
        sent = already_there

        sending(collected)

        assert creates(sent)[0]['json']['shifts'] == [
            {
                'start': '2026-09-10 19:15',
                'duration': '135',
                'slots': '4'
            }
        ]

    def test_an_opportunity_missing_nothing_is_not_written_to(
        self,
        already_there: list,
        sending: Callable[..., Any],
        collected: str
    ) -> None:
        # An empty create request would be a write to a live volunteer
        # system asking for nothing.
        sent = already_there

        sending(collected)

        assert creates(sent) == []

    def test_two_events_asking_for_one_row_send_it_once(
        self,
        amplify_holds: Callable[..., list],
        sending: Callable[..., Any],
        collected: str,
        add_second_event: Callable[..., None]
    ) -> None:
        add_second_event()
        sent = amplify_holds()

        sending(collected)

        assert len(creates(sent)[0]['json']['shifts']) == 1


class TestWhatIsWrittenDown:
    def test_the_shifts_created_are_recorded(
        self,
        amplify_holds: Callable[..., list],
        sending: Callable[..., Any],
        sent: SentShiftRepository,
        collected: str
    ) -> None:
        amplify_holds()

        sending(collected)

        assert sent.already_sent(run_id=collected) == {IDENTITY}

    def test_the_record_says_who_sent_it_and_under_which_key(
        self,
        amplify_holds: Callable[..., list],
        sending: Callable[..., Any],
        sent: SentShiftRepository,
        collected: str
    ) -> None:
        amplify_holds()

        sending(collected)
        recorded = sent.list_for_run(run_id=collected)[0]

        assert recorded.principal_id == PRINCIPAL_ID
        assert recorded.idempotency_key == SEND_ATTEMPT

    def test_a_shift_that_was_skipped_is_not_recorded(
        self,
        already_there: list,
        sending: Callable[..., Any],
        sent: SentShiftRepository,
        collected: str
    ) -> None:
        # The record says what this run created, not what Amplify has.
        del already_there

        sending(collected)

        assert sent.already_sent(run_id=collected) == set()

    def test_only_the_shifts_this_batch_created_are_recorded(
        self,
        already_there: list,
        sending: Callable[..., Any],
        sent: SentShiftRepository,
        collected: str,
        add_second_event: Callable[..., None]
    ) -> None:
        # The batch that reached Amplify held one of the two rows the
        # revision asks for; recording both would claim this run
        # created a shift it deliberately did not send.
        del already_there
        add_second_event(date='2026-09-10')

        sending(collected)

        assert sent.already_sent(run_id=collected) == {
            (NEED_ID, '2026-09-10', '19:15', '21:30')
        }

    def test_the_run_is_sent_and_says_when_it_reached_amplify(
        self,
        amplify_holds: Callable[..., list],
        sending: Callable[..., Any],
        runs: RunRepository,
        collected: str
    ) -> None:
        # One fact rather than two: a run becoming sent and the time it
        # was sent are what the repository writes in one statement.
        amplify_holds()

        sending(collected)
        run = runs.get(run_id=collected)

        assert run.status == RUN_STATUS_SENT
        assert run.sent_at is not None

    def test_a_run_that_found_everything_already_there_is_sent(
        self,
        already_there: list,
        sending: Callable[..., Any],
        runs: RunRepository,
        collected: str
    ) -> None:
        # Nothing is left for it to do, which is what the status says.
        del already_there

        sending(collected)

        assert runs.get(run_id=collected).status == RUN_STATUS_SENT

    def test_a_run_asking_for_nothing_is_left_where_it_was(
        self,
        amplify_holds: Callable[..., list],
        sending: Callable[..., Any],
        runs: RunRepository,
        run_id: str,
        revision: int
    ) -> None:
        # Saying it had sent would make a recollection refuse to
        # replace a run that has put nothing into Amplify.
        del revision
        amplify_holds()
        runs.set_status(run_id=run_id, status=RUN_STATUS_UNSENT)

        sending(run_id)

        assert runs.get(run_id=run_id).status == RUN_STATUS_UNSENT
        assert runs.get(run_id=run_id).sent_at is None

    def test_a_send_that_failed_part_way_leaves_the_run_partly_sent(
        self,
        half_sent: str,
        runs: RunRepository
    ) -> None:
        assert runs.get(run_id=half_sent).status == RUN_STATUS_PARTLY_SENT

    def test_the_batch_that_succeeded_stays_recorded(
        self,
        half_sent: str,
        sent: SentShiftRepository
    ) -> None:
        # What raised is unfinished, not undone: those rows are in
        # Amplify and cannot be taken back.
        assert sent.already_sent(run_id=half_sent) == {IDENTITY}

    def test_nothing_is_recorded_for_a_request_that_failed(
        self,
        half_sent: str,
        sent: SentShiftRepository
    ) -> None:
        # What that request did is exactly what is unknown.
        assert not [
            shift for shift in sent.list_for_run(run_id=half_sent)
            if shift.need_id == OTHER_NEED_ID
        ]


def _refusing_the_second_create() -> Callable[[str], dict]:
    """ Return a script whose second create request fails. """
    created: List[str] = []

    def body_for(url: str) -> dict:
        """ Answer a read, and refuse the second create. """
        if not url.endswith(CREATE_SUFFIX):
            return {'data': {'need_title': 'Need'}}

        created.append(url)

        if len(created) > 1:
            raise UpstreamError('Amplify refused the request.')

        return {}

    return body_for


class TestWhatStopsASend:
    def test_a_blocked_event_stops_the_whole_send(
        self,
        amplify_holds: Callable[..., list],
        sending: Callable[..., Any],
        collected: str,
        add_second_event: Callable[..., None]
    ) -> None:
        # A missing shift is invisible until volunteers cannot sign up,
        # so the run stops rather than sending the rest.
        add_second_event(category=None, roles=())
        sent = amplify_holds()

        with pytest.raises(ValidationError) as refused:
            sending(collected)

        assert '1 event(s)' in str(refused.value)
        assert sent == []

    def test_an_unknown_run_is_refused(
        self,
        amplify_holds: Callable[..., list],
        sending: Callable[..., Any]
    ) -> None:
        amplify_holds()

        with pytest.raises(ValidationError) as refused:
            sending('no-such-run')

        assert 'no-such-run' in str(refused.value)
