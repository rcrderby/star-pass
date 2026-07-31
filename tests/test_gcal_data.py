""" Characterization tests for star_pass.gcal_data.GCALData.

    Covers the time/offset math in _get_shift_time_data, the calendar
    item filter, and the collection pipeline. Unless a test drives the
    pipeline deliberately, the GCALData instance is created with
    auto_prep_data=False so that construction performs no network calls.
"""
# pylint: disable=missing-function-docstring,missing-class-docstring
# pylint: disable=protected-access,redefined-outer-name

# Imports - Python Standard Library
import copy
import importlib
import logging
from unittest.mock import Mock

# Imports - Third-Party
import pytest

# Imports - Local
from star_pass import gcal_data
from star_pass._helpers import Helpers
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

    def test_event_spanning_more_than_a_day(self, gcal):
        # Regression for the 'timedelta.seconds' bug: 'seconds' excludes
        # the 'days' component, so a two-day event measured 0 minutes.
        # 'total_seconds' gives the real 2880 minute span.
        need = {'slots': 20, 'id': 628861}
        result = gcal._get_shift_time_data(
            need,
            '2025-04-11T18:00:00-07:00',
            '2025-04-09T18:00:00-07:00'
        )
        assert result == ('2025-04-09', '18:00', 2880)

    def test_long_event_still_capped_at_max_length(self, gcal):
        need = {'slots': 20, 'id': 628861, 'max_length': 165}
        result = gcal._get_shift_time_data(
            need,
            '2025-04-11T18:00:00-07:00',
            '2025-04-09T18:00:00-07:00'
        )
        assert result == ('2025-04-09', '18:00', 165)

    def test_negative_duration_exits(self, gcal, caplog):
        # Regression for the 'timedelta.seconds' bug: an end time pulled
        # before the start time reported ~1440 minutes instead of a
        # negative value, so a nonsense shift was created silently.
        need = {
            'slots': 20,
            'id': 628861,
            'offset_end': -90
        }

        with caplog.at_level(logging.ERROR, logger='star_pass'):
            with pytest.raises(SystemExit) as exc_info:
                gcal._get_shift_time_data(
                    need,
                    '2025-04-09T19:00:00-07:00',
                    '2025-04-09T18:00:00-07:00',
                    need_name='Backwards Scrimmage'
                )

        assert exc_info.value.code == 1
        assert 'Backwards Scrimmage' in caplog.text
        assert '-30 minute(s)' in caplog.text
        assert 'offset_end -90' in caplog.text

    def test_zero_duration_exits(self, gcal, caplog):
        # An offset that collapses the shift to nothing is equally wrong.
        need = {'slots': 20, 'id': 628861, 'offset_end': -60}

        with caplog.at_level(logging.ERROR, logger='star_pass'):
            with pytest.raises(SystemExit):
                gcal._get_shift_time_data(
                    need,
                    '2025-04-09T19:00:00-07:00',
                    '2025-04-09T18:00:00-07:00'
                )

        assert '0 minute(s)' in caplog.text


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
        # Regression: an all-day event has no 'dateTime', which raised
        # an uncaught KeyError while the shift was being built.
        items = [_all_day_item('Board Retreat', '2099-01-05', '2099-01-06')]

        with caplog.at_level(logging.WARNING, logger='star_pass'):
            result = gcal.filter_gcal_items(items)

        assert result == []
        assert 'Board Retreat' in caplog.text
        assert 'all-day' in caplog.text

    def test_drops_untitled_events(self, gcal, caplog):
        # Regression: an event with no 'summary' raised an uncaught
        # KeyError while the shift was being built.
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


class TestCollectionPipeline:
    # End-to-end: calendar JSON in, CSV file out, with no network call.

    @staticmethod
    def _run_pipeline(monkeypatch, tmp_path, items):
        # Serve one page of calendar items and capture the CSV file the
        # run writes.
        monkeypatch.setattr(gcal_data, 'INPUT_DIR_PATH', tmp_path)
        pages = iter([_mock_response({'items': items})])
        monkeypatch.setattr(
            Helpers,
            'send_api_request',
            lambda _self, **_kwargs: next(pages)
        )

        # The 'events' calendar has a single query string, so the page
        # loop issues exactly one request.
        GCALData(gcal_name='events')

        written = list(tmp_path.glob('gcal_shifts_*.csv'))
        assert len(written) == 1
        return written[0].read_text(encoding='utf-8')

    def test_unusable_and_excluded_events_never_reach_the_model(
        self, monkeypatch, tmp_path, caplog
    ):
        # Regression for two coupled bugs: shifts were built before
        # filtering, so an all-day or untitled event raised a KeyError,
        # and every excluded event was matched against the shift data
        # model first, logging a spurious review warning each run.
        items = [
            _timed_item(
                'GNR v HH',
                '2099-01-05T18:00:00-08:00',
                '2099-01-05T20:00:00-08:00'
            ),
            _timed_item(
                'CANCELLED: Jet City vs Cherry City',
                '2099-01-06T18:00:00-08:00',
                '2099-01-06T20:00:00-08:00'
            ),
            _all_day_item('Board Retreat', '2099-01-07', '2099-01-08'),
            {
                'start': {'dateTime': '2099-01-08T18:00:00-08:00'},
                'end': {'dateTime': '2099-01-08T20:00:00-08:00'}
            },
        ]

        with caplog.at_level(logging.WARNING, logger='star_pass'):
            csv_text = self._run_pipeline(monkeypatch, tmp_path, items)

        # Only the matched event produces shifts: one row per need ID,
        # with the model's offsets applied (18:00 +15, 20:00 +30).
        rows = [line for line in csv_text.splitlines() if line.strip()]
        assert len(rows) == 3
        assert all('GNR v HH' in row for row in rows[1:])
        assert all(',135,' in row for row in rows[1:])
        assert '879609' in csv_text and '879610' in csv_text

        # The excluded event was never matched, so no review warning.
        assert 'review' not in caplog.text.lower()
        assert 'Jet City' not in caplog.text

    def test_an_all_day_event_does_not_abort_the_run(
        self, monkeypatch, tmp_path
    ):
        # Before filtering moved ahead of shift building, this raised
        # KeyError('dateTime') and lost the whole collection.
        items = [
            _all_day_item('Board Retreat', '2099-01-07', '2099-01-08'),
            _timed_item(
                'GNR v HH',
                '2099-01-05T18:00:00-08:00',
                '2099-01-05T20:00:00-08:00'
            ),
        ]

        csv_text = self._run_pipeline(monkeypatch, tmp_path, items)

        assert 'GNR v HH' in csv_text


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
