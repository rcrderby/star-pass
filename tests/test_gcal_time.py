""" Tests for star_pass._gcal_time.resolve_window.

    A run carries its own search window, so the bounds arrive as
    arguments.  What is pinned here is how a bound is read: a value
    without a UTC offset is local time in 'GCAL_TIMEZONE', and the zone
    supplies the offset in effect on that date.  Writing the window in
    UTC instead shifts it eight hours earlier in winter, which drops
    evening events on its final day.
"""
# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Third-Party
import pytest

# Imports - Local
from star_pass._gcal_time import resolve_window

# What a caller names its two bounds.  'star_pass._collect' passes
# these, so a message a test asserts is one an operator would read.
START_NAME = 'the window start'
END_NAME = 'the window end'


def _resolve(start: str, end: str):
    return resolve_window(
        start=start,
        end=end,
        start_name=START_NAME,
        end_name=END_NAME
    )


class TestTheZoneAppliedToAnOffsetLessValue:
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

        window_start, _window_end = _resolve(date_value, '2099-01-01')

        assert window_start == f'{date_value}T00:00:00{expected_offset}'

    def test_a_plain_date_starts_at_local_midnight(self, monkeypatch):
        # The whole point: a plain date must not drift into the previous
        # day, which is what a UTC-written window does in winter.
        monkeypatch.delenv('GCAL_TIMEZONE', raising=False)

        assert _resolve('2026-01-01', '2026-02-01') == (
            '2026-01-01T00:00:00-08:00',
            '2026-02-01T00:00:00-08:00'
        )

    def test_accepts_a_local_datetime(self, monkeypatch):
        monkeypatch.delenv('GCAL_TIMEZONE', raising=False)

        window_start, _window_end = _resolve(
            '2026-07-01T09:30:00', '2026-08-01'
        )

        assert window_start == '2026-07-01T09:30:00-07:00'

    def test_honors_a_value_that_carries_its_own_offset(self, monkeypatch):
        # An explicit offset is used as written, whatever the zone says.
        monkeypatch.setenv('GCAL_TIMEZONE', 'America/Los_Angeles')

        window_start, _window_end = _resolve(
            '2026-01-01T00:00:00-05:00', '2026-02-01'
        )

        assert window_start == '2026-01-01T00:00:00-05:00'

    def test_honors_a_different_time_zone(self, monkeypatch):
        monkeypatch.setenv('GCAL_TIMEZONE', 'America/New_York')

        window_start, _window_end = _resolve('2026-01-01', '2026-02-01')

        assert window_start == '2026-01-01T00:00:00-05:00'

    def test_raises_on_an_unknown_time_zone(self, monkeypatch):
        monkeypatch.setenv('GCAL_TIMEZONE', 'Mars/Olympus_Mons')

        with pytest.raises(ValueError, match='not a known time zone'):
            _resolve('2026-01-01', '2026-02-01')


class TestAWindowThatCannotBeUsed:
    @pytest.mark.parametrize(
        'bad_value',
        ['not-a-date', '2099-13-01', '']
    )
    def test_raises_on_an_unparseable_value(self, monkeypatch, bad_value):
        monkeypatch.delenv('GCAL_TIMEZONE', raising=False)

        with pytest.raises(ValueError) as error:
            _resolve(bad_value, '2099-02-01')

        # The caller's own name for the bound, so a reader is told which
        # of their two values is the wrong one.
        assert START_NAME in str(error.value)

    def test_names_the_end_when_the_end_is_the_bad_one(self, monkeypatch):
        monkeypatch.delenv('GCAL_TIMEZONE', raising=False)

        with pytest.raises(ValueError) as error:
            _resolve('2099-01-01', 'not-a-date')

        assert END_NAME in str(error.value)

    def test_raises_when_the_window_does_not_move_forward(self, monkeypatch):
        monkeypatch.delenv('GCAL_TIMEZONE', raising=False)

        with pytest.raises(ValueError, match='must be earlier than'):
            _resolve('2099-02-01', '2099-01-01')

    def test_raises_when_the_window_is_empty(self, monkeypatch):
        # Equal bounds select nothing, which collects zero events.
        monkeypatch.delenv('GCAL_TIMEZONE', raising=False)

        with pytest.raises(ValueError, match='must be earlier than'):
            _resolve('2099-01-01', '2099-01-01')

    def test_orders_a_window_that_mixes_local_and_offset_values(
            self, monkeypatch
    ):
        # 00:00-08:00 is 08:00 UTC, so a UTC bound of 04:00 the same day
        # is earlier than a local midnight and must be rejected.
        monkeypatch.delenv('GCAL_TIMEZONE', raising=False)

        with pytest.raises(ValueError, match='must be earlier than'):
            _resolve('2026-01-01', '2026-01-01T04:00:00+00:00')
