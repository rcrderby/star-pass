#!/usr/bin/env python3
""" How the service reaches stored state.

    A SQLite connection belongs to the thread that opened it, and a
    request is not guaranteed to stay on one: a synchronous dependency
    and the endpoint that uses it can be run on different threads.  So
    a connection is never handed between them.  'in_database' takes the
    work instead, and opens, uses and closes a connection inside a
    single call on a single thread.

    Doing it that way also keeps the database off the event loop.
    SQLite is synchronous, and a read that ran there would stop the
    service answering anything else while it waited.

    Opening a connection per piece of work is cheap -- SQLite opens a
    file -- and it is what lets a request read while a job writes,
    since the database is in write-ahead logging.
"""

# Imports - Python Standard Library
import sqlite3
from typing import Callable, TypeVar

# Imports - Third-Party
from starlette.concurrency import run_in_threadpool

# Imports - Local
from star_pass._database import connect

# What the work returns, so a caller keeps the type it asked for.
Result = TypeVar('Result')


def open_connection() -> sqlite3.Connection:
    """ Open a connection to the configured database.

        Named here so that everything the service starts -- a request,
        a job on its own thread -- opens one the same way.

        Args:
            None.

        Raises:
            ConfigurationError:
                If the database cannot be opened or created.

        Returns:
            connection (sqlite3.Connection):
                An open connection with the schema applied.
    """

    return connect()


def in_database(
        work: Callable[[sqlite3.Connection], Result]
) -> Result:
    """ Run work against a connection of its own, and close it.

        Args:
            work (Callable[[sqlite3.Connection], Result]):
                What to do with the connection.  Called once, on the
                calling thread.

        Raises:
            ConfigurationError:
                If the database cannot be opened.

            StarPassError:
                Whatever the work raises.

        Returns:
            result (Result):
                What the work returned.
    """

    connection = open_connection()

    try:
        return work(connection)

    finally:
        connection.close()


async def in_the_database(
        work: Callable[[sqlite3.Connection], Result]
) -> Result:
    """ Run work against the database, off the event loop.

        What an endpoint calls, for a read or a write.  The work runs
        on a worker thread, so a slow statement delays the request
        that asked for it rather than every request the service is
        serving.

        Args:
            work (Callable[[sqlite3.Connection], Result]):
                What to do with the connection.

        Raises:
            ConfigurationError:
                If the database cannot be opened.

            StarPassError:
                Whatever the work raises.

        Returns:
            result (Result):
                What the work returned.
    """

    return await run_in_threadpool(in_database, work)
