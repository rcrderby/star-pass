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
from star_pass._records import (
    UNCOLLECTED_ALL_DAY,
    UNCOLLECTED_EXCLUDED,
    UNCOLLECTED_UNTITLED
)
from star_pass.gcal_data import exclusion_reason, GCALData


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


class TestWhyAnItemIsNotCollected:
    # The filter and the record of what a run left out read one
    # answer, so a reviewer is never given a reason for an item the
    # run collected anyway.

    def test_a_usable_item_has_no_reason(self):
        assert exclusion_reason(
            gcal_item=_timed_item(
                'Wreckers A/B Scrimmage',
                '2099-01-05T18:00:00-08:00',
                '2099-01-05T20:00:00-08:00'
            )
        ) is None

    def test_an_untitled_item_is_untitled_rather_than_excluded(self):
        # The title is read before it is matched against the excluded
        # terms, so an item with none is named for what it lacks.
        assert exclusion_reason(
            gcal_item={
                'start': {'dateTime': '2099-01-05T18:00:00-08:00'},
                'end': {'dateTime': '2099-01-05T20:00:00-08:00'}
            }
        ) == UNCOLLECTED_UNTITLED

    def test_an_excluded_title_is_excluded(self):
        assert exclusion_reason(
            gcal_item=_timed_item(
                'CANCELED: Adult Scrimmage',
                '2099-01-05T18:00:00-08:00',
                '2099-01-05T20:00:00-08:00'
            )
        ) == UNCOLLECTED_EXCLUDED

    def test_an_all_day_item_is_an_all_day_one(self):
        assert exclusion_reason(
            gcal_item=_all_day_item(
                'Board Retreat',
                '2099-01-05',
                '2099-01-06'
            )
        ) == UNCOLLECTED_ALL_DAY

    def test_a_cancelled_all_day_item_is_reported_as_excluded(self):
        # Both reasons hold.  The excluded one is the useful answer:
        # an all-day event is one somebody may want pulled in and a
        # cancelled one never is.
        assert exclusion_reason(
            gcal_item=_all_day_item(
                'CANCELLED: Board Retreat',
                '2099-01-05',
                '2099-01-06'
            )
        ) == UNCOLLECTED_EXCLUDED


class TestReadingAWindowWhole:
    # A run has to be able to say what it did not collect, and the
    # events nobody looked for are the ones the configured query
    # strings never returned.

    def test_a_searched_calendar_is_read_again_without_a_query(
        self,
        monkeypatch
    ):
        # 'practices' is searched for two terms, neither of them the
        # empty string, so the whole window is a third request.
        gcal = GCALData(gcal_name='practices')
        queries = []

        def fake_send(api_request_data, **_kwargs):
            queries.append(api_request_data['params']['q'])

            return _mock_response({'items': [{'id': queries[-1] or 'all'}]})

        monkeypatch.setattr(gcal.helpers, 'send_api_request', fake_send)

        read = gcal.read_window(
            timeMin='2099-01-01T00:00:00-00:00',
            timeMax='2099-01-31T00:00:00-00:00'
        )

        assert queries == ['officials', 'scrimmage', '']
        assert read.searched == [{'id': 'officials'}, {'id': 'scrimmage'}]
        assert read.everything == [{'id': 'all'}]

    def test_a_calendar_read_whole_already_is_not_read_twice(
        self,
        monkeypatch
    ):
        # 'events' is configured with the empty query string, so its
        # search is the whole window and a second request would be the
        # same request.
        gcal = GCALData(gcal_name='events')
        queries = []

        def fake_send(api_request_data, **_kwargs):
            queries.append(api_request_data['params']['q'])

            return _mock_response({'items': [{'id': 'a'}]})

        monkeypatch.setattr(gcal.helpers, 'send_api_request', fake_send)

        read = gcal.read_window(
            timeMin='2099-01-01T00:00:00-00:00',
            timeMax='2099-01-31T00:00:00-00:00'
        )

        assert queries == ['']
        assert read.everything == read.searched == [{'id': 'a'}]


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
