#!/usr/bin/env python3
""" Asking Amplify whether the credential this process holds works.

    The one thing the tool says about its own credential, so what
    these pin is mostly what it does **not** say: never the
    credential, never more of it than four characters, and nothing
    about the account behind it.

    The other half is that a credential Amplify refuses is an answer
    rather than a failure.  Whether it works is the question, and a
    caller who asked it should not have to read an exception to find
    out that the answer is no.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
from typing import Any, Callable, Dict, List

# Imports - Third-Party
import pytest

# Imports - Local
from star_pass._credentials import (
    check_credential,
    CREDENTIAL_VARIABLE,
    VISIBLE_CHARACTERS
)
from star_pass._exceptions import UpstreamError

# Constants
# What the suite configures, and the four characters of it a caller
# may see.  Read from the constant rather than written out twice, so
# the test is about the last four rather than about this value.
CONFIGURED = 'test-amplify-token'

# Written out rather than sliced from the value above: how much of a
# credential may be shown is a decision (D8), and a test that took the
# length from the code would agree with whatever the code did.
SHOWN = 'oken'

# What Amplify says when it will not take the credential, as the core
# words a refused request.
REFUSED = 'The request returned a bad status code (401): Unauthorized'


@pytest.fixture(name='amplify_refuses')
def fixture_amplify_refuses(
    monkeypatch: pytest.MonkeyPatch
) -> Callable[[], None]:
    """ Return a way to have Amplify reject every request. """

    def refuse() -> None:
        """ Raise what the core raises for a request it was refused. """

        def send(*_args: Any, **_kwargs: Any) -> None:
            """ Refuse one request. """
            raise UpstreamError(REFUSED)

        monkeypatch.setattr(
            'star_pass._helpers.Helpers.send_api_request',
            send
        )

    return refuse


class TestACredentialAmplifyAccepts:
    def test_it_is_reported_as_working(
        self,
        credential_accepted: List[Dict[str, Any]]
    ) -> None:
        del credential_accepted

        assert check_credential().working is True

    def test_its_last_four_characters_are_published(
        self,
        credential_accepted: List[Dict[str, Any]]
    ) -> None:
        del credential_accepted

        assert check_credential().last_four == SHOWN

    def test_four_is_how_many(
        self,
        credential_accepted: List[Dict[str, Any]]
    ) -> None:
        # The number is the decision, not an implementation detail:
        # four tell two credentials apart and are no use to anybody
        # else (D8).
        del credential_accepted

        assert VISIBLE_CHARACTERS == 4
        assert len(check_credential().last_four) == 4

    def test_nothing_more_of_it_is(
        self,
        credential_accepted: List[Dict[str, Any]]
    ) -> None:
        # The whole point of publishing four characters is that four
        # tell two credentials apart and are no use to anybody else.
        del credential_accepted

        assert CONFIGURED not in repr(check_credential())

    def test_a_working_credential_carries_no_reason(
        self,
        credential_accepted: List[Dict[str, Any]]
    ) -> None:
        del credential_accepted

        assert check_credential().reason is None


class TestTheRequestItIsCheckedWith:
    def test_one_request_is_sent(
        self,
        credential_accepted: List[Dict[str, Any]]
    ) -> None:
        check_credential()

        assert len(credential_accepted) == 1

    def test_it_reads_rather_than_writes(
        self,
        credential_accepted: List[Dict[str, Any]]
    ) -> None:
        check_credential()

        assert credential_accepted[0]['method'] == 'GET'
        assert credential_accepted[0]['json'] is None

    def test_it_asks_for_one_row(
        self,
        credential_accepted: List[Dict[str, Any]]
    ) -> None:
        # Smallest read there is: the body is discarded unread, and
        # what is being asked is whether the request was allowed.
        check_credential()

        assert credential_accepted[0]['params']['per_page'] == 1

    def test_it_carries_the_credential(
        self,
        credential_accepted: List[Dict[str, Any]]
    ) -> None:
        # Without which the answer would say nothing: an endpoint
        # reached anonymously proves only that Amplify is up.
        check_credential()

        assert CONFIGURED in credential_accepted[0]['headers']['Authorization']

    def test_it_names_no_need(
        self,
        credential_accepted: List[Dict[str, Any]]
    ) -> None:
        # A read of something the data model names would report a
        # deployment whose model matched nothing as a broken
        # credential.
        check_credential()

        assert 'needs' not in credential_accepted[0]['url']


class TestACredentialAmplifyRefuses:
    def test_it_is_reported_as_not_working(
        self,
        amplify_refuses: Callable[[], None]
    ) -> None:
        amplify_refuses()

        assert check_credential().working is False

    def test_the_refusal_is_answered_rather_than_raised(
        self,
        amplify_refuses: Callable[[], None]
    ) -> None:
        amplify_refuses()

        assert REFUSED in check_credential().reason

    def test_which_credential_was_refused_is_still_said(
        self,
        amplify_refuses: Callable[[], None]
    ) -> None:
        # A deployment told its credential does not work has to know
        # which one it was running on.
        amplify_refuses()

        assert check_credential().last_four == SHOWN


class TestNoCredentialAtAll:
    def test_it_is_reported_as_not_working(
        self,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv(CREDENTIAL_VARIABLE, raising=False)

        assert check_credential().working is False

    def test_there_are_no_characters_to_show(
        self,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv(CREDENTIAL_VARIABLE, raising=False)

        assert check_credential().last_four is None

    def test_the_reason_names_what_to_set(
        self,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv(CREDENTIAL_VARIABLE, raising=False)

        assert CREDENTIAL_VARIABLE in check_credential().reason

    def test_nothing_is_asked_of_amplify(
        self,
        credential_accepted: List[Dict[str, Any]],
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A request would be sent as "Bearer None" and refused, which
        # is the right answer reached the expensive way.
        monkeypatch.delenv(CREDENTIAL_VARIABLE, raising=False)

        check_credential()

        assert credential_accepted == []


class TestWhatIsLogged:
    def test_a_working_credential_is_logged_by_its_last_four(
        self,
        credential_accepted: List[Dict[str, Any]],
        caplog: pytest.LogCaptureFixture
    ) -> None:
        del credential_accepted

        check_credential()

        assert SHOWN in caplog.text
        assert CONFIGURED not in caplog.text

    def test_a_missing_credential_reaches_the_log(
        self,
        caplog: pytest.LogCaptureFixture,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv(CREDENTIAL_VARIABLE, raising=False)

        check_credential()

        assert CREDENTIAL_VARIABLE in caplog.text
