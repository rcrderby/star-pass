#!/usr/bin/env python3
""" What both modes are asked for.

    A module of its own rather than the conftest beside it, because
    'conftest' is a name pytest gives to more than one file and a test
    importing from it would be importing whichever one a reader
    guessed at.
"""

# What both modes are asked to collect.
A_COLLECTION = {
    'calendar': 'events',
    'window': {'start': '2026-09-01', 'end': '2026-10-01'}
}

# A recollection of a run nothing has been done to since.
NO_CHANGES = {'expectedChangeCount': 0}

# What a run holding no events is asked to send.
NOTHING_TO_SEND = {'expectedShiftCount': 0}
