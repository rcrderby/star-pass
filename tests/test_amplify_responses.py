""" Unit tests for star_pass.amplify_responses.

    No network calls are made: helpers.send_api_request is monkeypatched
    (for the reader methods) or the network methods are replaced directly
    (for the summary-composition tests).
"""
# pylint: disable=missing-function-docstring,missing-class-docstring
# pylint: disable=protected-access,redefined-outer-name

# Imports - Python Standard Library
from datetime import datetime, timedelta
from unittest.mock import Mock
from zoneinfo import ZoneInfo

# Imports - Third-Party
import pytest

# Imports - Local
from star_pass.amplify_responses import (
    AmplifyResponses,
    count_signups_by_shift,
    _format_day_heading,
    _format_long_date,
    _format_short_date,
    _format_slot_when,
    _format_time_range,
    _max_numeric_id,
    _response_created_dt,
    _upcoming_shifts,
    local_now,
    _window_end,
    _window_title,
)
from star_pass import _defaults
from star_pass import amplify_responses

# Constants
PER_PAGE = _defaults.AMPLIFY_RESPONSES_PER_PAGE

# Two active responses on shift S1, one inactive on S1, one active on S2.
# Shared by the count and summary tests.
SAMPLE_RESPONSES = [
    {'response_status': 'active', 'shift': {'id': 'S1'}},
    {'response_status': 'active', 'shift': {'id': 'S1'}},
    {'response_status': 'inactive', 'shift': {'id': 'S1'}},
    {'response_status': 'active', 'shift': {'id': 'S2'}},
]

# A fixed 'now' keeps the upcoming-shift filter deterministic.
NOW = datetime(2026, 7, 14, 9, 0, 0)
# A window wide enough to reach every sample shift, used by the tests
# that exercise composition, ordering, and counting rather than the day
# window itself.  NOW is day one, so this reaches 2026-07-22.
WIDE_DAYS = 9
WIDE_WINDOW_END = datetime(2026, 7, 22, 23, 59, 59, 999999)


def _mock_response(payload: dict) -> Mock:
    # Stand-in for a requests.Response whose .json() returns the payload.
    response = Mock()
    response.json.return_value = payload
    return response


def _shift(shift_id: str, start: str, end: str, slots: str = '8') -> dict:
    # Minimal shift object in the shape GET /needs/{id} returns.
    return {'id': shift_id, 'start': start, 'end': end, 'slots': slots}


class TestCountSignupsByShift:
    def test_counts_active_only(self):
        responses = SAMPLE_RESPONSES
        assert count_signups_by_shift(responses) == {'S1': 2, 'S2': 1}

    def test_ignores_missing_shift_id(self):
        responses = [
            {'response_status': 'active', 'shift': {}},
            {'response_status': 'active'},
        ]
        assert not count_signups_by_shift(responses)

    def test_numeric_shift_ids_key_on_strings(self):
        # The API returns numeric IDs in some payloads; counts must key
        # on strings so the summary's lookups match.
        responses = [
            {'response_status': 'active', 'shift': {'id': 13345369}},
        ]
        assert count_signups_by_shift(responses) == {'13345369': 1}


class TestFormatTimeRange:
    def test_writes_the_meridiem_once_for_a_same_half_range(self):
        # How the posts are written by hand: "6:00-7:00 p.m.".
        when = _format_time_range(
            datetime(2025, 12, 17, 18, 0),
            datetime(2025, 12, 17, 19, 0)
        )
        assert when == '6:00-7:00 p.m.'

    def test_writes_both_when_the_range_crosses_noon(self):
        when = _format_time_range(
            datetime(2025, 12, 17, 11, 0),
            datetime(2025, 12, 17, 13, 30)
        )
        assert when == '11:00 a.m.-1:30 p.m.'

    def test_midnight_and_noon_read_correctly(self):
        assert _format_time_range(
            datetime(2025, 12, 17, 0, 0),
            datetime(2025, 12, 17, 0, 30)
        ) == '12:00-12:30 a.m.'
        assert _format_time_range(
            datetime(2025, 12, 17, 12, 0),
            datetime(2025, 12, 17, 12, 30)
        ) == '12:00-12:30 p.m.'


class TestFormatSlotWhen:
    def test_formats_the_time_range_only(self):
        # The date lives in the day heading, not on every line.
        when = _format_slot_when(
            _shift('S1', '2025-12-17 18:00:00', '2025-12-17 19:00:00')
        )
        assert when == '6:00-7:00 p.m.'

    def test_falls_back_to_the_raw_value_when_unparseable(self):
        when = _format_slot_when(_shift('S1', 'not-a-date', 'not-a-date'))
        assert when == 'not-a-date'

    def test_placeholder_without_a_start(self):
        assert _format_slot_when({'start': None, 'end': None}) == 'Time TBD'


class TestDateFormatting:
    def test_long_date_has_no_padded_day_and_a_comma(self):
        # Written the way a person would: "August 3, 2026", not
        # "August 03 2026".
        assert _format_long_date(datetime(2026, 8, 3)) == (
            'Monday, August 3, 2026'
        )

    def test_long_date_keeps_a_two_digit_day(self):
        assert _format_long_date(datetime(2025, 12, 17)) == (
            'Wednesday, December 17, 2025'
        )

    def test_short_date_omits_the_year(self):
        # The summary title already carries the year.
        assert _format_short_date(datetime(2026, 8, 5)) == (
            'Wednesday, August 5'
        )


class TestFormatDayHeading:
    def test_names_the_weekday_and_date(self):
        heading = _format_day_heading(
            _shift('S1', '2025-12-17 18:00:00', '2025-12-17 19:00:00')
        )
        assert heading == 'Wednesday, December 17'

    def test_empty_when_the_start_cannot_be_parsed(self):
        # An unreadable shift must not create a day heading of its own.
        assert _format_day_heading(
            _shift('S1', 'not-a-date', 'not-a-date')
        ) == ''


class TestLocalNow:
    def test_returns_a_naive_datetime(self, monkeypatch):
        # Amplify reports naive local datetimes, so the reference time
        # must be naive to stay comparable.
        monkeypatch.setattr(
            amplify_responses, 'LOCAL_TIMEZONE', 'America/Los_Angeles'
        )

        assert local_now().tzinfo is None

    def test_reads_the_configured_zone_not_the_host_clock(
            self, monkeypatch
    ):
        # The regression this guards: a container or CI runner in UTC
        # is already on tomorrow's date during a Portland evening, which
        # would move a same-day summary onto the wrong day.
        monkeypatch.setattr(amplify_responses, 'LOCAL_TIMEZONE', 'UTC')
        as_utc = local_now()
        monkeypatch.setattr(
            amplify_responses, 'LOCAL_TIMEZONE', 'America/Los_Angeles'
        )
        as_pacific = local_now()

        offset = abs((as_utc - as_pacific).total_seconds())
        # Pacific is 7 or 8 hours behind UTC, depending on the season.
        assert 7 * 3600 - 60 < offset < 8 * 3600 + 60

    def test_matches_the_zone_it_is_given(self, monkeypatch):
        monkeypatch.setattr(amplify_responses, 'LOCAL_TIMEZONE', 'UTC')
        expected = datetime.now(tz=ZoneInfo('UTC')).replace(tzinfo=None)

        assert abs((local_now() - expected).total_seconds()) < 5

    def test_unknown_zone_raises_a_clear_error(self, monkeypatch):
        monkeypatch.setattr(
            amplify_responses, 'LOCAL_TIMEZONE', 'Mars/Olympus_Mons'
        )

        with pytest.raises(ValueError, match='LOCAL_TIMEZONE'):
            local_now()


class TestHelperFunctions:
    def test_max_numeric_id_ignores_non_numeric(self):
        rows = [{'id': '10'}, {'id': 'abc'}, {'id': '42'}, {}]
        assert _max_numeric_id(rows) == 42

    def test_max_numeric_id_returns_none_without_numeric_ids(self):
        assert _max_numeric_id([{'id': 'abc'}, {}]) is None

    def test_response_created_accepts_either_field_name(self):
        live = {'created_at': '2026-07-13 13:11:11'}
        documented = {'response_date_added': '2026-07-13 13:11:11'}
        expected = datetime(2026, 7, 13, 13, 11, 11)
        assert _response_created_dt(live) == expected
        assert _response_created_dt(documented) == expected

    def test_response_created_returns_none_when_absent(self):
        assert _response_created_dt({}) is None

    def test_upcoming_shifts_filters_and_orders(self):
        shifts = [
            _shift('LATER', '2026-07-22 18:00:00', '2026-07-22 19:00:00'),
            _shift('PAST', '2026-07-01 18:00:00', '2026-07-01 19:00:00'),
            _shift('SOON', '2026-07-15 18:00:00', '2026-07-15 19:00:00'),
            _shift('BAD', 'not-a-date', 'not-a-date'),
        ]

        result = _upcoming_shifts(shifts, NOW, WIDE_WINDOW_END)

        assert [shift['id'] for shift in result] == ['SOON', 'LATER']

    def test_upcoming_shifts_includes_a_shift_starting_now(self):
        shifts = [_shift('NOW', '2026-07-14 09:00:00', '2026-07-14 10:00:00')]

        assert len(_upcoming_shifts(shifts, NOW, WIDE_WINDOW_END)) == 1

    def test_upcoming_shifts_excludes_a_shift_past_the_window(self):
        # The window's last instant is inclusive; the next one is not.
        shifts = [
            _shift('IN', '2026-07-22 23:59:59', '2026-07-23 01:00:00'),
            _shift('OUT', '2026-07-23 00:00:00', '2026-07-23 01:00:00'),
        ]

        result = _upcoming_shifts(shifts, NOW, WIDE_WINDOW_END)

        assert [shift['id'] for shift in result] == ['IN']

    def test_window_end_covers_the_rest_of_today(self):
        # Day one is today, so the window ends at today's last instant.
        assert _window_end(NOW, 1) == datetime(
            2026, 7, 14, 23, 59, 59, 999999
        )

    def test_window_end_counts_today_as_day_one(self):
        assert _window_end(NOW, 2) == datetime(
            2026, 7, 15, 23, 59, 59, 999999
        )

    def test_window_end_rejects_a_window_shorter_than_a_day(self):
        with pytest.raises(ValueError, match='at least one day'):
            _window_end(NOW, 0)

    def test_window_title_names_a_single_day(self):
        title = _window_title(NOW, _window_end(NOW, 1))

        assert title == 'Shift sign-ups for Tuesday, July 14, 2026'

    def test_window_title_names_a_date_range(self):
        title = _window_title(NOW, _window_end(NOW, 2))

        assert title == (
            'Shift sign-ups for Tuesday, July 14, 2026 - '
            'Wednesday, July 15, 2026'
        )


class TestGetRecentResponses:
    def _reader_with_pages(self, monkeypatch, pages):
        # Serve successive payloads, recording each request's params.
        reader = AmplifyResponses()
        calls = []
        remaining = list(pages)

        def fake_send(api_request_data, **_kwargs):
            calls.append(api_request_data)
            payload = remaining.pop(0) if remaining else {'data': []}
            return _mock_response(payload)

        monkeypatch.setattr(reader.helpers, 'send_api_request', fake_send)
        return reader, calls

    def test_sends_server_side_filters(self, monkeypatch):
        reader, calls = self._reader_with_pages(
            monkeypatch, [{'data': []}]
        )

        reader.get_recent_responses(since_created='2026-04-15 09:00')

        assert len(calls) == 1
        params = calls[0]['params']
        assert params['since_created'] == '2026-04-15 09:00'
        assert params['show_inactive'] == 'No'
        assert params['per_page'] == PER_PAGE
        # The first request has no cursor.
        assert 'since_id' not in params

    def test_filters_to_the_requested_need(self, monkeypatch):
        # The endpoint has no server-side need filter, so a page mixes
        # needs and the reader must keep only the target need's rows.
        page = {
            'data': [
                {'id': '1', 'need': {'id': '607934'}},
                {'id': '2', 'need': {'id': '999999'}},
                {'id': '3', 'need': {'id': 607934}},
                {'id': '4'},
            ]
        }
        reader, _calls = self._reader_with_pages(monkeypatch, [page])

        result = reader.get_recent_responses(
            since_created='2026-04-15 09:00',
            need_ids=['607934']
        )

        # Numeric and string need IDs both match; unrelated rows do not.
        assert [row['id'] for row in result] == ['1', '3']

    def test_keeps_every_row_without_a_need_filter(self, monkeypatch):
        page = {
            'data': [
                {'id': '1', 'need': {'id': '607934'}},
                {'id': '2', 'need': {'id': '999999'}},
            ]
        }
        reader, _calls = self._reader_with_pages(monkeypatch, [page])

        result = reader.get_recent_responses(
            since_created='2026-04-15 09:00'
        )

        assert len(result) == 2

    def test_pages_with_the_since_id_cursor(self, monkeypatch):
        # A full page must trigger another request carrying a since_id
        # cursor set to the page's largest ID; the short page ends it.
        full_page = {
            'data': [
                {'id': str(index), 'need': {'id': '1'}}
                for index in range(1, PER_PAGE + 1)
            ]
        }
        short_page = {'data': [{'id': '999', 'need': {'id': '1'}}]}
        reader, calls = self._reader_with_pages(
            monkeypatch, [full_page, short_page]
        )

        result = reader.get_recent_responses(
            since_created='2026-04-15 09:00',
            need_ids=['1']
        )

        assert len(calls) == 2
        assert 'since_id' not in calls[0]['params']
        assert calls[1]['params']['since_id'] == PER_PAGE
        assert len(result) == PER_PAGE + 1

    def test_stops_when_the_cursor_cannot_advance(self, monkeypatch):
        # A full page whose IDs are all non-numeric leaves the cursor
        # stuck; the reader must stop instead of looping forever.
        stuck_page = {
            'data': [
                {'id': 'abc', 'need': {'id': '1'}}
                for _ in range(PER_PAGE)
            ]
        }
        reader, calls = self._reader_with_pages(
            monkeypatch, [stuck_page, stuck_page, stuck_page]
        )

        result = reader.get_recent_responses(
            since_created='2026-04-15 09:00',
            need_ids=['1']
        )

        assert len(calls) == 1
        assert len(result) == PER_PAGE

    def test_missing_data_key_returns_empty(self, monkeypatch):
        reader, _calls = self._reader_with_pages(monkeypatch, [{}])

        result = reader.get_recent_responses(
            since_created='2026-04-15 09:00'
        )

        assert not result


class TestGetNeed:
    def test_returns_data(self, monkeypatch):
        reader = AmplifyResponses()
        response = _mock_response(
            {'data': {'need_title': 'X', 'shifts': []}}
        )
        monkeypatch.setattr(
            reader.helpers,
            'send_api_request',
            lambda **_kwargs: response
        )
        assert reader.get_need(need_id='42') == {
            'need_title': 'X',
            'shifts': []
        }


class TestBuildSummary:
    def _reader_with(self, monkeypatch, need, responses, since_days=90):
        reader = AmplifyResponses(since_days=since_days)
        monkeypatch.setattr(reader, 'get_need', lambda need_id: need)
        monkeypatch.setattr(
            reader,
            'get_recent_responses',
            lambda since_created, need_ids=None, progress=None: responses
        )
        return reader

    def _reader_for_needs(self, monkeypatch, needs, responses):
        # 'needs' maps need ID to the need object that ID returns.
        reader = AmplifyResponses(since_days=90)
        monkeypatch.setattr(
            reader, 'get_need', lambda need_id: needs[str(need_id)]
        )
        monkeypatch.setattr(
            reader,
            'get_recent_responses',
            lambda since_created, need_ids=None, progress=None: responses
        )
        return reader

    def _wide_summary(self, monkeypatch, need):
        # These tests cover composition, ordering, and counting; the day
        # window has its own tests, so it is opened wide here.
        reader = self._reader_with(monkeypatch, need, [])
        return reader.build_summary(
            need_ids=['1'], now=NOW, days=WIDE_DAYS
        )

    def _shifts_of(self, summary, index=0):
        return summary['needs'][index]['shifts']

    def test_composes_live_counts(self, monkeypatch):
        need = {
            'need_title': 'Adult Scrimmage Officials',
            'shifts': [
                _shift('S1', '2026-07-20 18:00:00', '2026-07-20 20:45:00'),
                _shift('S2', '2026-07-21 18:00:00', '2026-07-21 20:45:00'),
            ]
        }
        reader = self._reader_with(monkeypatch, need, SAMPLE_RESPONSES)

        summary = reader.build_summary(
            need_ids=['628861'], now=NOW, days=WIDE_DAYS
        )
        need_entry = summary['needs'][0]
        shifts = need_entry['shifts']

        # The default title names the window, not the need: a summary
        # can cover several needs at once.
        assert summary['title'].startswith('Shift sign-ups for')
        assert 'as_of' in summary
        assert need_entry['title'] == 'Adult Scrimmage Officials'
        assert need_entry['signup_url'].endswith('?need_id=628861')
        assert len(shifts) == 2
        # The inactive response is not counted.
        assert shifts[0]['filled'] == 2
        assert shifts[1]['filled'] == 1
        assert shifts[0]['when'] == '6:00-8:45 p.m.'
        assert shifts[0]['day'] == 'Monday, July 20'

    def test_covers_several_needs_in_one_summary(self, monkeypatch):
        needs = {
            '1': {
                'need_title': 'Adult Scrimmages - Non-Skating Officials',
                'shifts': [
                    _shift(
                        'S1',
                        '2026-07-14 19:00:00',
                        '2026-07-14 20:00:00'
                    )
                ]
            },
            '2': {
                'need_title': 'Adult Scrimmages - Skating Officials',
                'shifts': [
                    _shift(
                        'S2',
                        '2026-07-14 19:00:00',
                        '2026-07-14 20:00:00'
                    )
                ]
            }
        }
        responses = [
            {'response_status': 'active', 'shift': {'id': 'S1'}},
            {'response_status': 'active', 'shift': {'id': 'S2'}},
            {'response_status': 'active', 'shift': {'id': 'S2'}},
        ]
        reader = self._reader_for_needs(monkeypatch, needs, responses)

        summary = reader.build_summary(need_ids=['1', '2'], now=NOW)

        assert [need['title'] for need in summary['needs']] == [
            'Adult Scrimmages - Non-Skating Officials',
            'Adult Scrimmages - Skating Officials'
        ]
        assert self._shifts_of(summary, 0)[0]['filled'] == 1
        assert self._shifts_of(summary, 1)[0]['filled'] == 2

    def test_reads_responses_once_for_every_need(self, monkeypatch):
        # The responses endpoint has no server-side need filter, so it
        # pages the whole domain: one read must serve every need.
        needs = {
            str(index): {
                'need_title': f'Need {index}',
                'shifts': [
                    _shift(
                        f'S{index}',
                        '2026-07-14 19:00:00',
                        '2026-07-14 20:00:00'
                    )
                ]
            }
            for index in range(1, 6)
        }
        reader = AmplifyResponses(since_days=90)
        monkeypatch.setattr(
            reader, 'get_need', lambda need_id: needs[str(need_id)]
        )
        calls = []

        def fake_recent(**kwargs):
            calls.append(list(kwargs.get('need_ids') or []))
            return []

        monkeypatch.setattr(reader, 'get_recent_responses', fake_recent)

        reader.build_summary(
            need_ids=['1', '2', '3', '4', '5'], now=NOW
        )

        assert len(calls) == 1
        assert calls[0] == ['1', '2', '3', '4', '5']

    def test_omits_a_need_with_nothing_in_the_window(self, monkeypatch):
        # An opportunity with no shifts today contributes no lines and
        # no sign-up button.
        needs = {
            '1': {
                'need_title': 'Running Today',
                'shifts': [
                    _shift(
                        'S1',
                        '2026-07-14 19:00:00',
                        '2026-07-14 20:00:00'
                    )
                ]
            },
            '2': {
                'need_title': 'Nothing Today',
                'shifts': [
                    _shift(
                        'S2',
                        '2026-07-20 19:00:00',
                        '2026-07-20 20:00:00'
                    )
                ]
            }
        }
        reader = self._reader_for_needs(monkeypatch, needs, [])

        summary = reader.build_summary(need_ids=['1', '2'], now=NOW)

        assert [need['title'] for need in summary['needs']] == [
            'Running Today'
        ]

    def test_strips_whitespace_from_titles(self, monkeypatch):
        # Amplify titles are typed by hand; a stray trailing space would
        # split a group in two and ride into the button text.
        need = {
            'need_title': 'Adult Scrimmages: Non-Skating Officials ',
            'shifts': [
                _shift('S1', '2026-07-14 19:00:00', '2026-07-14 20:00:00')
            ]
        }
        reader = self._reader_with(monkeypatch, need, [])

        summary = reader.build_summary(need_ids=['1'], now=NOW)

        assert summary['needs'][0]['title'] == (
            'Adult Scrimmages: Non-Skating Officials'
        )

    def test_defaults_now_to_the_local_zone(self, monkeypatch):
        # Without this the day window follows the host clock, which is
        # UTC in a container and lands on the wrong calendar day.
        need = {'need_title': 'Anything', 'shifts': []}
        reader = self._reader_with(monkeypatch, need, [])
        called = []

        def fake_local_now():
            called.append(True)
            return NOW

        monkeypatch.setattr(
            amplify_responses, 'local_now', fake_local_now
        )

        reader.build_summary(need_ids=['1'])

        assert called

    def test_rejects_an_empty_need_list(self, monkeypatch):
        reader = self._reader_with(monkeypatch, {'shifts': []}, [])

        with pytest.raises(ValueError, match='At least one need ID'):
            reader.build_summary(need_ids=[], now=NOW)

    def test_multi_day_window_flags_day_headings(self, monkeypatch):
        need = {
            'need_title': 'Two Days',
            'shifts': [
                _shift('S1', '2026-07-14 19:00:00', '2026-07-14 20:00:00'),
                _shift('S2', '2026-07-15 19:00:00', '2026-07-15 20:00:00'),
            ]
        }
        reader = self._reader_with(monkeypatch, need, [])

        summary = reader.build_summary(
            need_ids=['1'], now=NOW, days=2
        )

        # The window spans days, so the message groups them under
        # headings; each shift carries the day it belongs under.
        assert summary['multi_day'] is True
        assert [shift['day'] for shift in self._shifts_of(summary)] == [
            'Tuesday, July 14',
            'Wednesday, July 15'
        ]

    def test_single_day_window_needs_no_day_headings(self, monkeypatch):
        # The title already names the day a heading would repeat.
        need = {
            'need_title': 'One Day',
            'shifts': [
                _shift('S1', '2026-07-14 19:00:00', '2026-07-14 20:00:00')
            ]
        }
        reader = self._reader_with(monkeypatch, need, [])

        summary = reader.build_summary(need_ids=['1'], now=NOW)

        assert summary['multi_day'] is False

    def test_excludes_past_shifts(self, monkeypatch):
        # A long-lived need carries hundreds of past shifts; only the
        # upcoming ones belong in a sign-up summary.
        need = {
            'need_title': 'Long-Lived Need',
            'shifts': [
                _shift('OLD', '2026-07-01 18:00:00', '2026-07-01 19:00:00'),
                _shift('NEW', '2026-07-20 18:00:00', '2026-07-20 19:00:00'),
            ]
        }
        summary = self._wide_summary(monkeypatch, need)

        assert len(self._shifts_of(summary)) == 1
        assert self._shifts_of(summary)[0]['sort_key'].startswith(
            '2026-07-20'
        )

    def test_orders_shifts_by_start(self, monkeypatch):
        need = {
            'need_title': 'Unordered',
            'shifts': [
                _shift('B', '2026-07-22 18:00:00', '2026-07-22 19:00:00'),
                _shift('A', '2026-07-15 18:00:00', '2026-07-15 19:00:00'),
            ]
        }
        summary = self._wide_summary(monkeypatch, need)
        keys = [shift['sort_key'] for shift in self._shifts_of(summary)]

        assert keys[0].startswith('2026-07-15')
        assert keys[1].startswith('2026-07-22')

    def test_skips_shifts_with_unparseable_start(self, monkeypatch):
        need = {
            'need_title': 'Bad Data',
            'shifts': [
                _shift('BAD', 'not-a-date', 'not-a-date'),
                _shift('OK', '2026-07-20 18:00:00', '2026-07-20 19:00:00'),
            ]
        }
        summary = self._wide_summary(monkeypatch, need)

        assert len(self._shifts_of(summary)) == 1

    def test_empty_shift_defaults_to_zero(self, monkeypatch):
        need = {
            'need_title': 'Quiet Need',
            'shifts': [
                _shift('S9', '2026-07-20 18:00:00', '2026-07-20 20:45:00')
            ]
        }
        summary = self._wide_summary(monkeypatch, need)
        assert self._shifts_of(summary)[0]['filled'] == 0

    def test_title_override(self, monkeypatch):
        need = {'need_title': 'Default', 'shifts': []}
        reader = self._reader_with(monkeypatch, need, [])

        summary = reader.build_summary(
            need_ids=['1'], title='Custom', now=NOW
        )
        assert summary['title'] == 'Custom'

    def test_defaults_to_today_only(self, monkeypatch):
        # The default window replaces the same-day post an admin used to
        # write by hand, so tomorrow's shift must not appear.
        need = {
            'need_title': 'Scrimmages',
            'shifts': [
                _shift('TODAY', '2026-07-14 18:00:00', '2026-07-14 19:00:00'),
                _shift(
                    'TOMORROW',
                    '2026-07-15 18:00:00',
                    '2026-07-15 19:00:00'
                )
            ]
        }
        reader = self._reader_with(monkeypatch, need, [])

        summary = reader.build_summary(need_ids=['1'], now=NOW)
        shifts = self._shifts_of(summary)

        assert len(shifts) == 1
        assert shifts[0]['sort_key'].startswith('2026-07-14')

    def test_two_days_reaches_tomorrow(self, monkeypatch):
        need = {
            'need_title': 'Scrimmages',
            'shifts': [
                _shift('TODAY', '2026-07-14 18:00:00', '2026-07-14 19:00:00'),
                _shift(
                    'TOMORROW',
                    '2026-07-15 18:00:00',
                    '2026-07-15 19:00:00'
                ),
                _shift('LATER', '2026-07-16 18:00:00', '2026-07-16 19:00:00')
            ]
        }
        reader = self._reader_with(monkeypatch, need, [])

        summary = reader.build_summary(need_ids=['1'], now=NOW, days=2)
        keys = [shift['sort_key'] for shift in self._shifts_of(summary)]

        assert len(keys) == 2
        assert keys[0].startswith('2026-07-14')
        assert keys[1].startswith('2026-07-15')

    def test_empty_window_yields_no_needs(self, monkeypatch):
        # A day with nothing scheduled is routine, not an error; the
        # caller decides not to post.
        need = {
            'need_title': 'Quiet Day',
            'shifts': [
                _shift('LATER', '2026-07-20 18:00:00', '2026-07-20 19:00:00')
            ]
        }
        reader = self._reader_with(monkeypatch, need, [])

        summary = reader.build_summary(need_ids=['1'], now=NOW)

        assert summary['needs'] == []
        assert summary['title']

    def test_rejects_a_window_shorter_than_a_day(self, monkeypatch):
        reader = self._reader_with(monkeypatch, {'shifts': []}, [])

        with pytest.raises(ValueError, match='at least one day'):
            reader.build_summary(
                need_ids=['1'], now=NOW, days=0
            )

    def test_passes_the_since_created_window(self, monkeypatch):
        # The window must be derived from 'now' and 'since_days'.
        reader = AmplifyResponses(since_days=90)
        monkeypatch.setattr(
            reader, 'get_need', lambda need_id: {'shifts': []}
        )
        captured = {}

        def fake_recent(since_created, need_ids=None, **_kwargs):
            captured['since_created'] = since_created
            captured['need_ids'] = need_ids
            return []

        monkeypatch.setattr(reader, 'get_recent_responses', fake_recent)

        reader.build_summary(
            need_ids=['607934'], now=NOW
        )

        expected = (NOW - timedelta(days=90)).strftime('%Y-%m-%d %H:%M')
        assert captured['since_created'] == expected
        assert list(captured['need_ids']) == ['607934']


class TestWindowMarginLogging:
    def _summary_with_response_created(self, monkeypatch, created_at):
        need = {
            'need_title': 'Margin',
            'shifts': [
                _shift('S1', '2026-07-20 18:00:00', '2026-07-20 19:00:00')
            ]
        }
        responses = [
            {
                'response_status': 'active',
                'shift': {'id': 'S1'},
                'created_at': created_at
            }
        ]
        reader = AmplifyResponses(since_days=90)
        monkeypatch.setattr(reader, 'get_need', lambda need_id: need)
        monkeypatch.setattr(
            reader,
            'get_recent_responses',
            lambda since_created, need_ids=None, progress=None: responses
        )
        return reader

    def test_warns_when_margin_is_thin(self, monkeypatch, caplog):
        # Cutoff is NOW - 90 days (2026-04-15); a sign-up created one day
        # later leaves almost no margin.
        reader = self._summary_with_response_created(
            monkeypatch, '2026-04-16 09:00:00'
        )

        with caplog.at_level('WARNING'):
            reader.build_summary(
                need_ids=['1'], now=NOW, days=WIDE_DAYS
            )

        assert 'AMPLIFY_RESPONSES_SINCE_DAYS' in caplog.text

    def test_reports_healthy_margin(self, monkeypatch, caplog):
        # A sign-up created the day before 'now' sits far inside the
        # window, so no warning is emitted.
        reader = self._summary_with_response_created(
            monkeypatch, '2026-07-13 13:11:11'
        )

        with caplog.at_level('INFO'):
            reader.build_summary(
                need_ids=['1'], now=NOW, days=WIDE_DAYS
            )

        assert 'margin is healthy' in caplog.text
        assert 'AMPLIFY_RESPONSES_SINCE_DAYS' not in caplog.text

    def test_silent_without_counted_signups(self, monkeypatch, caplog):
        need = {
            'need_title': 'Empty',
            'shifts': [
                _shift('S1', '2026-07-20 18:00:00', '2026-07-20 19:00:00')
            ]
        }
        reader = AmplifyResponses(since_days=90)
        monkeypatch.setattr(reader, 'get_need', lambda need_id: need)
        monkeypatch.setattr(
            reader,
            'get_recent_responses',
            lambda since_created, need_ids=None, progress=None: []
        )

        with caplog.at_level('INFO'):
            reader.build_summary(
                need_ids=['1'], now=NOW, days=WIDE_DAYS
            )

        assert 'margin' not in caplog.text
