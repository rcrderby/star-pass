#!/usr/bin/env python3
""" Stored state, reached only through these classes.

    Every statement that touches the database is in this package.  A
    caller asks for records and passes records back; it never builds a
    query, and no SQL appears outside these modules.  That is what keeps
    the core testable without a database and what keeps a move to
    another one contained: the queries change, and nothing that calls
    them does.

    One repository per thing that has a lifetime of its own, and a
    module each, because the layer is still growing: jobs, the record of
    what was sent and the idempotency keys join it when the endpoints
    that use them are written, and a single module holding all of them
    would not stay readable.

    A run owns the opportunities it resolved, so those live with it; a
    revision owns the events in it, and an event owns its roles, so each
    is read and written whole rather than a piece at a time.

    Times the layer records are ISO-8601 UTC.  A caller that displays
    one converts it to the league's own time zone, which is also why
    nothing here reads the host clock for a calendar day: the record of
    when something happened is an instant, and only its presentation is
    local.
"""

# Imports - Local
from ._change_log import ChangeLogRepository
from ._events import EventRepository
from ._revisions import RevisionRepository
from ._runs import RunRepository

__all__ = [
    'ChangeLogRepository',
    'EventRepository',
    'RevisionRepository',
    'RunRepository'
]
