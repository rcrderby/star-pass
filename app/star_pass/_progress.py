#!/usr/local/bin/python3
""" Terminal progress display.

    An Amplify sign-up summary spends most of its run waiting on the
    API: the responses endpoint has no server-side need or shift-date
    filter, so a run pages the whole domain's recent responses before it
    can count anything.  That is tens of seconds with nothing on screen.

    'Spinner' animates a one-line status while that work happens, and
    the caller updates the text as it advances, so the display reports
    where the run is rather than only that it is alive.

    The animation writes to stderr and only when stderr is a terminal.
    A scheduled run redirects its output, where carriage returns and
    animation frames would be noise in a log file.
"""

# Imports - Python Standard Library
import sys
import threading
from types import TracebackType
from typing import Optional, TextIO, Type

# Frames are ASCII on purpose.  A packaged Windows build writes to a
# console whose encoding cannot be relied on to carry Braille or box
# drawing characters.
SPINNER_FRAMES = ('-', '\\', '|', '/')

# Seconds between frames.
SPINNER_INTERVAL = 0.1


class Spinner:
    """ Animate a single line of progress text on a terminal. """

    def __init__(
            self,
            message: str = 'Working',
            stream: Optional[TextIO] = None,
            interval: float = SPINNER_INTERVAL,
            enabled: Optional[bool] = None
    ) -> None:
        """ Class initialization method.

            Args:
                message (str, optional):
                    Initial status text.  Default is 'Working'.

                stream (TextIO, optional):
                    Target for the animation.  Default 'None', which
                    resolves to the current 'sys.stderr' at call time so
                    that redirection is respected.

                interval (float, optional):
                    Seconds between frames.  Default is
                    'SPINNER_INTERVAL'.

                enabled (bool, optional):
                    Force the animation on or off.  Default 'None',
                    which enables it only when the stream is a terminal.

            Returns:
                None.
        """

        self.message = message
        self.interval = interval

        # Resolve the stream at call time rather than binding
        # 'sys.stderr' once as a default argument value.
        self._stream = stream if stream is not None else sys.stderr

        if enabled is None:
            # A stream without 'isatty' (a pytest capture object, for
            # example) is treated as not a terminal.
            enabled = bool(getattr(self._stream, 'isatty', bool)())
        self.enabled = enabled

        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._width = 0

        return None

    def update(
            self,
            message: str
    ) -> None:
        """ Replace the status text shown beside the animation.

            Args:
                message (str):
                    The new status text.

            Returns:
                None.
        """

        self.message = message

        return None

    def stop(
            self,
            clear: bool = True
    ) -> None:
        """ Halt the animation and wait for its thread to finish.

            Args:
                clear (bool, optional):
                    Erase the status line.  Default 'True', which leaves
                    the terminal as the run found it.

            Returns:
                None.
        """

        if self._thread is None:
            return None

        self._stop.set()
        self._thread.join()
        self._thread = None

        if clear is True:
            self._erase()

        return None

    def __enter__(self) -> 'Spinner':
        """ Start animating on entry to a 'with' block.

            Returns:
                spinner (Spinner):
                    This spinner.
        """

        if self.enabled is True:
            self._stop.clear()
            # A daemon thread cannot keep the interpreter alive if the
            # run exits before 'stop' is reached.
            self._thread = threading.Thread(
                target=self._spin,
                daemon=True
            )
            self._thread.start()

        return self

    def __exit__(
            self,
            exc_type: Optional[Type[BaseException]],
            exc_value: Optional[BaseException],
            traceback: Optional[TracebackType]
    ) -> None:
        """ Stop animating on exit, including when an error is raised.

            Args:
                exc_type (Type[BaseException] | None):
                    Type of any exception raised in the block.

                exc_value (BaseException | None):
                    Any exception raised in the block.

                traceback (TracebackType | None):
                    Traceback of any exception raised in the block.

            Returns:
                None.  Returning a false value lets an exception
                propagate, so a failure is never hidden by the display.
        """

        self.stop()

        return None

    def _write(
            self,
            text: str
    ) -> None:
        """ Write text to the stream, tolerating a closed stream.

            Args:
                text (str):
                    Content to write.

            Returns:
                None.
        """

        try:
            self._stream.write(text)
            self._stream.flush()
        except (ValueError, OSError):
            # The stream closed underneath the animation thread; the
            # display is cosmetic, so there is nothing to report.
            self.enabled = False

        return None

    def _erase(self) -> None:
        """ Clear the status line and return the cursor to its start.

            Returns:
                None.
        """

        if self._width:
            self._write(f'\r{" " * self._width}\r')
            self._width = 0

        return None

    def _spin(self) -> None:
        """ Animate until stopped.  Runs on the spinner's thread.

            Returns:
                None.
        """

        frame = 0

        while not self._stop.is_set():
            line = f'{SPINNER_FRAMES[frame]} {self.message}'
            frame = (frame + 1) % len(SPINNER_FRAMES)

            # Pad to the longest line written so far so that a shorter
            # message cannot leave characters behind.
            padding = max(self._width - len(line), 0)
            self._write(f'\r{line}{" " * padding}')
            self._width = max(self._width, len(line))

            self._stop.wait(self.interval)

        return None
