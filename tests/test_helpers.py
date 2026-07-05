""" Characterization tests for star_pass._helpers.Helpers.

    These tests capture the *current* behavior of the helper methods so
    that later refactoring (Phase 2+) cannot change it unnoticed. Where
    current behavior differs from a method's docstring, the test asserts
    the real behavior and notes the discrepancy.
"""
# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
import logging

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


class TestSearchShiftInfo:
    @pytest.mark.parametrize(
        'gcal_name, need_name, expected_description',
        [
            ('practices', 'Adult Scrimmage', 'Adult Scrimmages'),
            (
                'practices',
                'WoJ Scrimmage',
                'Wheels of Justice (WoJ) Scrimmages'
            ),
            ('events', 'AoA vs BNB', 'Axles of Annihilation (AoA) Games'),
        ]
    )
    def test_best_match_description(
        self, helpers, gcal_name, need_name, expected_description
    ):
        result = helpers.search_shift_info(
            gcal_name=gcal_name,
            need_name=need_name
        )
        assert result['description'] == expected_description


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

        def raise_conn_error(**_kwargs):
            raise _helpers.exceptions.ConnectionError(
                f'Failed for url https://x/events?key={sentinel}'
            )

        # Force the HTTP call to raise, and capture the error record
        # that is logged before the program exits.
        monkeypatch.setattr(_helpers, 'request', raise_conn_error)

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
