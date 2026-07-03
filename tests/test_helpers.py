""" Characterization tests for star_pass._helpers.Helpers.

    These tests capture the *current* behavior of the helper methods so
    that later refactoring (Phase 2+) cannot change it unnoticed. Where
    current behavior differs from a method's docstring, the test asserts
    the real behavior and notes the discrepancy.
"""
# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Third-Party
import pytest


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
