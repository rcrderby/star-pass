""" Unit tests for star_pass.amplify_responses.

    No network calls are made: helpers.send_api_request is monkeypatched
    (for the reader methods) or the network methods are replaced directly
    (for the summary-composition test).
"""
# pylint: disable=missing-function-docstring,missing-class-docstring
# pylint: disable=protected-access,redefined-outer-name

# Imports - Python Standard Library
from unittest.mock import Mock

# Imports - Local
from star_pass.amplify_responses import (
    AmplifyResponses,
    count_signups_by_shift,
    _format_shift_when,
)


def _mock_response(payload: dict) -> Mock:
    # Stand-in for a requests.Response whose .json() returns the payload.
    response = Mock()
    response.json.return_value = payload
    return response


# Two active responses on shift S1, one inactive on S1, one active on S2.
# Shared by the count and summary tests.
SAMPLE_RESPONSES = [
    {'response_status': 'active', 'shift': {'id': 'S1'}},
    {'response_status': 'active', 'shift': {'id': 'S1'}},
    {'response_status': 'inactive', 'shift': {'id': 'S1'}},
    {'response_status': 'active', 'shift': {'id': 'S2'}},
]


class TestCountSignupsByShift:
    def test_counts_active_only(self):
        responses = SAMPLE_RESPONSES
        assert count_signups_by_shift(responses) == {'S1': 2, 'S2': 1}

    def test_ignores_missing_shift_id(self):
        responses = [
            {'response_status': 'active', 'shift': {}},
            {'response_status': 'active'},
        ]
        assert count_signups_by_shift(responses) == {}


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


class TestGetNeedResponses:
    def test_follows_meta_last_page(self, monkeypatch):
        reader = AmplifyResponses()
        pages = [
            _mock_response(
                {'data': [{'id': 'r1'}], 'meta': {'last_page': 2}}
            ),
            _mock_response(
                {'data': [{'id': 'r2'}], 'meta': {'last_page': 2}}
            ),
        ]
        seen_pages = []

        def fake_send(api_request_data, **_kwargs):
            seen_pages.append(api_request_data['params']['page'])
            return pages[len(seen_pages) - 1]

        monkeypatch.setattr(
            reader.helpers, 'send_api_request', fake_send
        )

        result = reader.get_need_responses(need_id='123')
        assert result == [{'id': 'r1'}, {'id': 'r2'}]
        assert seen_pages == [1, 2]

    def test_stops_on_short_page(self, monkeypatch):
        reader = AmplifyResponses()
        # One item is fewer than a full page and there is no meta, so the
        # loop stops after a single request.
        response = _mock_response({'data': [{'id': 'r1'}]})
        calls = []

        def fake_send(api_request_data, **_kwargs):
            calls.append(api_request_data['params']['page'])
            return response

        monkeypatch.setattr(
            reader.helpers, 'send_api_request', fake_send
        )

        result = reader.get_need_responses(need_id='123')
        assert result == [{'id': 'r1'}]
        assert calls == [1]


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
    def _reader_with(self, monkeypatch, need, responses):
        reader = AmplifyResponses()
        monkeypatch.setattr(reader, 'get_need', lambda need_id: need)
        monkeypatch.setattr(
            reader, 'get_need_responses', lambda need_id: responses
        )
        return reader

    def test_composes_live_counts(self, monkeypatch):
        need = {
            'need_title': 'Adult Scrimmage Officials',
            'shifts': [
                {
                    'id': 'S1',
                    'start': '2026-07-10 18:00:00',
                    'end': '2026-07-10 20:45:00',
                    'slots': '8'
                },
                {
                    'id': 'S2',
                    'start': '2026-07-11 18:00:00',
                    'end': '2026-07-11 20:45:00',
                    'slots': '8'
                },
            ]
        }
        responses = SAMPLE_RESPONSES
        reader = self._reader_with(monkeypatch, need, responses)

        summary = reader.build_need_summary(need_id='628861')
        shifts = summary['shifts']

        assert summary['title'] == 'Adult Scrimmage Officials'
        assert 'as_of' in summary
        assert len(shifts) == 2
        # Inactive response is not counted.
        assert shifts[0]['filled'] == 2
        assert shifts[1]['filled'] == 1
        assert shifts[0]['slots'] == '8'
        assert shifts[0]['start'] == '18:00'
        assert 'July 10 2026' in shifts[0]['name']
        assert shifts[0]['signup_url'].endswith('?need_id=628861')

    def test_empty_shift_defaults_to_zero(self, monkeypatch):
        need = {
            'need_title': 'Quiet Need',
            'shifts': [
                {
                    'id': 'S9',
                    'start': '2026-07-10 18:00:00',
                    'end': '2026-07-10 20:45:00',
                    'slots': '8'
                }
            ]
        }
        reader = self._reader_with(monkeypatch, need, [])

        summary = reader.build_need_summary(need_id='1')
        assert summary['shifts'][0]['filled'] == 0

    def test_title_override(self, monkeypatch):
        need = {'need_title': 'Default', 'shifts': []}
        reader = self._reader_with(monkeypatch, need, [])

        summary = reader.build_need_summary(need_id='1', title='Custom')
        assert summary['title'] == 'Custom'
