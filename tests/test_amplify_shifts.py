""" Tests for star_pass.amplify_shifts.CreateShifts.

    Two groups of tests:

    1. Input-file name handling, with CreateShifts constructed with
       auto_prep_data=False so that no CSV is read and no network call
       is made during __init__.
    2. The CSV-to-payload data pipeline, driven by a real CSV written to
       a tmp_path that replaces INPUT_DIR_PATH. The pipeline performs no
       network I/O, so auto_prep_data=True is safe here; create_new_shifts
       (the only method that sends requests) is never called.
"""
# pylint: disable=missing-function-docstring,missing-class-docstring
# pylint: disable=protected-access,redefined-outer-name
# '_json_shift_data' is initialized with 'data' set to None and filled in
# by the pipeline, so pylint infers the value as unsubscriptable even
# though it is a dictionary by the time these assertions run.
# pylint: disable=unsubscriptable-object

# Imports - Python Standard Library
import logging

# Imports - Third-Party
import pytest

# Imports - Local
from star_pass import amplify_shifts
from star_pass.amplify_shifts import CreateShifts

# A CSV header matching the columns written by GCALData.generate_shift_csv.
CSV_HEADER = 'need_name,need_id,start_date,start_time,duration,slots'


@pytest.fixture
def csv_dir(tmp_path, monkeypatch):
    # Redirect the input directory so tests write their own CSV files
    # instead of touching the repository's data/csv directory.
    monkeypatch.setattr(amplify_shifts, 'INPUT_DIR_PATH', tmp_path)
    return tmp_path


def _write_csv(csv_dir, rows, name='shifts.csv') -> str:
    # Write a CSV of shift rows and return its bare file name, which is
    # what CreateShifts expects as 'input_file'.
    content = '\n'.join([CSV_HEADER, *rows]) + '\n'
    (csv_dir / name).write_text(content, encoding='utf-8')
    return name


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
        # rstrip('.csv') would strip any trailing '.', 'c', 's', or
        # 'v' characters. removesuffix removes only the exact '.csv'
        # extension.
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


class TestDataPipeline:
    # CSV in, Amplify POST body out. Guards the whole transformation
    # chain.

    def test_builds_a_valid_grouped_payload(self, csv_dir):
        input_file = _write_csv(
            csv_dir,
            [
                'Adult Game A,879609,2099-01-01,12:00,60,12',
                'Adult Game A,879610,2099-01-01,12:00,60,8',
                'Adult Game B,879609,2099-01-02,18:00,90,12',
            ]
        )

        shifts = CreateShifts(input_file=input_file)

        # Rows are grouped by need ID, with the informational columns
        # dropped and the start date/time combined and reformatted.
        assert shifts._json_shift_data['data'] == {
            '879609': {
                'shifts': [
                    {
                        'start': '2099-01-01 12:00',
                        'duration': '60',
                        'slots': '12'
                    },
                    {
                        'start': '2099-01-02 18:00',
                        'duration': '90',
                        'slots': '12'
                    },
                ]
            },
            '879610': {
                'shifts': [
                    {
                        'start': '2099-01-01 12:00',
                        'duration': '60',
                        'slots': '8'
                    }
                ]
            },
        }
        # The payload also satisfies the JSON Schema.
        assert shifts._json_shift_data['valid'] is True
        assert shifts._json_shift_data['error'] is None

    def test_fully_duplicate_rows_are_removed(self, csv_dir):
        input_file = _write_csv(
            csv_dir,
            [
                'Adult Game A,879609,2099-01-01,12:00,60,12',
                'Adult Game A,879609,2099-01-01,12:00,60,12',
            ]
        )

        shifts = CreateShifts(input_file=input_file)

        assert len(shifts._json_shift_data['data']['879609']['shifts']) == 1

    def test_invalid_need_id_fails_schema_validation(self, csv_dir):
        # The schema requires a six-digit need ID; a shorter one must be
        # caught before any request is sent.
        input_file = _write_csv(
            csv_dir,
            ['Adult Game A,123,2099-01-01,12:00,60,12']
        )

        shifts = CreateShifts(input_file=input_file)

        assert shifts._json_shift_data['valid'] is False
        assert shifts._json_shift_data['error'] is not None


class TestValidateShiftRows:
    # An event title that matches no category in the shift data model
    # reaches the CSV with a blank need_id. groupby drops null keys, so
    # those rows would be discarded silently and their shifts never
    # created. The run must fail instead.

    def test_blank_need_id_exits_and_names_the_event(self, csv_dir, caplog):
        input_file = _write_csv(
            csv_dir,
            [
                'Adult Game A,879609,2099-01-01,12:00,60,12',
                'Jet City vs Cherry City,,2099-01-02,18:00,90,12',
            ]
        )

        with caplog.at_level(logging.ERROR, logger='star_pass'):
            with pytest.raises(SystemExit) as exc_info:
                CreateShifts(input_file=input_file)

        assert exc_info.value.code == 1
        # The operator needs the event title, the CSV line, and the file
        # to edit in order to act on the error.
        assert 'Jet City vs Cherry City' in caplog.text
        assert 'line 3' in caplog.text
        assert 'shift_info.yml' in caplog.text
        # The row that did match must not be blamed.
        assert 'Adult Game A' not in caplog.text

    def test_whitespace_only_need_id_is_blank(self, csv_dir, caplog):
        input_file = _write_csv(
            csv_dir,
            ['Unmatched Event,   ,2099-01-01,12:00,60,12']
        )

        with caplog.at_level(logging.ERROR, logger='star_pass'):
            with pytest.raises(SystemExit):
                CreateShifts(input_file=input_file)

        assert 'Unmatched Event' in caplog.text

    def test_reports_every_blank_row(self, csv_dir, caplog):
        input_file = _write_csv(
            csv_dir,
            [
                'First Unmatched,,2099-01-01,12:00,60,12',
                'Adult Game A,879609,2099-01-01,12:00,60,12',
                'Second Unmatched,,2099-01-03,18:00,90,12',
            ]
        )

        with caplog.at_level(logging.ERROR, logger='star_pass'):
            with pytest.raises(SystemExit):
                CreateShifts(input_file=input_file)

        assert '2 shift row(s)' in caplog.text
        assert 'First Unmatched' in caplog.text
        assert 'Second Unmatched' in caplog.text

    def test_input_file_errors_are_reported(self, csv_dir, caplog):
        # A mistyped -i value is an operator error, not a bug, so the
        # path is named instead of raising from inside pandas.
        with caplog.at_level(logging.ERROR, logger='star_pass'):
            with pytest.raises(SystemExit) as exc_info:
                CreateShifts(input_file='does_not_exist.csv')

        assert exc_info.value.code == 1
        assert 'does_not_exist.csv' in caplog.text
        assert csv_dir is not None

    def test_missing_columns_are_named(self, csv_dir, caplog):
        # The file is hand-edited, so a renamed column is expected
        # input and must be named rather than raising a bare KeyError.
        path = csv_dir / 'bad_columns.csv'
        path.write_text(
            'need_name,need_id,start_date,start_time\n'
            'Adult Game A,879609,2099-01-01,12:00\n',
            encoding='utf-8'
        )

        with caplog.at_level(logging.ERROR, logger='star_pass'):
            with pytest.raises(SystemExit):
                CreateShifts(input_file='bad_columns.csv')

        assert 'duration' in caplog.text
        assert 'slots' in caplog.text

    def test_unparseable_start_is_named(self, csv_dir, caplog):
        # 'dateparser.parse' returns None rather than raising.
        input_file = _write_csv(
            csv_dir,
            ['Adult Game A,879609,not-a-date,99:99,60,12']
        )

        with caplog.at_level(logging.ERROR, logger='star_pass'):
            with pytest.raises(SystemExit) as exc_info:
                CreateShifts(input_file=input_file)

        assert exc_info.value.code == 1
        assert 'not-a-date' in caplog.text

    def test_complete_data_does_not_exit(self, csv_dir, caplog):
        input_file = _write_csv(
            csv_dir,
            ['Adult Game A,879609,2099-01-01,12:00,60,12']
        )

        with caplog.at_level(logging.ERROR, logger='star_pass'):
            shifts = CreateShifts(input_file=input_file)

        assert shifts._json_shift_data['valid'] is True
        assert not caplog.text
