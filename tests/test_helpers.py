""" Characterization tests for star_pass._helpers.Helpers.

    These tests capture the *current* behavior of the helper methods so
    that later refactoring (Phase 2+) cannot change it unnoticed. Where
    current behavior differs from a method's docstring, the test asserts
    the real behavior and notes the discrepancy.
"""
# pylint: disable=missing-function-docstring,missing-class-docstring
# pylint: disable=protected-access

# Imports - Python Standard Library
import json
import logging
from pathlib import Path

# Imports - Third-Party
import pytest

# Imports - Local
from star_pass import _helpers


class TestConvertToBool:
    @pytest.mark.parametrize(
        'value, expected',
        [
            ('true', True),
            ('false', False),
            ('True', True),
            ('False', False),
            ('  TRUE  ', True),
            ('yes', True),
            ('y', True),
            ('t', True),
            ('1', True),
            ('no', False),
            ('n', False),
            ('f', False),
            ('0', False),
        ]
    )
    def test_valid_boolean_strings(self, helpers, value, expected):
        assert helpers.convert_to_bool(value) is expected

    @pytest.mark.parametrize(
        'value',
        ['maybe', 'flase', '', '2', 'tru', 'noo']
    )
    def test_invalid_input_raises_value_error(self, helpers, value):
        # Fail fast: a typo must never be silently coerced (e.g. so a
        # mistyped check_mode can't accidentally send live requests).
        with pytest.raises(ValueError):
            helpers.convert_to_bool(value)


class TestDateTimeFormatting:
    @pytest.mark.parametrize(
        'value, expected',
        [
            ('5/6/24 11:30', '2024-05-06 11:30'),
            ('6 may 2024 11:30 am', '2024-05-06 11:30'),
        ]
    )
    def test_format_date_time_amplify(self, helpers, value, expected):
        assert helpers.format_date_time_amplify(value) == expected

    def test_format_shift_date_simple(self, helpers):
        # NOTE: the '%d' directive zero-pads the day ('09'), unlike the
        # method docstring's 'April 9' example. Current behavior asserted.
        result = helpers.format_shift_date_simple('2025-04-09 11:30')
        assert result == 'Wednesday, April 09 2025'

    def test_format_shift_time_simple_adds_end_time(self, helpers):
        result = helpers.format_shift_time_simple('2025-04-09 11:30', '60')
        assert result == '11:30-12:30'


# Independent baseline of the need_ids each keyword resolved to before the
# data-model refactor, with the two documented fixes applied (hr, aoa ->
# standard adult_game). Keys are '<calendar>|<keyword>'.
_NEED_IDS_BASELINE = json.loads(
    (
        Path(__file__).resolve().parent
        / 'fixtures' / 'shift_need_ids_expected.json'
    ).read_text(encoding='utf-8')
)


class TestSearchShiftInfo:
    @pytest.mark.parametrize(
        'key, expected_need_ids',
        list(_NEED_IDS_BASELINE.items())
    )
    def test_need_ids_unchanged_after_refactor(
        self, helpers, key, expected_need_ids
    ):
        # Every historical keyword must still resolve to the same
        # need_ids after the data-model and matcher refactor.
        gcal_name, need_name = key.split('|', 1)
        result = helpers.search_shift_info(
            gcal_name=gcal_name,
            need_name=need_name
        )
        assert result['need_ids'] == expected_need_ids

    @pytest.mark.parametrize(
        'gcal_name, need_name, expected_description',
        [
            # Real event titles sampled from Google Calendar exports.
            ('events', 'GNR v HH', 'Adult Games'),
            (
                'events',
                'G1: Petals Exhibition Bout',
                'Rose Petals Games'
            ),
            ('practices', 'Officials', 'Adult Officiating Practices'),
            (
                'practices',
                'Adult HT Scrimmage: BB/HH',
                'Adult Scrimmages'
            ),
            ('practices', 'Wreckers A/B Scrimmage', 'Adult Scrimmages'),
            ('practices', 'Buds Mixed Scrimmage', 'Junior Scrimmages'),
            # Synthesized titles a human might reasonably use.
            ('events', 'Wheels of Justice vs Wreckers', 'Adult Games'),
            (
                'practices',
                'Junior Officials Practice',
                'Junior Officiating Practices'
            ),
            ('events', 'Petals Game Day', 'Rose Petals Games'),
            ('events', 'GnR vs BB Doubleheader', 'Adult Games'),
            (
                'practices',
                'Officials Training',
                'Adult Officiating Practices'
            ),
            (
                'practices',
                'Wreckers Contact Scrimmage',
                'Adult Scrimmages'
            ),
        ]
    )
    def test_realistic_event_name_matches(
        self, helpers, gcal_name, need_name, expected_description
    ):
        result = helpers.search_shift_info(
            gcal_name=gcal_name,
            need_name=need_name
        )
        assert result['description'] == expected_description

    def test_unmatched_title_routes_to_review(self, helpers, caplog):
        # A junior travel-team abbreviation with no alias must not be
        # guessed; it falls back to the review default and logs a
        # warning so the operator can add an alias.
        with caplog.at_level(logging.WARNING, logger='star_pass'):
            result = helpers.search_shift_info(
                gcal_name='events',
                need_name='G1: PTT v TBD'
            )

        assert result['description'] == 'Unknown Game'
        assert result['need_ids'][0]['id'] == ''
        assert 'review' in caplog.text.lower()


class TestRedactSecrets:
    @pytest.mark.parametrize(
        'text, secret',
        [
            (
                'https://www.googleapis.com/events?key=SUPERSECRET&x=1',
                'SUPERSECRET'
            ),
            (
                "{'Authorization': 'Bearer abc123.token'}",
                'abc123.token'
            ),
        ]
    )
    def test_secret_is_removed(self, helpers, text, secret):
        result = helpers.redact_secrets(text)
        assert secret not in result
        assert 'REDACTED' in result

    def test_preserves_the_label_prefix(self, helpers):
        result = helpers.redact_secrets('?key=SUPERSECRET&page=2')
        assert result == '?key=REDACTED&page=2'

    def test_ordinary_text_is_unchanged(self, helpers):
        text = 'HTTP 404 Not Found for /needs/123/shifts'
        assert helpers.redact_secrets(text) == text


class TestSendApiRequestRedaction:
    def test_error_repr_with_key_is_redacted(
            self, helpers, monkeypatch, caplog
    ):
        # 'sentinel' (not 'secret'/'token') avoids a false-positive
        # bandit B105 hardcoded-password finding on the test value.
        sentinel = 'TOPSECRET'

        def raise_conn_error(_self, **_kwargs):
            raise _helpers.exceptions.ConnectionError(
                f'Failed for url https://x/events?key={sentinel}'
            )

        # Force the session's HTTP call to raise, and capture the error
        # record that is logged before the program exits.
        monkeypatch.setattr(
            _helpers.Session, 'request', raise_conn_error
        )

        # The real exit_program raises SystemExit after logging.
        with caplog.at_level(logging.ERROR, logger='star_pass'):
            with pytest.raises(SystemExit):
                helpers.send_api_request(
                    api_request_data={
                        'method': 'GET',
                        'url': 'https://x/events',
                        'timeout': 3
                    }
                )

        assert sentinel not in caplog.text
        assert 'REDACTED' in caplog.text


class TestBuildSession:
    def test_session_retry_is_configured(self, helpers):
        session = helpers._build_session()
        retry = session.get_adapter('https://example.test').max_retries

        assert retry.total == 3
        assert retry.backoff_factor == 0.5
        assert 429 in retry.status_forcelist
        assert 503 in retry.status_forcelist

    def test_post_is_not_retried(self, helpers):
        # POST creates Amplify shifts; it must not be auto-retried on a
        # read error or bad status, which could duplicate a shift. The
        # urllib3 default allowed-methods set excludes POST.
        session = helpers._build_session()
        retry = session.get_adapter('https://example.test').max_retries

        assert 'POST' not in retry.allowed_methods
        assert 'GET' in retry.allowed_methods
