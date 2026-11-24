#!/usr/bin/env python3
""" Asking each League Calendar whether the key this process holds works.

    What these pin follows the Amplify check: never the key, never
    more of it than four characters, and a refusal answered rather
    than raised.  The addition is that each configured calendar is
    asked on its own and answers on its own.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
from typing import Any, Callable, Dict, List

# Imports - Third-Party
import pytest
from requests import Response

# Imports - Local
from star_pass import _defaults
from star_pass._credentials import (
    CALENDAR_CREDENTIAL_VARIABLE,
    CALENDAR_ID_NOT_CONFIGURED,
    check_calendar_credential
)
from star_pass._exceptions import UpstreamError

# Constants
# What the suite configures for the key and the two calendars.
KEY = 'test-gcal-token'
EVENTS_ID = 'test-events-calendar-id'
PRACTICES_ID = 'test-practices-calendar-id'

# Written out rather than sliced from the key, for the reason the
# Amplify tests give.
KEY_ENDS = 'oken'


@pytest.fixture(name='calendars_accept')
def fixture_calendars_accept(
    answer_requests: Callable[[Callable[[dict], dict]], list]
) -> List[Dict[str, Any]]:
    """ Have every calendar take the key, and return what was asked. """
    return answer_requests(lambda _request: {'items': []})


@pytest.fixture(name='practices_refuses')
def fixture_practices_refuses(
    monkeypatch: pytest.MonkeyPatch
) -> List[Dict[str, Any]]:
    """ Have the practices calendar refuse the key and events take it. """
    asked: List[Dict[str, Any]] = []

    def send(
        _self: Any,
        api_request_data: Dict[str, Any],
        **_ignored: Any
    ) -> Response:
        """ Answer one read, refusing the practices calendar. """
        asked.append(api_request_data)

        if PRACTICES_ID in api_request_data['url']:
            raise UpstreamError('Not Found')

        response = Response()
        response.status_code = 200

        return response

    monkeypatch.setattr(
        'star_pass._helpers.Helpers.send_api_request',
        send
    )

    return asked


class TestKeyAcceptedByEveryCalendar:
    def test_it_is_reported_as_working(
        self,
        calendars_accept: List[Dict[str, Any]]
    ) -> None:
        del calendars_accept

        checked = check_calendar_credential()

        assert checked.working is True
        assert checked.reason is None

    def test_each_calendar_answers_in_the_order_configured(
        self,
        calendars_accept: List[Dict[str, Any]]
    ) -> None:
        del calendars_accept

        calendars = check_calendar_credential().calendars

        assert [access.calendar for access in calendars] == list(
            _defaults.GCAL_CALENDARS
        )
        assert all(access.working for access in calendars)

    def test_only_four_characters_of_the_key_are_published(
        self,
        calendars_accept: List[Dict[str, Any]]
    ) -> None:
        del calendars_accept

        checked = check_calendar_credential()

        assert checked.last_four == KEY_ENDS
        assert KEY not in repr(checked)


class TestTheReadsItIsCheckedWith:
    def test_one_read_per_calendar_to_its_own_events(
        self,
        calendars_accept: List[Dict[str, Any]]
    ) -> None:
        check_calendar_credential()

        assert [request['url'] for request in calendars_accept] == [
            f'{_defaults.BASE_GCAL_URL}/{EVENTS_ID}/events',
            f'{_defaults.BASE_GCAL_URL}/{PRACTICES_ID}/events'
        ]

    def test_each_read_asks_for_one_event_with_the_key(
        self,
        calendars_accept: List[Dict[str, Any]]
    ) -> None:
        check_calendar_credential()

        for request in calendars_accept:
            assert request['method'] == 'GET'
            assert request['params'] == {'maxResults': 1, 'key': KEY}


class TestOneCalendarRefusing:
    def test_the_key_is_reported_as_not_working(
        self,
        practices_refuses: List[Dict[str, Any]]
    ) -> None:
        del practices_refuses

        checked = check_calendar_credential()

        assert checked.working is False
        assert checked.last_four == KEY_ENDS

    def test_only_that_calendar_is_reported_with_its_reason(
        self,
        practices_refuses: List[Dict[str, Any]]
    ) -> None:
        del practices_refuses

        answers = {
            access.calendar: access
            for access in check_calendar_credential().calendars
        }

        assert answers['events'].working is True
        assert answers['events'].reason is None
        assert answers['practices'].working is False
        assert answers['practices'].reason == 'Not Found'

    def test_every_calendar_is_still_asked(
        self,
        practices_refuses: List[Dict[str, Any]]
    ) -> None:
        check_calendar_credential()

        assert len(practices_refuses) == len(_defaults.GCAL_CALENDARS)


class TestARefusalQuotingTheKey:
    def test_the_key_is_redacted_from_the_reason(
        self,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The real request path, with only the session replaced: a
        # refused read quotes its address, and the key is in it.
        class Refusing:
            """ A session answering every read with a 400. """

            def request(self, **request: Any) -> Response:
                """ Refuse one read, quoting its address. """
                del self
                refused = Response()
                refused.status_code = 400
                refused.reason = 'Bad Request'
                refused.url = (
                    f'{request["url"]}?maxResults=1'
                    f'&key={request["params"]["key"]}'
                )

                return refused

        monkeypatch.setattr(
            'star_pass._helpers.Helpers._build_session',
            lambda _self: Refusing()
        )

        for access in check_calendar_credential().calendars:
            assert access.working is False
            assert KEY not in access.reason
            assert 'key=REDACTED' in access.reason


class TestNothingToReadWith:
    def test_no_key_is_reported_without_asking_any_calendar(
        self,
        monkeypatch: pytest.MonkeyPatch,
        calendars_accept: List[Dict[str, Any]]
    ) -> None:
        monkeypatch.delenv(CALENDAR_CREDENTIAL_VARIABLE, raising=False)

        checked = check_calendar_credential()

        assert checked.working is False
        assert checked.last_four is None
        assert CALENDAR_CREDENTIAL_VARIABLE in checked.reason
        assert checked.calendars == ()
        assert calendars_accept == []

    def test_a_calendar_with_no_identifier_is_not_read(
        self,
        monkeypatch: pytest.MonkeyPatch,
        calendars_accept: List[Dict[str, Any]]
    ) -> None:
        unset = {
            name: {**settings, 'gcal_id': None}
            if name == 'practices' else settings
            for name, settings in _defaults.GCAL_CALENDARS.items()
        }
        monkeypatch.setattr(_defaults, 'GCAL_CALENDARS', unset)

        answers = {
            access.calendar: access
            for access in check_calendar_credential().calendars
        }

        assert answers['practices'].working is False
        assert answers['practices'].reason == CALENDAR_ID_NOT_CONFIGURED
        assert len(calendars_accept) == 1
