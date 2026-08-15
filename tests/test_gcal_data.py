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
from star_pass._exceptions import ValidationError
from star_pass._helpers import Helpers
from star_pass._reporting import Reporter
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

    VALID_START = '2099-01-01T00:00:00-00:00'
    VALID_END = '2099-01-31T00:00:00-00:00'

    def test_honors_an_explicit_offset(self, monkeypatch):
        # A value carrying its own offset keeps that offset; only the
        # spelling is normalized ('-00:00' and '+00:00' are both UTC).
        monkeypatch.setenv('GCAL_WINDOW_START', self.VALID_START)
        monkeypatch.setenv('GCAL_WINDOW_END', self.VALID_END)

        assert get_gcal_time_window() == (
            '2099-01-01T00:00:00+00:00',
            '2099-01-31T00:00:00+00:00'
        )

    @pytest.mark.parametrize(
        'missing', ['GCAL_WINDOW_START', 'GCAL_WINDOW_END']
    )
    def test_raises_when_a_value_is_unset(self, monkeypatch, missing):
        monkeypatch.setenv('GCAL_WINDOW_START', self.VALID_START)
        monkeypatch.setenv('GCAL_WINDOW_END', self.VALID_END)
        monkeypatch.delenv(missing)

        with pytest.raises(ValueError, match=missing):
            get_gcal_time_window()

    def test_raises_when_both_are_unset(self, monkeypatch):
        monkeypatch.delenv('GCAL_WINDOW_START', raising=False)
        monkeypatch.delenv('GCAL_WINDOW_END', raising=False)

        with pytest.raises(ValueError) as error:
            get_gcal_time_window()

        assert 'GCAL_WINDOW_START' in str(error.value)
        assert 'GCAL_WINDOW_END' in str(error.value)

    def test_raises_when_a_value_is_empty(self, monkeypatch):
        monkeypatch.setenv('GCAL_WINDOW_START', '')
        monkeypatch.setenv('GCAL_WINDOW_END', self.VALID_END)

        with pytest.raises(ValueError, match='GCAL_WINDOW_START'):
            get_gcal_time_window()

    @pytest.mark.parametrize(
        'bad_value', ['not-a-date', '2099-13-01', '01/01/2099', '']
    )
    def test_raises_on_an_unparseable_value(self, monkeypatch, bad_value):
        # A typo fails the same silent way a stale window does.  An
        # empty value is reported as unset rather than unparseable.
        monkeypatch.setenv('GCAL_WINDOW_START', bad_value)
        monkeypatch.setenv('GCAL_WINDOW_END', self.VALID_END)

        with pytest.raises(ValueError, match='GCAL_WINDOW_START'):
            get_gcal_time_window()

    def test_raises_when_the_window_does_not_move_forward(self, monkeypatch):
        monkeypatch.setenv('GCAL_WINDOW_START', self.VALID_END)
        monkeypatch.setenv('GCAL_WINDOW_END', self.VALID_START)

        with pytest.raises(ValueError, match='must be earlier than'):
            get_gcal_time_window()

    def test_raises_when_the_window_is_empty(self, monkeypatch):
        # Identical bounds select nothing at all.
        monkeypatch.setenv('GCAL_WINDOW_START', self.VALID_START)
        monkeypatch.setenv('GCAL_WINDOW_END', self.VALID_START)

        with pytest.raises(ValueError, match='must be earlier than'):
            get_gcal_time_window()


class TestSearchWindowTimeZone:
    # A window value without an offset is local time in GCAL_TIMEZONE.
    # The zone supplies the offset in effect on that date, so the same
    # plain date means midnight local time year round and Daylight
    # Saving needs no attention.  Writing the window in UTC instead
    # shifts it eight hours earlier in winter, which drops evening
    # events on its final day.

    @pytest.mark.parametrize(
        'date_value, expected_offset',
        [
            ('2026-01-01', '-08:00'),   # PST
            ('2026-07-01', '-07:00'),   # PDT
            ('2026-03-08', '-08:00'),   # transition day, before 02:00
            ('2026-03-09', '-07:00'),   # day after the spring change
            ('2026-11-01', '-07:00'),   # transition day, before 02:00
            ('2026-11-02', '-08:00'),   # day after the autumn change
        ]
    )
    def test_applies_the_offset_in_effect_on_that_date(
            self, monkeypatch, date_value, expected_offset
    ):
        monkeypatch.delenv('GCAL_TIMEZONE', raising=False)
        monkeypatch.setenv('GCAL_WINDOW_START', date_value)
        monkeypatch.setenv('GCAL_WINDOW_END', '2099-01-01')

        window_start, _window_end = get_gcal_time_window()

        assert window_start == f'{date_value}T00:00:00{expected_offset}'

    def test_a_plain_date_starts_at_local_midnight(self, monkeypatch):
        # The whole point: a plain date must not drift into the previous
        # day, which is what a UTC-written window does in winter.
        monkeypatch.delenv('GCAL_TIMEZONE', raising=False)
        monkeypatch.setenv('GCAL_WINDOW_START', '2026-01-01')
        monkeypatch.setenv('GCAL_WINDOW_END', '2026-02-01')

        assert get_gcal_time_window() == (
            '2026-01-01T00:00:00-08:00',
            '2026-02-01T00:00:00-08:00'
        )

    def test_accepts_a_local_datetime(self, monkeypatch):
        monkeypatch.delenv('GCAL_TIMEZONE', raising=False)
        monkeypatch.setenv('GCAL_WINDOW_START', '2026-07-01T09:30:00')
        monkeypatch.setenv('GCAL_WINDOW_END', '2026-08-01')

        window_start, _window_end = get_gcal_time_window()

        assert window_start == '2026-07-01T09:30:00-07:00'

    def test_honors_a_different_time_zone(self, monkeypatch):
        monkeypatch.setenv('GCAL_TIMEZONE', 'America/New_York')
        monkeypatch.setenv('GCAL_WINDOW_START', '2026-01-01')
        monkeypatch.setenv('GCAL_WINDOW_END', '2026-02-01')

        window_start, _window_end = get_gcal_time_window()

        assert window_start == '2026-01-01T00:00:00-05:00'

    def test_raises_on_an_unknown_time_zone(self, monkeypatch):
        monkeypatch.setenv('GCAL_TIMEZONE', 'Mars/Olympus_Mons')
        monkeypatch.setenv('GCAL_WINDOW_START', '2026-01-01')
        monkeypatch.setenv('GCAL_WINDOW_END', '2026-02-01')

        with pytest.raises(ValueError, match='not a known time zone'):
            get_gcal_time_window()

    def test_orders_a_window_that_mixes_local_and_offset_values(
            self, monkeypatch
    ):
        # 00:00-08:00 is 08:00 UTC, so a UTC bound of 04:00 the same day
        # is earlier than a local midnight and must be rejected.
        monkeypatch.delenv('GCAL_TIMEZONE', raising=False)
        monkeypatch.setenv('GCAL_WINDOW_START', '2026-01-01')
        monkeypatch.setenv('GCAL_WINDOW_END', '2026-01-01T04:00:00+00:00')

        with pytest.raises(ValueError, match='must be earlier than'):
            get_gcal_time_window()


class TestOtherRunModesDoNotNeedTheWindow:
    # The window is validated lazily, when a calendar request is about
    # to run.  Reading it at import time would make the create-shifts
    # and Slack run modes -- and the scheduled Slack job -- require
    # Google Calendar configuration they never use.

    def test_importing_the_cli_without_the_window(self, monkeypatch):
        monkeypatch.delenv('GCAL_WINDOW_START', raising=False)
        monkeypatch.delenv('GCAL_WINDOW_END', raising=False)

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
        monkeypatch.delenv('GCAL_WINDOW_START', raising=False)
        monkeypatch.delenv('GCAL_WINDOW_END', raising=False)

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
        # 'timedelta.seconds' excludes the 'days' component, so a
        # two-day event would measure 0 minutes.  'total_seconds' gives
        # the real 2880 minute span.
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
        # 'timedelta.seconds' is never negative, so an end time pulled
        # before the start time reads as ~1440 minutes. The run must
        # fail rather than create a nonsense shift.
        need = {
            'slots': 20,
            'id': 628861,
            'offset_end': -90
        }

        with caplog.at_level(logging.ERROR, logger='star_pass'):
            with pytest.raises(ValidationError) as exc_info:
                gcal._get_shift_time_data(
                    need,
                    '2025-04-09T19:00:00-07:00',
                    '2025-04-09T18:00:00-07:00',
                    need_name='Backwards Scrimmage'
                )

        assert exc_info.value.args
        assert 'Backwards Scrimmage' in caplog.text
        assert '-30 minute(s)' in caplog.text
        assert 'offset_end -90' in caplog.text

    def test_zero_duration_exits(self, gcal, caplog):
        # An offset that collapses the shift to nothing is equally wrong.
        need = {'slots': 20, 'id': 628861, 'offset_end': -60}

        with caplog.at_level(logging.ERROR, logger='star_pass'):
            with pytest.raises(ValidationError):
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
        # Filtering runs before shifts are built, so an all-day or
        # untitled event cannot raise a KeyError, and an excluded event
        # never reaches the shift data model to log a review warning.
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


class TestCollectionReporting:
    # The run reports what it is doing to whatever the caller supplies.
    # The text those events produce is pinned in
    # tests/test_terminal_reporter.py; what matters here is that the
    # pipeline emits them, in order, and names the file it wrote.

    class RecordingReporter(Reporter):
        """ Record the event sequence instead of displaying it. """

        def __init__(self) -> None:
            self.events = []
            self.csv_path = None

        def calendar_read_started(self) -> None:
            self.events.append('read')

        def step_started(self, label: str) -> None:
            self.events.append(f'start:{label}')

        def step_finished(self) -> None:
            self.events.append('finish')

        def csv_written(self, path: str) -> None:
            self.events.append('written')
            self.csv_path = path

    @staticmethod
    def _serve_one_event(monkeypatch, tmp_path):
        # One page holding one usable event, written to tmp_path, with
        # no network call.
        monkeypatch.setattr(gcal_data, 'INPUT_DIR_PATH', tmp_path)
        pages = iter([_mock_response({'items': [
            _timed_item(
                'GNR v HH',
                '2099-01-05T18:00:00-08:00',
                '2099-01-05T20:00:00-08:00'
            )
        ]})])
        monkeypatch.setattr(
            Helpers,
            'send_api_request',
            lambda _self, **_kwargs: next(pages)
        )

    def test_the_pipeline_reports_every_step_in_order(
        self, monkeypatch, tmp_path
    ):
        self._serve_one_event(monkeypatch, tmp_path)

        reporter = self.RecordingReporter()
        GCALData(gcal_name='events', reporter=reporter)

        # Filtering precedes processing: an unusable event is dropped
        # before anything tries to build a shift from it.
        assert reporter.events == [
            'read',
            'start:Filtering event data', 'finish',
            'start:Processing Google Calendar event data', 'finish',
            'start:Converting Google Calendar events to Amplify shifts',
            'finish',
            'start:Writing Amplify shift data to a CSV file', 'finish',
            'written'
        ]

    def test_the_reported_path_is_the_file_that_was_written(
        self, monkeypatch, tmp_path
    ):
        self._serve_one_event(monkeypatch, tmp_path)

        reporter = self.RecordingReporter()
        GCALData(gcal_name='events', reporter=reporter)

        written = list(tmp_path.glob('gcal_shifts_*.csv'))
        assert reporter.csv_path == str(written[0])

    def test_a_run_with_no_reporter_still_completes(
        self, monkeypatch, tmp_path
    ):
        # The default discards events, so a caller that only wants the
        # CSV file passes nothing.
        self._serve_one_event(monkeypatch, tmp_path)

        GCALData(gcal_name='events')

        assert len(list(tmp_path.glob('gcal_shifts_*.csv'))) == 1


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
