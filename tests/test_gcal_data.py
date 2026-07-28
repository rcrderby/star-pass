""" Characterization tests for star_pass.gcal_data.GCALData.

    Focused on the pure time/offset math in _get_shift_time_data. The
    GCALData instance is created with auto_prep_data=False so that
    construction performs no network calls.
"""
# pylint: disable=missing-function-docstring,missing-class-docstring
# pylint: disable=protected-access,redefined-outer-name

# Imports - Python Standard Library
import copy
import importlib
from unittest.mock import Mock

# Imports - Third-Party
import pytest

# Imports - Local
from star_pass.gcal_data import GCALData, get_gcal_time_window


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


class TestGetGcalTimeWindow:
    # The search window has no default: a stale one silently collects
    # zero events, so every invalid state must fail loudly instead.

    VALID_MIN = '2099-01-01T00:00:00-00:00'
    VALID_MAX = '2099-01-31T00:00:00-00:00'

    def test_returns_the_configured_window(self, monkeypatch):
        monkeypatch.setenv('GCAL_TIME_MIN', self.VALID_MIN)
        monkeypatch.setenv('GCAL_TIME_MAX', self.VALID_MAX)

        assert get_gcal_time_window() == (self.VALID_MIN, self.VALID_MAX)

    @pytest.mark.parametrize('missing', ['GCAL_TIME_MIN', 'GCAL_TIME_MAX'])
    def test_raises_when_a_value_is_unset(self, monkeypatch, missing):
        monkeypatch.setenv('GCAL_TIME_MIN', self.VALID_MIN)
        monkeypatch.setenv('GCAL_TIME_MAX', self.VALID_MAX)
        monkeypatch.delenv(missing)

        with pytest.raises(ValueError, match=missing):
            get_gcal_time_window()

    def test_raises_when_both_are_unset(self, monkeypatch):
        monkeypatch.delenv('GCAL_TIME_MIN', raising=False)
        monkeypatch.delenv('GCAL_TIME_MAX', raising=False)

        with pytest.raises(ValueError) as error:
            get_gcal_time_window()

        assert 'GCAL_TIME_MIN' in str(error.value)
        assert 'GCAL_TIME_MAX' in str(error.value)

    def test_raises_when_a_value_is_empty(self, monkeypatch):
        monkeypatch.setenv('GCAL_TIME_MIN', '')
        monkeypatch.setenv('GCAL_TIME_MAX', self.VALID_MAX)

        with pytest.raises(ValueError, match='GCAL_TIME_MIN'):
            get_gcal_time_window()

    def test_raises_on_an_unparseable_value(self, monkeypatch):
        # A typo fails the same silent way a stale window does.
        monkeypatch.setenv('GCAL_TIME_MIN', '2099-01-01')
        monkeypatch.setenv('GCAL_TIME_MAX', self.VALID_MAX)

        with pytest.raises(ValueError, match='not a valid date and time'):
            get_gcal_time_window()

    def test_raises_when_the_window_does_not_move_forward(self, monkeypatch):
        monkeypatch.setenv('GCAL_TIME_MIN', self.VALID_MAX)
        monkeypatch.setenv('GCAL_TIME_MAX', self.VALID_MIN)

        with pytest.raises(ValueError, match='must be earlier than'):
            get_gcal_time_window()

    def test_raises_when_the_window_is_empty(self, monkeypatch):
        # Identical bounds select nothing at all.
        monkeypatch.setenv('GCAL_TIME_MIN', self.VALID_MIN)
        monkeypatch.setenv('GCAL_TIME_MAX', self.VALID_MIN)

        with pytest.raises(ValueError, match='must be earlier than'):
            get_gcal_time_window()


class TestOtherRunModesDoNotNeedTheWindow:
    # Regression guard: the window is validated lazily, when a calendar
    # request is about to run.  Reading it at import time would make the
    # create-shifts and Slack run modes -- and the scheduled Slack job --
    # require Google Calendar configuration they never use.

    def test_importing_the_cli_without_the_window(self, monkeypatch):
        monkeypatch.delenv('GCAL_TIME_MIN', raising=False)
        monkeypatch.delenv('GCAL_TIME_MAX', raising=False)

        # A fresh import of every module the CLI pulls in must succeed.
        for module in (
            'star_pass.gcal_data',
            'star_pass.amplify_shifts',
            'star_pass.amplify_responses',
            'star_pass.slack_notify',
        ):
            importlib.reload(importlib.import_module(module))

    def test_constructing_gcal_data_without_the_window(self, monkeypatch):
        # Construction alone performs no calendar request, so it must
        # not require the window either.
        monkeypatch.delenv('GCAL_TIME_MIN', raising=False)
        monkeypatch.delenv('GCAL_TIME_MAX', raising=False)

        assert GCALData(gcal_name='practices', auto_prep_data=False)


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
