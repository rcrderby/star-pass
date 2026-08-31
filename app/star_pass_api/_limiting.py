#!/usr/bin/env python3
""" How often one caller may ask for something.

    In the service and not in the core: how often a thing may be asked
    for is a property of a public surface, and the command line client
    calling the same operation in this process is the operator asking
    their own machine a question.

    Held in memory rather than in the database.  What it protects is
    this process's own upstream requests, so a count that survived a
    restart would be describing requests a restarted process is not
    making, and a limiter that wrote a row per attempt would put a
    write in the path of an endpoint whose whole point is to be cheap.
    A deployment behind more than one process would need the count
    moved somewhere both could see; there is one.

    A window that slides rather than one that resets on the hour: a
    fixed window lets twice the allowance through across its edge,
    which is exactly the burst the limit exists to prevent.
"""

# Imports - Python Standard Library
from collections import deque
from threading import Lock
from time import monotonic
from typing import Deque, Dict, Optional


class RateLimit:
    """ A count of recent attempts per caller, and what it allows.

        Attributes:
            _allowed (int):
                How many attempts one caller may make in a window.

            _window (float):
                How long that window is, in seconds.

            _attempts (Dict[str, Deque[float]]):
                When each caller's recent attempts were made.

            _lock (Lock):
                Held while the count is read and written, because the
                service answers requests on more than one thread and
                two arriving together would otherwise both see the
                count before either had added to it.
    """

    def __init__(
            self,
            allowed: int,
            window_seconds: float
    ) -> None:
        """ Set up a limit nobody has yet been counted against.

            Args:
                allowed (int):
                    How many attempts one caller may make in a window.

                window_seconds (float):
                    How long the window is.

            Returns:
                None.
        """

        self._allowed = allowed
        self._window = window_seconds
        self._attempts: Dict[str, Deque[float]] = {}
        self._lock = Lock()

        return None

    def claim(
            self,
            caller: str
    ) -> Optional[float]:
        """ Count one attempt, or say how long until one is allowed.

            A refused attempt is not counted.  Counting it would mean
            a caller who kept asking never came back inside the
            window, which turns a limit into a lockout.

            Args:
                caller (str):
                    Who is asking, as the principal is identified.

            Returns:
                wait (float | None):
                    How many seconds until an attempt would be
                    allowed, or None when this one was.
        """

        now = monotonic()

        with self._lock:
            self._forget_the_quiet(now=now)
            recent = self._attempts.setdefault(caller, deque())

            if len(recent) >= self._allowed:
                return recent[0] + self._window - now

            recent.append(now)

        return None

    def _forget_the_quiet(
            self,
            now: float
    ) -> None:
        """ Drop attempts that have left the window, and empty callers.

            Every caller rather than only the one asking: an entry
            nobody clears is an entry that lives as long as the
            process, and a caller who asked once is exactly the caller
            who never comes back to clear their own.

            Args:
                now (float):
                    The reading of the clock this claim is being made
                    against.

            Returns:
                None.
        """

        expired = now - self._window

        for caller, recent in list(self._attempts.items()):
            while recent and recent[0] <= expired:
                recent.popleft()

            if not recent:
                del self._attempts[caller]

        return None
