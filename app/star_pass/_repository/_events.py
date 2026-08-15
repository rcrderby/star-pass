#!/usr/bin/env python3
""" The events in one revision of a run, and their roles. """

# Imports - Python Standard Library
import sqlite3
from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

# Imports - Local
from .._database import execute, execute_many, query, query_one, transaction
from .._logging import get_logger
from .._records import Event, EventRole, Match
from ._common import (
    EVENT_COLUMNS,
    EVENT_ROLE_COLUMNS,
    insert_statement,
    Repository,
    require_row
)

# Module logger
logger = get_logger(__name__)


def _to_event_role(
        row: sqlite3.Row
) -> EventRole:
    """ Build an event role record from a row.

        Args:
            row (sqlite3.Row):
                A row from the event roles table.

        Returns:
            role (EventRole):
                The role the row describes.
    """

    return EventRole(
        need_id=row['need_id'],
        slots=row['slots'],
        edited=bool(row['edited'])
    )


def _to_event(
        row: sqlite3.Row,
        roles: Tuple[EventRole, ...]
) -> Event:
    """ Build an event record from a row and the roles read with it.

        Args:
            row (sqlite3.Row):
                A row from the events table.

            roles (Tuple[EventRole, ...]):
                The event's roles, read separately so that a revision
                costs two queries rather than one per event.

        Returns:
            event (Event):
                The event the row describes.
    """

    match = None
    if row['match_kind'] is not None:
        match = Match(
            kind=row['match_kind'],
            keyword=row['match_keyword'],
            score=row['match_score']
        )

    return Event(
        id=row['id'],
        title=row['title'],
        date=row['date'],
        calendar_start=row['calendar_start'],
        calendar_end=row['calendar_end'],
        shift_start=row['shift_start'],
        shift_end=row['shift_end'],
        category=row['category'],
        match=match,
        added_by_hand=bool(row['added_by_hand']),
        roles=roles
    )


def _event_values(
        run_id: str,
        revision: int,
        event: Event
) -> Tuple:
    """ Return an event's column values in 'EVENT_COLUMNS' order.

        Args:
            run_id (str):
                Run the event belongs to.

            revision (int):
                Revision the event belongs to.

            event (Event):
                The event to write.

        Returns:
            values (Tuple):
                One value per column, ready to bind.
    """

    match = event.match

    return (
        run_id,
        revision,
        event.id,
        event.title,
        event.date,
        event.calendar_start,
        event.calendar_end,
        event.shift_start,
        event.shift_end,
        event.category,
        match.kind if match is not None else None,
        match.keyword if match is not None else None,
        match.score if match is not None else None,
        event.added_by_hand
    )


def _role_values(
        run_id: str,
        revision: int,
        events: Iterable[Event]
) -> List[Tuple]:
    """ Return every role's column values for a group of events.

        Args:
            run_id (str):
                Run the events belong to.

            revision (int):
                Revision the events belong to.

            events (Iterable[Event]):
                The events whose roles are being written.

        Returns:
            values (List[Tuple]):
                One tuple per role, in 'EVENT_ROLE_COLUMNS' order.
    """

    return [
        (
            run_id,
            revision,
            event.id,
            role.need_id,
            role.slots,
            role.edited
        )
        for event in events
        for role in event.roles
    ]


class EventRepository(Repository):
    """ The events in one revision of a run.

        An event is read and written with its roles, because an event
        without them creates no shift and a role without its event
        belongs to nothing.
    """

    def add_all(
            self,
            run_id: str,
            revision: int,
            events: Sequence[Event]
    ) -> None:
        """ Add events and their roles to a revision.

            Args:
                run_id (str):
                    Run the revision belongs to.

                revision (int):
                    Revision to add the events to.

                events (Sequence[Event]):
                    The events to add.

            Raises:
                ValidationError:
                    If the revision does not exist, or an event ID is
                    already used in it.

                UpstreamError:
                    If the events cannot be written.

            Returns:
                None.
        """

        with transaction(connection=self._connection):
            execute_many(
                connection=self._connection,
                statement=insert_statement(
                    table='events',
                    columns=EVENT_COLUMNS
                ),
                parameters=[
                    _event_values(
                        run_id=run_id,
                        revision=revision,
                        event=event
                    )
                    for event in events
                ]
            )
            execute_many(
                connection=self._connection,
                statement=insert_statement(
                    table='event_roles',
                    columns=EVENT_ROLE_COLUMNS
                ),
                parameters=_role_values(
                    run_id=run_id,
                    revision=revision,
                    events=events
                )
            )

        return None

    def add(
            self,
            run_id: str,
            revision: int,
            event: Event
    ) -> None:
        """ Add one event and its roles to a revision.

            Args:
                run_id (str):
                    Run the revision belongs to.

                revision (int):
                    Revision to add the event to.

                event (Event):
                    The event to add.

            Raises:
                ValidationError:
                    If the revision does not exist, or the event ID is
                    already used in it.

                UpstreamError:
                    If the event cannot be written.

            Returns:
                None.
        """

        return self.add_all(
            run_id=run_id,
            revision=revision,
            events=(event,)
        )

    def replace(
            self,
            run_id: str,
            revision: int,
            event: Event
    ) -> None:
        """ Replace an event, and its roles, with an edited version.

            Written whole rather than column by column: an edit can
            change the times, the category and the roles together, and
            applying those separately would leave a moment where the
            stored event is a mixture of the two.

            Args:
                run_id (str):
                    Run the revision belongs to.

                revision (int):
                    Revision holding the event.

                event (Event):
                    The event as it should now be, under the same ID.

            Raises:
                ValidationError:
                    If the revision holds no event with that ID.

                UpstreamError:
                    If the event cannot be written.

            Returns:
                None.
        """

        with transaction(connection=self._connection):
            self.remove(
                run_id=run_id,
                revision=revision,
                event_id=event.id
            )
            self.add(
                run_id=run_id,
                revision=revision,
                event=event
            )

        return None

    def remove(
            self,
            run_id: str,
            revision: int,
            event_id: str
    ) -> None:
        """ Remove an event, and its roles, from a revision.

            Args:
                run_id (str):
                    Run the revision belongs to.

                revision (int):
                    Revision holding the event.

                event_id (str):
                    Identifier of the event to remove.

            Raises:
                ValidationError:
                    If the revision holds no event with that ID.

                UpstreamError:
                    If the event cannot be removed.

            Returns:
                None.
        """

        cursor = execute(
            connection=self._connection,
            statement=(
                'DELETE FROM events '
                'WHERE run_id = ? AND revision = ? AND id = ?'
            ),
            parameters=(run_id, revision, event_id)
        )

        require_row(
            cursor=cursor,
            message=(
                f'Revision {revision} of run "{run_id}" has no event '
                f'"{event_id}".'
            )
        )

        return None

    def get(
            self,
            run_id: str,
            revision: int,
            event_id: str
    ) -> Optional[Event]:
        """ Return one event, with its roles.

            Args:
                run_id (str):
                    Run the revision belongs to.

                revision (int):
                    Revision holding the event.

                event_id (str):
                    Identifier of the event to read.

            Raises:
                UpstreamError:
                    If the event cannot be read.

            Returns:
                event (Event | None):
                    The event, or None when there is no such one.
        """

        row = query_one(
            connection=self._connection,
            statement=(
                'SELECT * FROM events '
                'WHERE run_id = ? AND revision = ? AND id = ?'
            ),
            parameters=(run_id, revision, event_id)
        )

        if row is None:
            return None

        return _to_event(
            row=row,
            roles=self._roles(
                run_id=run_id,
                revision=revision,
                event_id=event_id
            ).get(event_id, ())
        )

    def list_all(
            self,
            run_id: str,
            revision: int
    ) -> List[Event]:
        """ Return a revision's events, in the order they happen.

            The roles are read in one further query and matched up
            here, so that a revision costs two queries however many
            events it holds.

            Args:
                run_id (str):
                    Run the revision belongs to.

                revision (int):
                    Revision to read.

            Raises:
                UpstreamError:
                    If the events cannot be read.

            Returns:
                events (List[Event]):
                    Every event in the revision, by date and start
                    time.
        """

        rows = query(
            connection=self._connection,
            statement=(
                'SELECT * FROM events WHERE run_id = ? AND revision = ? '
                'ORDER BY date, shift_start, id'
            ),
            parameters=(run_id, revision)
        )
        roles = self._roles(
            run_id=run_id,
            revision=revision
        )

        return [
            _to_event(
                row=row,
                roles=roles.get(row['id'], ())
            )
            for row in rows
        ]

    def _roles(
            self,
            run_id: str,
            revision: int,
            event_id: Optional[str] = None
    ) -> Dict[str, Tuple[EventRole, ...]]:
        """ Return a revision's roles, keyed on the event they belong to.

            Args:
                run_id (str):
                    Run the revision belongs to.

                revision (int):
                    Revision to read.

                event_id (str, optional):
                    Read only this event's roles.  Defaults to None,
                    which reads every event's.

            Raises:
                UpstreamError:
                    If the roles cannot be read.

            Returns:
                roles (Dict[str, Tuple[EventRole, ...]]):
                    Event ID mapped to that event's roles, by need ID.
        """

        statement = (
            'SELECT * FROM event_roles WHERE run_id = ? AND revision = ?'
        )
        parameters = [run_id, revision]

        if event_id is not None:
            statement = f'{statement} AND event_id = ?'
            parameters.append(event_id)

        rows = query(
            connection=self._connection,
            statement=f'{statement} ORDER BY need_id',
            parameters=parameters
        )

        collected: Dict[str, List[EventRole]] = defaultdict(list)
        for row in rows:
            collected[row['event_id']].append(_to_event_role(row=row))

        return {
            key: tuple(value)
            for key, value in collected.items()
        }
