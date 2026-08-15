""" Tests for star_pass._models.

    The data models are read on first use rather than at import, so a
    bad one is an ordinary ConfigurationError raised by the call that
    needed it, not a print and an exit from an import.
"""
# pylint: disable=missing-function-docstring,missing-class-docstring
# pylint: disable=protected-access,redefined-outer-name

# Imports - Python Standard Library
import logging

# Imports - Third-Party
import pytest

# Imports - Local
from star_pass import _defaults, _models
from star_pass._exceptions import ConfigurationError


class TestDataModelsAreReadOnFirstUse:
    # Reading a file at import cannot report a failure usefully: it
    # happens before logging is configured and before a caller exists to
    # catch it.  Read on demand, a bad model is an ordinary
    # ConfigurationError.

    @pytest.fixture(autouse=True)
    def _clear_caches(self):
        # Each accessor caches its read, so a test that swaps the file
        # has to start from an unread state, and must not leave its
        # result behind for the next one.
        _models.get_shifts_info.cache_clear()
        _models._get_role_label_model.cache_clear()
        yield
        _models.get_shifts_info.cache_clear()
        _models._get_role_label_model.cache_clear()

    def test_the_shipped_shift_model_reads(self):
        assert 'calendar' in _models.get_shifts_info()

    def test_the_model_is_read_once(self, monkeypatch):
        # Cached, so a run that matches many titles does not re-read the
        # file for each one.
        reads = []
        monkeypatch.setattr(
            _models,
            '_read_model',
            lambda path, description: reads.append(path) or {'calendar': {}}
        )

        _models.get_shifts_info()
        _models.get_shifts_info()

        assert len(reads) == 1

    def test_a_missing_shift_model_is_a_configuration_error(
        self, monkeypatch, tmp_path, caplog
    ):
        monkeypatch.setattr(
            _defaults, 'SHIFTS_INFO_FILE', tmp_path / 'absent.yml'
        )

        with caplog.at_level(logging.ERROR, logger='star_pass'):
            with pytest.raises(ConfigurationError):
                _models.get_shifts_info()

        # Logged as well as raised, so the operator sees the path.
        assert 'absent.yml' in caplog.text

    def test_a_malformed_shift_model_is_a_configuration_error(
        self, monkeypatch, tmp_path, caplog
    ):
        bad = tmp_path / 'bad.yml'
        bad.write_text('calendar: [unclosed\n', encoding='utf-8')
        monkeypatch.setattr(_defaults, 'SHIFTS_INFO_FILE', bad)

        with caplog.at_level(logging.ERROR, logger='star_pass'):
            with pytest.raises(ConfigurationError):
                _models.get_shifts_info()

        assert 'not valid YAML' in caplog.text

    def test_the_role_label_model_is_optional(
        self, monkeypatch, tmp_path
    ):
        # Without it a summary keeps the full role text, which is
        # correct, only long.
        monkeypatch.setattr(
            _defaults, 'SLACK_ROLE_LABELS_FILE', tmp_path / 'absent.yml'
        )

        assert _models.get_slack_role_labels() == {}
        assert _models.get_slack_default_role_label() == 'Officials'

    def test_a_malformed_role_label_model_still_fails(
        self, monkeypatch, tmp_path
    ):
        # A file that exists is meant to be used.
        bad = tmp_path / 'bad.yml'
        bad.write_text('labels: [unclosed\n', encoding='utf-8')
        monkeypatch.setattr(_defaults, 'SLACK_ROLE_LABELS_FILE', bad)

        with pytest.raises(ConfigurationError):
            _models.get_slack_role_labels()
