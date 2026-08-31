#!/usr/bin/env python3
""" Stored state, reached only through these classes.

    Every statement that touches the database is in this package.  A
    caller asks for records and passes records back; it never builds a
    query, and no SQL appears outside these modules.

    One repository per thing with a lifetime of its own, and a module
    each.  The sent record and the idempotency reservations are two
    rather than one: they answer which rows a run has put into Amplify
    and what an already-made request answered, and a key covers many
    shifts, so neither is a column of the other.

    A run owns the opportunities it resolved, a revision owns its
    events, and an event owns its roles, so each is read and written
    whole.

    Times recorded here are ISO-8601 UTC.  A caller converts to the
    league's zone for display.
"""

# Imports - Local
from ._change_log import ChangeLogRepository
from ._events import EventRepository
from ._idempotency import IdempotencyRepository
from ._jobs import JobRepository
from ._revisions import RevisionRepository
from ._runs import RunRepository
from ._sent import SentShiftRepository
from ._uncollected import UncollectedRepository
from ._unmatched import UnmatchedTitleRepository

__all__ = [
    'ChangeLogRepository',
    'EventRepository',
    'IdempotencyRepository',
    'JobRepository',
    'RevisionRepository',
    'RunRepository',
    'SentShiftRepository',
    'UncollectedRepository',
    'UnmatchedTitleRepository'
]
