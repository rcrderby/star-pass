#!/usr/bin/env python3
""" The gate in front of the things that cannot be undone (D11).

    A send writes into a live volunteer system and Amplify has no way
    to take a shift back, so somebody reads what is about to happen and
    says yes.  The confirmation's job is to make them read the summary,
    which is why it restates the count, the window and the
    opportunities on the line above the question rather than asking a
    bare "are you sure".

    A deletion is the second.  It destroys nothing Amplify holds -- a
    run that sent anything is refused one (D24) -- but what it destroys
    here is gone, so it is put the same way and restates the run it is
    about.  What cannot be undone is not always what reached Amplify.

    **A typed number was rejected** (D11): it tests typing rather than
    attention, and on a routine monthly task it becomes something the
    hands do while the eyes are elsewhere.

    **No answer is not yes.**  Where there is no terminal to answer
    from -- a script, a scheduled job, a pipe -- the send is refused
    rather than carried out, and no flag turns that into a yes.  A gate
    with a way around it is a gate somebody eventually goes around, and
    the thing on the other side of this one is irreversible.
"""

# Imports - Python Standard Library
import sys

# Imports - Local
from ._output import write

# What counts as yes.  Everything else, including an empty line, is
# no: the safe answer is the one somebody gets by pressing return
# without reading, and by pressing anything at all without meaning it.
AFFIRMATIVE = frozenset({'y', 'yes'})

# What the question ends with, so the safe answer is visibly the
# default one.
CHOICES = '[y/N]'

# What a caller is told when nothing can answer.  One for each thing
# asked about, because a caller told the wrong reason would go looking
# for a send that is not there.
NO_TERMINAL_TO_SEND = (
    'This command writes to Amplify and cannot be undone, so it asks '
    'first -- and there is no terminal here to ask. Run it where '
    'somebody can answer.'
)
NO_TERMINAL_TO_DELETE = (
    'This command deletes a run and cannot be undone, so it asks '
    'first -- and there is no terminal here to ask. Run it where '
    'somebody can answer.'
)


class ConfirmationUnavailable(Exception):
    """ There is nobody to ask, so the answer cannot be assumed.

        Raised rather than answered as a no, because the two are
        different things: a person who said no made a decision, and
        this is a command that could not put the question.
    """


def confirmed(
        question: str,
        unavailable: str
) -> bool:
    """ Put a question and return whether the answer was yes.

        Args:
            question (str):
                What to ask, without the choices, which are added.

            unavailable (str):
                What to say when there is nobody to ask, which names
                what was being asked about rather than leaving a
                caller to guess.

        Raises:
            ConfirmationUnavailable:
                If there is no terminal to answer from.

        Returns:
            answered (bool):
                Whether the answer was one of 'AFFIRMATIVE'.
    """

    if not sys.stdin.isatty():
        raise ConfirmationUnavailable(unavailable)

    write(f'{question} {CHOICES} ', end='')

    return input().strip().lower() in AFFIRMATIVE
