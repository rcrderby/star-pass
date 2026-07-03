""" Characterization tests for star_pass.gcal_data.GCALData.

    Focused on the pure time/offset math in _get_shift_time_data. The
    GCALData instance is created with auto_prep_data=False so that
    construction performs no network calls.
"""
# pylint: disable=missing-function-docstring,missing-class-docstring
# pylint: disable=protected-access,redefined-outer-name

# Imports - Third-Party
import pytest

# Imports - Local
from star_pass.gcal_data import GCALData


@pytest.fixture
def gcal() -> GCALData:
    # auto_prep_data=False prevents any Google Calendar API calls.
    return GCALData(gcal_name='practices', auto_prep_data=False)


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
