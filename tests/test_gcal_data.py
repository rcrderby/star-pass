""" Characterization tests for star_pass.gcal_data.GCALData.

    Covers the calendar item filter and the paged calendar read.
    Construction sends no request, so an instance can be built without
    reaching Google Calendar.
"""
# pylint: disable=missing-function-docstring,missing-class-docstring
# pylint: disable=protected-access,redefined-outer-name

# Imports - Python Standard Library
import copy
import logging
from unittest.mock import Mock

# Imports - Third-Party
import pytest

# Imports - Local
from star_pass.gcal_data import GCALData


@pytest.fixture
def gcal() -> GCALData:
    return GCALData(gcal_name='practices')


def _mock_response(payload: dict) -> Mock:
    # Build a stand-in for a requests.Response whose .json() returns
    # the supplied payload.
    response = Mock()
    response.json.return_value = payload
    return response


def _timed_item(summary: str, start: str, end: str) -> dict:
    # A Google Calendar item for an event with a start and end time.
    return {
        'summary': summary,
        'start': {'dateTime': start},
        'end': {'dateTime': end}
    }


def _all_day_item(summary: str, start: str, end: str) -> dict:
    # An all-day event carries 'date' instead of 'dateTime'.
    return {
        'summary': summary,
        'start': {'date': start},
        'end': {'date': end}
    }


class TestFilterGcalItems:
    # Filtering runs before shifts are built, so an unusable item cannot
    # raise and a filtered-out event is never matched against the model.

    def test_keeps_an_ordinary_event(self, gcal):
        items = [
            _timed_item(
                'Wreckers A/B Scrimmage',
                '2099-01-05T18:00:00-08:00',
                '2099-01-05T20:00:00-08:00'
            )
        ]

        assert gcal.filter_gcal_items(items) == items

    @pytest.mark.parametrize(
        'title',
        [
            'CANCELED: Adult Scrimmage',
            'Cancelled Officials Practice',
            'Derby Daze',
            'Summer Camp Session 2'
        ]
    )
    def test_drops_excluded_titles(self, gcal, title):
        items = [
            _timed_item(
                title,
                '2099-01-05T18:00:00-08:00',
                '2099-01-05T20:00:00-08:00'
            )
        ]

        assert gcal.filter_gcal_items(items) == []

    def test_drops_all_day_events(self, gcal, caplog):
        # An all-day event has no 'dateTime', so building a shift from
        # one raises an uncaught KeyError.
        items = [_all_day_item('Board Retreat', '2099-01-05', '2099-01-06')]

        with caplog.at_level(logging.WARNING, logger='star_pass'):
            result = gcal.filter_gcal_items(items)

        assert result == []
        assert 'Board Retreat' in caplog.text
        assert 'all-day' in caplog.text

    def test_drops_untitled_events(self, gcal, caplog):
        # An event with no 'summary' raises an uncaught KeyError while
        # the shift is being built.
        items = [
            {
                'start': {'dateTime': '2099-01-05T18:00:00-08:00'},
                'end': {'dateTime': '2099-01-05T20:00:00-08:00'}
            }
        ]

        with caplog.at_level(logging.WARNING, logger='star_pass'):
            result = gcal.filter_gcal_items(items)

        assert result == []
        assert 'no title' in caplog.text

    def test_keeps_only_the_usable_items(self, gcal):
        good = _timed_item(
            'Wreckers A/B Scrimmage',
            '2099-01-05T18:00:00-08:00',
            '2099-01-05T20:00:00-08:00'
        )
        items = [
            good,
            _timed_item(
                'CANCELLED: Adult Scrimmage',
                '2099-01-06T18:00:00-08:00',
                '2099-01-06T20:00:00-08:00'
            ),
            _all_day_item('Board Retreat', '2099-01-07', '2099-01-08'),
        ]

        assert gcal.filter_gcal_items(items) == [good]


class TestGetGcalShiftData:
    # The 'events' calendar has a single query string, which keeps the
    # pagination assertions focused on the page loop itself.

    def test_follows_next_page_token(self, monkeypatch):
        gcal = GCALData(gcal_name='events')
        pages = [
            _mock_response(
                {'items': [{'id': 'a'}], 'nextPageToken': 'PAGE2'}
            ),
            _mock_response(
                {'items': [{'id': 'b'}]}
            ),
        ]
        seen_params = []

        def fake_send(api_request_data, **_kwargs):
            # Snapshot params per call; the method mutates one dict.
            seen_params.append(copy.deepcopy(api_request_data['params']))
            return pages[len(seen_params) - 1]

        monkeypatch.setattr(gcal.helpers, 'send_api_request', fake_send)

        result = gcal.get_gcal_shift_data(
            timeMin='2099-01-01T00:00:00-00:00',
            timeMax='2099-01-31T00:00:00-00:00'
        )

        # Items from both pages are accumulated in order.
        assert result == [{'id': 'a'}, {'id': 'b'}]
        # Two requests: the initial page and the next-page follow-up.
        assert len(seen_params) == 2
        assert 'pageToken' not in seen_params[0]
        assert seen_params[1]['pageToken'] == 'PAGE2'

    def test_missing_items_key_does_not_raise(self, monkeypatch):
        gcal = GCALData(gcal_name='events')
        response = _mock_response({})  # no 'items', no 'nextPageToken'

        monkeypatch.setattr(
            gcal.helpers,
            'send_api_request',
            lambda **_kwargs: response
        )

        result = gcal.get_gcal_shift_data(
            timeMin='2099-01-01T00:00:00-00:00',
            timeMax='2099-01-31T00:00:00-00:00'
        )

        assert result == []
