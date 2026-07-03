""" Tests for star_pass.amplify_shifts.CreateShifts.

    Focused on input-file name handling. CreateShifts is constructed
    with auto_prep_data=False so that no CSV is read and no network
    call is made during __init__.
"""
# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Local
from star_pass.amplify_shifts import CreateShifts


class TestBaseFileName:
    def test_strips_csv_suffix(self):
        shifts = CreateShifts(
            input_file='gcal_shifts_2099-01-01T00_00_00_000000.csv',
            auto_prep_data=False
        )
        assert shifts.base_file_name == (
            'gcal_shifts_2099-01-01T00_00_00_000000'
        )

    def test_only_removes_the_suffix_not_a_character_set(self):
        # Regression for the previous rstrip('.csv') bug, which stripped
        # any trailing '.', 'c', 's', or 'v' characters. removesuffix
        # must remove only the exact '.csv' extension.
        shifts = CreateShifts(
            input_file='shifts_scv.csv',
            auto_prep_data=False
        )
        assert shifts.base_file_name == 'shifts_scv'

    def test_output_file_uses_json_extension(self):
        shifts = CreateShifts(
            input_file='shifts_scv.csv',
            auto_prep_data=False
        )
        assert shifts.output_file.name == 'shifts_scv.json'
