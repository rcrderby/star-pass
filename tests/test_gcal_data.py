""" Characterization tests for star_pass.gcal_data.GCALData.

    Focused on the pure time/offset math in _get_shift_time_data. The
    GCALData instance is created with auto_prep_data=False so that
    construction performs no network calls.
"""
# pylint: disable=missing-function-docstring,missing-class-docstring
# pylint: disable=protected-access,redefined-outer-name

# Imports - Python Standard Library
import copy
from unittest.mock import Mock

# Imports - Third-Party
import pytest

# Imports - Local
from star_pass.gcal_data import GCALData


@pytest.fixture
def gcal() -> GCALData:
    # auto_prep_data=False prevents any Google Calendar API calls.
    return GCALData(gcal_name='practices', auto_prep_data=False)


def _mock_response(payload: dict) -> Mock:
    # Build a stand-in for a requests.Response whose .json() returns
    # the supplied payload.
    response = Mock()
    response.json.return_value = payload
    return response


class TestGetShiftTimeData:
    def test_applies_offsets_and_caps_at_max_length(self, gcal):
        # start -15 min => 17:45; end +30 min => 20:30 => 165 min span,
        # capped to max_length of 135.
        need = {
            'offset_start': -15,
            'offset_end': 30,
            'max_length': 135,
            'slots': 8,
            'id': 905197,
        }
        result = gcal._get_shift_time_data(
            need,
            '2025-04-09T20:00:00-07:00',
            '2025-04-09T18:00:00-07:00'
        )
        assert result == ('2025-04-09', '17:45', 135)

    def test_no_offsets_no_cap(self, gcal):
        # 18:00 to 20:00 with no offsets/cap => 120 minute duration.
        need = {'slots': 20, 'id': 628861}
        result = gcal._get_shift_time_data(
            need,
            '2025-04-09T20:00:00-07:00',
            '2025-04-09T18:00:00-07:00'
        )
        assert result == ('2025-04-09', '18:00', 120)


class TestGetGcalShiftData:
    # The 'events' calendar has a single query string, which keeps the
    # pagination assertions focused on the page loop itself.

    def test_follows_next_page_token(self, monkeypatch):
        gcal = GCALData(gcal_name='events', auto_prep_data=False)
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
        gcal = GCALData(gcal_name='events', auto_prep_data=False)
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
