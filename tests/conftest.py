""" Shared pytest configuration and fixtures.

    Sets dummy credentials/config in the environment *before* any
    star_pass module is imported, so import-time getenv() calls succeed
    and no test requires a real .env file or network access.
"""

# Imports - Python Standard Library
import os

# Populate dummy environment variables prior to importing star_pass.
# Values are intentionally fake; no test may make a live API call.
os.environ.setdefault('AMPLIFY_TOKEN', 'test-amplify-token')
os.environ.setdefault('GCAL_TOKEN', 'test-gcal-token')
os.environ.setdefault('GCAL_TIME_MIN', '2099-01-01T00:00:00-00:00')
os.environ.setdefault('GCAL_TIME_MAX', '2099-01-31T00:00:00-00:00')

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
