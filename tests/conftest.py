""" Shared pytest configuration and fixtures.

    Sets dummy credentials/config in the environment *before* any
    star_pass module is imported, so import-time getenv() calls succeed
    and no test requires a real .env file or network access.
"""

# Imports - Python Standard Library
import os

# Imports - Third-Party
import dotenv

# Neutralize the .env load before star_pass is imported.
# 'star_pass._defaults' calls 'load_dotenv' at import time with a path
# relative to the working directory, so running pytest from a checkout
# that has a real .env let deployment settings decide test results: a
# value set there and read after the load (for example
# 'SLACK_SUMMARY_EMOJI') reached the code under test, and the suite
# passed in continuous integration -- where no .env exists -- while
# failing on a contributor's machine.  Stubbing the function here is
# what makes "tests require no .env" true rather than merely intended.
dotenv.load_dotenv = lambda *args, **kwargs: False

# Populate dummy environment variables prior to importing star_pass.
# Values are intentionally fake; no test may make a live API call.
os.environ.setdefault('AMPLIFY_TOKEN', 'test-amplify-token')
os.environ.setdefault('GCAL_TOKEN', 'test-gcal-token')
# Set so the run-mode credential preflight passes. Tests that exercise a
# missing credential delete the variable with monkeypatch.
os.environ.setdefault('SLACK_BOT_TOKEN', 'test-slack-not-a-real-token')
os.environ.setdefault('GCAL_WINDOW_START', '2099-01-01T00:00:00-00:00')
os.environ.setdefault('GCAL_WINDOW_END', '2099-01-31T00:00:00-00:00')

# Imports below intentionally follow the env setup above.
# pylint: disable=wrong-import-position

# Imports - Third-Party
import pytest  # noqa: E402

# Imports - Local
from star_pass._helpers import Helpers  # noqa: E402


@pytest.fixture
def helpers() -> Helpers:
    """ Return a fresh Helpers instance for each test. """
    return Helpers()
