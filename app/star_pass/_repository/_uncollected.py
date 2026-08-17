#!/usr/bin/env python3
""" What a run's window held that the run does not.

    Written once, by the collection that read the window, and read
    back whenever somebody asks why an event is not in the run.  It is
    stored rather than worked out on demand because the figure appears
    beside every reading of the run: produced on demand it would cost
    a calendar request per look, and it would be a second answer about
    a window the run has already read.

    Replaced as a set, like the opportunities a run resolved.  A
    collection reads the whole window, so what it found is the whole
    truth about that window, and merging it with an earlier reading
    would keep rows describing events the calendar no longer has.
"""

# Imports - Python Standard Library
import sqlite3
from typing import Iterable, List, Optional

# Imports - Local
from .._database import (
    execute,
    execute_many,
    query,
    query_one,
    transaction
)
from .._records import UncollectedEvent, UNCOLLECTED_REASONS
from ._common import (
    insert_statement,
    Repository,
    require_one_of
)

# Constants
# Columns a row is written with and read back by, in one order, so an
# insert and a select cannot drift apart.
UNCOLLECTED_COLUMNS = (
    'run_id',
    'id',
    'reason',
    'title',
    'date',
    'calendar_start',
    'calendar_end'
)


def _to_uncollected(
        row: sqlite3.Row
) -> UncollectedEvent:
    """ Build an uncollected event record from a row.

        Args:
            row (sqlite3.Row):
                A row from the uncollected events table.

        Returns:
            uncollected (UncollectedEvent):
                The event the row describes.
    """

    return UncollectedEvent(
        id=row['id'],
        reason=row['reason'],
        title=row['title'],
        date=row['date'],
        calendar_start=row['calendar_start'],
        calendar_end=row['calendar_end']
    )


class UncollectedRepository(Repository):
    """ The events a run's window held and the run left out. """

    def replace(
            self,
            run_id: str,
            uncollected: Iterable[UncollectedEvent]
    ) -> None:
        """ Replace what a run's window held and the run left out.

            Args:
                run_id (str):
                    Identifier of the run.

                uncollected (Iterable[UncollectedEvent]):
                    Everything in the window that did not become an
                    event, with the reason for each.

            Raises:
                ValidationError:
                    If a reason is not one the layer knows, or there is
                    no such run.

                UpstreamError:
                    If they cannot be written.

            Returns:
                None.
        """

        rows = list(uncollected)

        for event in rows:
            require_one_of(
                value=event.reason,
                allowed=UNCOLLECTED_REASONS,
                description='a reason an event was not collected'
            )

        with transaction(connection=self._connection):
            execute(
                connection=self._connection,
                statement=(
                    'DELETE FROM uncollected_events WHERE run_id = ?'
                ),
                parameters=(run_id,)
            )
            execute_many(
                connection=self._connection,
                statement=insert_statement(
                    table='uncollected_events',
                    columns=UNCOLLECTED_COLUMNS
                ),
                parameters=[
                    (
                        run_id,
                        event.id,
                        event.reason,
                        event.title,
                        event.date,
                        event.calendar_start,
                        event.calendar_end
                    )
                    for event in rows
                ]
            )

        return None

    def get(
            self,
            run_id: str,
            event_id: str
    ) -> Optional[UncollectedEvent]:
        """ Return one thing a run's window held and the run left out.

            Read by the run as well as the identifier, because the
            identifier is the calendar's and two runs whose windows
            overlap hold rows for the same event.

            Args:
                run_id (str):
                    Identifier of the run.

                event_id (str):
                    The calendar's identifier for the event.

            Raises:
                UpstreamError:
                    If it cannot be read.

            Returns:
                uncollected (UncollectedEvent | None):
                    What the run left out under that identifier, or
                    None when it left out no such thing.
        """

        row = query_one(
            connection=self._connection,
            statement=(
                'SELECT * FROM uncollected_events '
                'WHERE run_id = ? AND id = ?'
            ),
            parameters=(run_id, event_id)
        )

        if row is None:
            return None

        return _to_uncollected(row=row)

    def list_all(
            self,
            run_id: str
    ) -> List[UncollectedEvent]:
        """ Return what a run's window held and the run left out.

            In the order the window ran, so a reader goes down the list
            the way they read a calendar.  An event whose date could
            not be read comes first rather than being left out: it is
            still something the window held.

            Args:
                run_id (str):
                    Identifier of the run.

            Raises:
                UpstreamError:
                    If they cannot be read.

            Returns:
                uncollected (List[UncollectedEvent]):
                    Everything stored for the run, earliest first.
        """

        rows = query(
            connection=self._connection,
            statement=(
                'SELECT * FROM uncollected_events '
                'WHERE run_id = ? '
                'ORDER BY date, calendar_start, id'
            ),
            parameters=(run_id,)
        )

        return [_to_uncollected(row=row) for row in rows]
