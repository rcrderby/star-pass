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

# Imports - Local
from star_pass.amplify_responses import (
    AmplifyResponses,
    count_signups_by_shift,
    _format_shift_when,
    _max_numeric_id,
    _response_created_dt,
    _upcoming_shifts,
)
from star_pass import _defaults

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


class TestFormatShiftWhen:
    def test_formats_datetimes(self):
        when = _format_shift_when(
            {
                'start': '2026-07-10 18:00:00',
                'end': '2026-07-10 20:45:00'
            }
        )
        assert when['start'] == '18:00'
        assert when['end'] == '20:45'
        assert 'July 10 2026' in when['name']

    def test_fallback_on_bad_input(self):
        when = _format_shift_when({'start': None, 'end': None})
        assert when['name'] == 'Shift'
        assert when['start'] is None


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

        result = _upcoming_shifts(shifts, NOW)

        assert [shift['id'] for shift in result] == ['SOON', 'LATER']

    def test_upcoming_shifts_includes_a_shift_starting_now(self):
        shifts = [_shift('NOW', '2026-07-14 09:00:00', '2026-07-14 10:00:00')]

        assert len(_upcoming_shifts(shifts, NOW)) == 1


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
            need_id='607934'
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
            need_id='1'
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
            need_id='1'
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


class TestBuildNeedSummary:
    def _reader_with(self, monkeypatch, need, responses, since_days=90):
        reader = AmplifyResponses(since_days=since_days)
        monkeypatch.setattr(reader, 'get_need', lambda need_id: need)
        monkeypatch.setattr(
            reader,
            'get_recent_responses',
            lambda since_created, need_id=None: responses
        )
        return reader

    def test_composes_live_counts(self, monkeypatch):
        need = {
            'need_title': 'Adult Scrimmage Officials',
            'shifts': [
                _shift('S1', '2026-07-20 18:00:00', '2026-07-20 20:45:00'),
                _shift('S2', '2026-07-21 18:00:00', '2026-07-21 20:45:00'),
            ]
        }
        reader = self._reader_with(monkeypatch, need, SAMPLE_RESPONSES)

        summary = reader.build_need_summary(need_id='628861', now=NOW)
        shifts = summary['shifts']

        assert summary['title'] == 'Adult Scrimmage Officials'
        assert 'as_of' in summary
        assert len(shifts) == 2
        # The inactive response is not counted.
        assert shifts[0]['filled'] == 2
        assert shifts[1]['filled'] == 1
        assert shifts[0]['slots'] == '8'
        assert shifts[0]['start'] == '18:00'
        assert 'July 20 2026' in shifts[0]['name']
        assert shifts[0]['signup_url'].endswith('?need_id=628861')

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
        reader = self._reader_with(monkeypatch, need, [])

        summary = reader.build_need_summary(need_id='1', now=NOW)

        assert len(summary['shifts']) == 1
        assert 'July 20 2026' in summary['shifts'][0]['name']

    def test_orders_shifts_by_start(self, monkeypatch):
        need = {
            'need_title': 'Unordered',
            'shifts': [
                _shift('B', '2026-07-22 18:00:00', '2026-07-22 19:00:00'),
                _shift('A', '2026-07-15 18:00:00', '2026-07-15 19:00:00'),
            ]
        }
        reader = self._reader_with(monkeypatch, need, [])

        summary = reader.build_need_summary(need_id='1', now=NOW)
        names = [shift['name'] for shift in summary['shifts']]

        assert 'July 15 2026' in names[0]
        assert 'July 22 2026' in names[1]

    def test_skips_shifts_with_unparseable_start(self, monkeypatch):
        need = {
            'need_title': 'Bad Data',
            'shifts': [
                _shift('BAD', 'not-a-date', 'not-a-date'),
                _shift('OK', '2026-07-20 18:00:00', '2026-07-20 19:00:00'),
            ]
        }
        reader = self._reader_with(monkeypatch, need, [])

        summary = reader.build_need_summary(need_id='1', now=NOW)

        assert len(summary['shifts']) == 1

    def test_empty_shift_defaults_to_zero(self, monkeypatch):
        need = {
            'need_title': 'Quiet Need',
            'shifts': [
                _shift('S9', '2026-07-20 18:00:00', '2026-07-20 20:45:00')
            ]
        }
        reader = self._reader_with(monkeypatch, need, [])

        summary = reader.build_need_summary(need_id='1', now=NOW)
        assert summary['shifts'][0]['filled'] == 0

    def test_title_override(self, monkeypatch):
        need = {'need_title': 'Default', 'shifts': []}
        reader = self._reader_with(monkeypatch, need, [])

        summary = reader.build_need_summary(
            need_id='1', title='Custom', now=NOW
        )
        assert summary['title'] == 'Custom'

    def test_passes_the_since_created_window(self, monkeypatch):
        # The window must be derived from 'now' and 'since_days'.
        reader = AmplifyResponses(since_days=90)
        monkeypatch.setattr(
            reader, 'get_need', lambda need_id: {'shifts': []}
        )
        captured = {}

        def fake_recent(since_created, need_id=None):
            captured['since_created'] = since_created
            captured['need_id'] = need_id
            return []

        monkeypatch.setattr(reader, 'get_recent_responses', fake_recent)

        reader.build_need_summary(need_id='607934', now=NOW)

        expected = (NOW - timedelta(days=90)).strftime('%Y-%m-%d %H:%M')
        assert captured['since_created'] == expected
        assert captured['need_id'] == '607934'


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
            lambda since_created, need_id=None: responses
        )
        return reader

    def test_warns_when_margin_is_thin(self, monkeypatch, caplog):
        # Cutoff is NOW - 90 days (2026-04-15); a sign-up created one day
        # later leaves almost no margin.
        reader = self._summary_with_response_created(
            monkeypatch, '2026-04-16 09:00:00'
        )

        with caplog.at_level('WARNING'):
            reader.build_need_summary(need_id='1', now=NOW)

        assert 'AMPLIFY_RESPONSES_SINCE_DAYS' in caplog.text

    def test_reports_healthy_margin(self, monkeypatch, caplog):
        # A sign-up created the day before 'now' sits far inside the
        # window, so no warning is emitted.
        reader = self._summary_with_response_created(
            monkeypatch, '2026-07-13 13:11:11'
        )

        with caplog.at_level('INFO'):
            reader.build_need_summary(need_id='1', now=NOW)

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
            lambda since_created, need_id=None: []
        )

        with caplog.at_level('INFO'):
            reader.build_need_summary(need_id='1', now=NOW)

        assert 'margin' not in caplog.text
