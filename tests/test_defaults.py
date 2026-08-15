""" Tests for star_pass._defaults.

    The module reads every setting from the environment at import time,
    so the order of its statements is part of its behavior: a value read
    before the .env load ignores the file with no error to say so.
"""
# pylint: disable=missing-function-docstring,missing-class-docstring
# pylint: disable=redefined-outer-name

# Imports - Python Standard Library
import importlib

# Imports - Third-Party
# The real implementation, imported from where it is defined.  The
# suite stubs the 'dotenv.load_dotenv' name (see conftest) so no test
# reads a contributor's .env; the tests below restore the real function
# and point it at a temporary file, because the load is what they are
# about.
from dotenv.main import load_dotenv as real_load_dotenv
import dotenv
import pytest

# Imports - Local
from star_pass import _defaults


@pytest.fixture
def env_file(tmp_path, monkeypatch):
    # Run star_pass._defaults against a temporary .env.  ENV_FILE_PATH
    # is relative to the working directory, so changing directory is
    # what selects the file.
    monkeypatch.setattr(dotenv, 'load_dotenv', real_load_dotenv)
    monkeypatch.chdir(tmp_path)

    def write(contents: str):
        (tmp_path / '.env').write_text(contents, encoding='utf-8')
        return importlib.reload(_defaults)

    yield write

    # Restore the module for every later test, with the stub back in
    # place so the reload cannot read a real .env.
    monkeypatch.undo()
    importlib.reload(_defaults)


class TestEnvFileIsLoadedFirst:
    # Settings are read at import time, so the .env load has to happen
    # before the first read.  A setting read above it takes its default
    # and the file is silently ignored.

    def test_local_timezone_comes_from_the_env_file(
        self, env_file, monkeypatch
    ):
        # LOCAL_TIMEZONE decides which calendar day a summary covers and
        # how the search window is read, so a deployment that sets it in
        # .env and silently gets the default would collect the wrong
        # days.
        monkeypatch.delenv('LOCAL_TIMEZONE', raising=False)

        reloaded = env_file('LOCAL_TIMEZONE=America/New_York\n')

        assert reloaded.LOCAL_TIMEZONE == 'America/New_York'

    def test_the_process_environment_wins_over_the_file(
        self, env_file, monkeypatch
    ):
        # The file supplies a value; it does not override one already
        # set, which is what makes container and CI configuration work.
        monkeypatch.setenv('LOCAL_TIMEZONE', 'America/Denver')

        reloaded = env_file('LOCAL_TIMEZONE=America/New_York\n')

        assert reloaded.LOCAL_TIMEZONE == 'America/Denver'

    def test_the_default_still_applies_with_no_value_anywhere(
        self, env_file, monkeypatch
    ):
        monkeypatch.delenv('LOCAL_TIMEZONE', raising=False)

        reloaded = env_file('\n')

        assert reloaded.LOCAL_TIMEZONE == 'America/Los_Angeles'

    def test_no_setting_is_read_before_the_load(self):
        # A guard against reintroducing the ordering fault in a setting
        # other than LOCAL_TIMEZONE: every 'getenv' call in the module
        # has to appear after the 'load_dotenv' call.
        source = (
            _defaults.CURRENT_FILE_PATH / '_defaults.py'
        ).read_text(encoding='utf-8')
        lines = source.splitlines()

        load_line = next(
            number
            for number, text in enumerate(lines)
            if text.startswith('load_dotenv(')
        )
        early_reads = [
            f'{number + 1}: {text.strip()}'
            for number, text in enumerate(lines[:load_line])
            if 'getenv(' in text
        ]

        assert not early_reads
