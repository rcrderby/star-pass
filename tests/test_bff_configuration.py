#!/usr/bin/env python3
""" The front end refusing to start on what it cannot work with.

    Everything it does needs the credential and the signing secret, so
    a process that started without one would answer page loads and
    fail every write.  Failing at startup is the difference between a
    deployment somebody fixes now and one somebody finds later.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring
# pylint: disable=protected-access

# Imports - Third-Party
import pytest

# Imports - Local
from _importing import imported_modules
from star_pass_bff import _defaults
from star_pass_bff._configuration import (
    check_configuration,
    ConfigurationError
)

# Constants
# Long enough to clear the minimum, and obviously not real. Named for
# its length rather than for what it is: bandit reads a constant's
# name, and one saying "secret" is one it stops on.
LONG_ENOUGH = 'test-star-pass-signing-value-not-a-real-one'


class TestWhatItRefusesToStartWithout:
    def test_a_credential_for_the_api(
        self,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(_defaults, 'API_TOKEN', None)

        with pytest.raises(ConfigurationError) as error:
            check_configuration()

        assert 'STAR_PASS_API_TOKEN' in str(error.value)

    def test_something_to_sign_a_session_with(
        self,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(_defaults, 'SESSION_SECRET', None)

        with pytest.raises(ConfigurationError) as error:
            check_configuration()

        assert 'STAR_PASS_SESSION_SECRET' in str(error.value)

    def test_a_signing_value_long_enough_to_be_generated(
        self,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Short enough to be typed is short enough to be guessed, and
        # this one is generated.
        monkeypatch.setattr(_defaults, 'SESSION_SECRET', 'short')

        with pytest.raises(ConfigurationError) as error:
            check_configuration()

        assert str(_defaults.SESSION_SECRET_MINIMUM_LENGTH) in str(
            error.value
        )

    def test_a_page_to_give_a_browser(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: pytest.TempPathFactory
    ) -> None:
        # Read the other way round from the two above: this service
        # exists to serve a page and to carry its session, so a
        # process with nothing behind the proxy is reachable and
        # unusable, and says so only to whoever opens it.
        monkeypatch.setattr(_defaults, 'WEB_ROOT', tmp_path)

        with pytest.raises(ConfigurationError) as error:
            check_configuration()

        assert _defaults.WEB_INDEX in str(error.value)
        assert str(tmp_path) in str(error.value)


class TestWhatItStartsWith:
    def test_a_credential_a_signing_value_and_a_page(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: pytest.TempPathFactory
    ) -> None:
        monkeypatch.setattr(_defaults, 'API_TOKEN', 'an-api-value')
        monkeypatch.setattr(_defaults, 'SESSION_SECRET', LONG_ENOUGH)
        # Written here rather than left to the checkout's own 'web'
        # directory, so the test says what it needs instead of passing
        # on something it did not arrange.
        (tmp_path / _defaults.WEB_INDEX).write_text(
            '<!DOCTYPE html>',
            encoding='utf-8'
        )
        monkeypatch.setattr(_defaults, 'WEB_ROOT', tmp_path)

        assert check_configuration() is None


class TestANumericSettingThatIsNotANumber:
    # The two numeric settings are read at import, so a typo in one
    # stops the service.  What it says when it does is the whole
    # point: a bare 'int()' names neither the variable nor where to
    # correct it, which reaches an operator as a traceback in a
    # detached container's log.

    @pytest.mark.parametrize(
        'var_name, bad',
        (
            ('STAR_PASS_SESSION_MAX_AGE_SECONDS', '432O0'),
            ('STAR_PASS_BFF_TIMEOUT_SECONDS', '12O')
        )
    )
    def test_it_is_named_along_with_its_value(
        self,
        monkeypatch: pytest.MonkeyPatch,
        var_name: str,
        bad: str
    ) -> None:
        monkeypatch.setenv(var_name, bad)

        with pytest.raises(ConfigurationError) as error:
            _defaults._number(
                var_name=var_name,
                default='1',
                kind=int,
                description='a whole number'
            )

        said = str(error.value)

        assert var_name in said
        assert bad in said
        assert '.env' in said

    def test_a_usable_value_is_read_as_its_kind(self) -> None:
        # A guard that refused everything would pass the test above
        # and stop the service starting at all.
        assert _defaults._number(
            var_name='STAR_PASS_NOT_SET_ANYWHERE',
            default='90',
            kind=int,
            description='a whole number'
        ) == 90

        assert _defaults._number(
            var_name='STAR_PASS_NOT_SET_ANYWHERE',
            default='9.5',
            kind=float,
            description='a number'
        ) == 9.5

    def test_the_settings_themselves_are_numbers(self) -> None:
        # The defaults have to survive the guard, or the service does
        # not start on a deployment that overrode nothing.
        assert isinstance(_defaults.SESSION_MAX_AGE_SECONDS, int)
        assert isinstance(_defaults.REQUEST_TIMEOUT_SECONDS, float)


class TestWhatItDoesNotImport:
    def test_nothing_of_the_domain(self) -> None:
        # The internet-facing process holds no domain logic and no
        # credential mount, and the import graph is where that
        # stays true rather than being a coding convention.
        loaded = imported_modules(statement='import star_pass_bff')

        assert 'star_pass' not in loaded

    def test_nothing_of_the_api_service_either(self) -> None:
        # Which is the same rule read the other way: importing the
        # service would bring the core with it.
        loaded = imported_modules(statement='import star_pass_bff')

        assert 'star_pass_api' not in loaded

    def test_it_is_importable_on_its_own(self) -> None:
        # A negative test alone would pass on a name that no longer
        # imports because it no longer exists.
        loaded = imported_modules(
            statement=(
                'from star_pass_bff import create_app\n'
                'assert create_app is not None'
            )
        )

        assert 'star_pass_bff' in loaded
