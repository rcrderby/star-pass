#!/usr/bin/env python3
""" How often one caller may ask for something.

    A window that slides, so what these pin is mostly what a fixed
    one would get wrong: that the allowance is counted over the last
    however-many seconds rather than reset on a boundary, that a
    refused attempt does not itself count, and that one caller's
    asking says nothing about another's.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
from typing import Any, Callable

# Imports - Third-Party
import pytest

# Imports - Local
from star_pass_api._limiting import RateLimit

# Constants
# A small allowance over a window long enough that nothing in these
# tests reaches the end of it by running.
ALLOWED = 3
WINDOW = 60.0

# Who is asking.
CALLER = 'static-token'
ANOTHER = 'somebody-else'


@pytest.fixture(name='clock')
def fixture_clock(
    monkeypatch: pytest.MonkeyPatch
) -> Callable[[float], None]:
    """ Return a way to move the clock the window is measured on.

        Moved rather than waited out: a test that slept for its window
        would be a slow test whose failure mode is a busy machine.
    """
    reading = [1000.0]
    monkeypatch.setattr(
        'star_pass_api._limiting.monotonic',
        lambda: reading[0]
    )

    def advance(seconds: float) -> None:
        """ Move it forward. """
        reading[0] += seconds

    return advance


@pytest.fixture(name='limit')
def fixture_limit(
    clock: Callable[[float], None]
) -> RateLimit:
    """ Return a limit of three attempts a minute, on a held clock. """
    del clock

    return RateLimit(allowed=ALLOWED, window_seconds=WINDOW)


def claim_all(limit: RateLimit, caller: str = CALLER) -> None:
    """ Use up one caller's whole allowance. """
    for _attempt in range(ALLOWED):
        assert limit.claim(caller=caller) is None


class TestWhatIsAllowed:
    def test_the_whole_allowance_goes_through(
        self,
        limit: RateLimit
    ) -> None:
        claim_all(limit=limit)

    def test_the_next_attempt_is_refused(
        self,
        limit: RateLimit
    ) -> None:
        claim_all(limit=limit)

        assert limit.claim(caller=CALLER) is not None

    def test_a_refusal_says_how_long_to_wait(
        self,
        clock: Callable[[float], None],
        limit: RateLimit
    ) -> None:
        # Measured from the oldest attempt still inside the window,
        # which is the one whose leaving makes room.
        claim_all(limit=limit)
        clock(WINDOW / 4)

        assert limit.claim(caller=CALLER) == pytest.approx(WINDOW * 0.75)


class TestHowTheWindowMoves:
    def test_an_attempt_that_ages_out_makes_room(
        self,
        clock: Callable[[float], None],
        limit: RateLimit
    ) -> None:
        claim_all(limit=limit)
        clock(WINDOW)

        assert limit.claim(caller=CALLER) is None

    def test_one_attempt_leaving_frees_exactly_one(
        self,
        clock: Callable[[float], None],
        limit: RateLimit
    ) -> None:
        # What a fixed window gets wrong: at its boundary it gives the
        # whole allowance back at once, which is twice the allowance
        # across the edge.  Here the attempts leave one at a time.
        limit.claim(caller=CALLER)
        clock(WINDOW / 2)
        limit.claim(caller=CALLER)
        limit.claim(caller=CALLER)
        clock(WINDOW / 2)

        assert limit.claim(caller=CALLER) is None
        assert limit.claim(caller=CALLER) is not None

    def test_a_refused_attempt_is_not_counted(
        self,
        clock: Callable[[float], None],
        limit: RateLimit
    ) -> None:
        # Counting it would mean a caller who kept asking never came
        # back inside the window, which is a lockout rather than a
        # limit.
        claim_all(limit=limit)
        clock(WINDOW / 2)

        for _refused in range(ALLOWED):
            limit.claim(caller=CALLER)

        clock(WINDOW / 2)

        assert limit.claim(caller=CALLER) is None


class TestWhoIsCounted:
    def test_one_caller_using_it_up_leaves_another_alone(
        self,
        limit: RateLimit
    ) -> None:
        claim_all(limit=limit)

        assert limit.claim(caller=ANOTHER) is None

    def test_a_caller_with_nothing_recent_is_forgotten(
        self,
        clock: Callable[[float], None],
        limit: RateLimit
    ) -> None:
        # Otherwise the count grows by one entry per caller for as
        # long as the process runs.
        claim_all(limit=limit)
        clock(WINDOW)

        limit.claim(caller=ANOTHER)

        # pylint: disable-next=protected-access
        held: Any = limit._attempts

        assert list(held) == [ANOTHER]
