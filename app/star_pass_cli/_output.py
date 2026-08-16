#!/usr/bin/env python3
""" Where rendered output goes.

    One primitive, used by everything in the command line client that
    writes: the reporter that renders a run's progress and the
    commands that render an answer.  Written once because the reason
    it is written that way is easy to lose.
"""

# Imports - Python Standard Library
import sys


def write(
        message: str,
        end: str = '\n'
) -> None:
    """ Write one piece of rendered output.

        Args:
            message (str):
                Text to write.

            end (str, optional):
                Appended after the message.  Defaults to a newline; an
                empty string leaves a status line open for the result
                that closes it.

        Returns:
            None.
    """

    # Resolve the stream at call time rather than binding it once, so
    # redirected output (pytest's capsys, a shell redirection) is
    # captured.
    print(message, end=end, file=sys.stdout)

    return None
