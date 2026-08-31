#!/usr/bin/env python3
""" Editing the events in a run's current revision.

    One user action is one call carrying a list of operations, so a
    bulk action over thirty selected rows is one request, one log
    entry and one revision delta rather than thirty of each.

    In the core, not the service: the command line client edits a run
    without one, and what an edit means is decided in one place so the
    two cannot disagree about what a nudge did.

    An edit moves the shift times; the calendar times never move.  The
    calendar times are what the calendar said, so a run can always say
    what it started from.  The shift times reach Amplify, and a
    reviewer sets, nudges and resets them, which lets 'undo' recompute
    the original from the calendar times and the category's offsets.

    An edit that cannot become a correct shift is refused whole: a
    bulk nudge that would push one event of thirty past midnight
    leaves all thirty as they were.
"""

# Imports - Python Standard Library
import sqlite3
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Imports - Local
from ._event_edits import (
    as_collected,
    EditContext,
    nudged,
    required,
    slots_reset,
    timed,
    under_category,
    with_slots
)
from ._database import transaction
from ._derived import may_unassign
from ._exceptions import ValidationError
from ._helpers import Helpers
from ._logging import get_logger
from ._records import (
    EDIT_OPERATIONS,
    Event,
    LogEntry,
    OP_NUDGE,
    OP_REMOVE,
    OP_RESET_SLOTS,
    OP_SET_CATEGORY,
    OP_SET_END,
    OP_SET_SLOTS,
    OP_SET_START,
    OP_UNASSIGN,
    OP_UNDO
)
from ._repository import (
    ChangeLogRepository,
    EventRepository,
    RunRepository
)

# Module logger
logger = get_logger(__name__)


@dataclass(frozen=True)
class Operation:
    """ One thing a reviewer did, over one or more events.

        A record rather than a bag of arguments: an operation carries
        different fields depending on what it is, and every caller
        naming them positionally would be a caller to fix when a new
        operation arrives.

        Attributes:
            op (str):
                Which operation, from 'OPERATIONS'.

            event_ids (Tuple[str, ...]):
                The events it applies to.  A selection of thirty is one
                operation naming thirty, not thirty operations.

            category (str, optional):
                Category to set, for 'set_category'.

            time (str, optional):
                Time of day to set, as 'HH:MM', for 'set_start' and
                'set_end'.

            need_id (str, optional):
                Which role to set slots for, for 'set_slots'.  A role
                rather than the event, because an event serving skating
                and non-skating officials wants different numbers of
                each.

            slots (int, optional):
                Volunteers wanted, for 'set_slots'.

            minutes (int, optional):
                How far to move both shift times, for 'nudge'.
                Negative moves the shift earlier.
    """

    op: str
    event_ids: Tuple[str, ...]
    category: Optional[str] = None
    time: Optional[str] = None
    need_id: Optional[str] = None
    slots: Optional[int] = None
    minutes: Optional[int] = None


@dataclass(frozen=True)
class Edit:
    """ What applying operations produced.

        Attributes:
            events (Tuple[Event, ...]):
                The revision's events as they now are, in the order
                they were read.

            removed (Tuple[str, ...]):
                Identifiers of the events the operations took out.

            entries (Tuple[LogEntry, ...]):
                One per operation: what was done and the values it
                carried.  The caller writes these to the change log,
                because when an entry is durable is the caller's
                business.
    """

    events: Tuple[Event, ...]
    removed: Tuple[str, ...]
    entries: Tuple[LogEntry, ...]


@dataclass(frozen=True)
class _Result:
    """ What one operation did.

        Attributes:
            entry (LogEntry):
                What to log: the operation and the values it carried.

            changed (Dict[str, Event]):
                The events it changed, by ID.  Empty for an operation
                that only removes.

            removed (Tuple[str, ...]):
                Identifiers it took out of the revision.
    """

    entry: LogEntry
    changed: Dict[str, Event] = field(default_factory=dict)
    removed: Tuple[str, ...] = ()


def _named(
        events: Sequence[Event]
) -> str:
    """ Return what to call a set of events in a refusal.

        For the core's own messages, which are sentences it owns and
        writes for a person.  What the change log records is not a
        sentence at all -- see '_recorded'.

        Args:
            events (Sequence[Event]):
                The events a refusal is about.

        Returns:
            name (str):
                The title in quotes, or a count.
    """

    if len(events) == 1:
        return f'"{events[0].title}"'

    return f'{len(events)} events'


def _recorded(
        action: str,
        events: Sequence[Event],
        **values: Any
) -> LogEntry:
    """ Return what an operation writes to the change log.

        One event is named and a selection is counted, because a line
        listing thirty titles is one nobody reads -- but both are
        recorded and neither is worded here, so whoever shows the
        entry decides how it reads.

        Args:
            action (str):
                What was done, one of 'LOG_ACTIONS'.

            events (Sequence[Event]):
                The events it applied to.

            **values:
                The values the action carried, by the name 'LogEntry'
                holds each under.

        Returns:
            entry (LogEntry):
                The entry, less the identity the repository stamps on.
    """

    return LogEntry(
        action=action,
        subject=events[0].title if len(events) == 1 else None,
        subject_count=len(events),
        **values
    )


def _remove(
        operation: Operation,
        events: Sequence[Event],
        context: EditContext
) -> '_Result':
    """ Take the named events out of the revision. """

    del operation, context

    return _Result(
        removed=tuple(event.id for event in events),
        entry=_recorded(action=OP_REMOVE, events=events)
    )


def _set_category(
        operation: Operation,
        events: Sequence[Event],
        context: EditContext
) -> '_Result':
    """ Put the named events under a category a person chose.

        What the collection matched is left as it is, so the row can
        say it was changed and an undo has somewhere to put it back
        to.
    """

    category = required(
        value=operation.category,
        name='category',
        op=operation.op
    )

    return _Result(
        changed={
            event.id: under_category(
                event=replace(event, match=None),
                category=category,
                calendar=context.calendar,
                helpers=context.helpers
            )
            for event in events
        },
        entry=_recorded(
            action=OP_SET_CATEGORY,
            events=events,
            category=category
        )
    )


def _unassign(
        operation: Operation,
        events: Sequence[Event],
        context: EditContext
) -> '_Result':
    """ Put the named events back to having no opportunity.

        Only where the collection matched nothing, which is the row
        unassigned is a state of.  A row the collection did match is
        refused: what such a row wants when it should create no shift
        is to be removed from the revision, and unassigning it would
        leave a row behind blocking the whole run.
    """

    del operation

    matched = [event for event in events if not may_unassign(event=event)]

    if matched:
        message = (
            f'{_named(matched)} cannot be unassigned, because the '
            'collection matched an opportunity for it. Unassigned is '
            'where a row starts when nothing matched, not somewhere a '
            'row can be put. Remove the event from the run if it '
            'should create no shift.'
        )
        logger.error(message)
        raise ValidationError(message)

    return _Result(
        changed={
            event.id: under_category(
                event=replace(event, match=None),
                category=None,
                calendar=context.calendar,
                helpers=context.helpers
            )
            for event in events
        },
        entry=_recorded(action=OP_UNASSIGN, events=events)
    )


def _set_start(
        operation: Operation,
        events: Sequence[Event],
        context: EditContext
) -> '_Result':
    """ Set where the named events' shifts start. """

    del context
    time = required(value=operation.time, name='time', op=operation.op)

    return _Result(
        changed={
            event.id: timed(
                event=event,
                shift_start=time,
                shift_end=event.shift_end
            )
            for event in events
        },
        entry=_recorded(
            action=OP_SET_START,
            events=events,
            shift_time=time
        )
    )


def _set_end(
        operation: Operation,
        events: Sequence[Event],
        context: EditContext
) -> '_Result':
    """ Set where the named events' shifts end. """

    del context
    time = required(value=operation.time, name='time', op=operation.op)

    return _Result(
        changed={
            event.id: timed(
                event=event,
                shift_start=event.shift_start,
                shift_end=time
            )
            for event in events
        },
        entry=_recorded(
            action=OP_SET_END,
            events=events,
            shift_time=time
        )
    )


def _nudge(
        operation: Operation,
        events: Sequence[Event],
        context: EditContext
) -> '_Result':
    """ Move the named events' shifts by a number of minutes. """

    del context
    minutes = required(
        value=operation.minutes,
        name='minutes',
        op=operation.op
    )

    return _Result(
        changed={
            event.id: nudged(event=event, minutes=minutes)
            for event in events
        },
        entry=_recorded(
            action=OP_NUDGE,
            events=events,
            minutes=minutes
        )
    )


def _set_slots(
        operation: Operation,
        events: Sequence[Event],
        context: EditContext
) -> '_Result':
    """ Set how many volunteers one role wants. """

    del context
    need_id = required(
        value=operation.need_id,
        name='needId',
        op=operation.op
    )
    slots = required(
        value=operation.slots,
        name='slots',
        op=operation.op
    )

    return _Result(
        changed={
            event.id: with_slots(
                event=event,
                need_id=need_id,
                slots=slots
            )
            for event in events
        },
        entry=_recorded(
            action=OP_SET_SLOTS,
            events=events,
            slots=slots,
            need_id=need_id
        )
    )


def _reset_slots(
        operation: Operation,
        events: Sequence[Event],
        context: EditContext
) -> '_Result':
    """ Put every role back to what its category asked for. """

    del operation, context

    return _Result(
        changed={
            event.id: slots_reset(event=event)
            for event in events
        },
        entry=_recorded(action=OP_RESET_SLOTS, events=events)
    )


def _undo(
        operation: Operation,
        events: Sequence[Event],
        context: EditContext
) -> '_Result':
    """ Put the named events back as collection produced them. """

    del operation

    return _Result(
        changed={
            event.id: as_collected(
                event=event,
                calendar=context.calendar,
                helpers=context.helpers
            )
            for event in events
        },
        entry=_recorded(action=OP_UNDO, events=events)
    )


# What each operation does.  A table rather than a chain of branches,
# so what a caller may ask for and what answers it are one list: an
# operation named in the contract with no handler here is a KeyError
# at the point of use rather than a branch that silently falls
# through.
HANDLERS = {
    OP_SET_CATEGORY: _set_category,
    OP_UNASSIGN: _unassign,
    OP_SET_START: _set_start,
    OP_SET_END: _set_end,
    OP_SET_SLOTS: _set_slots,
    OP_NUDGE: _nudge,
    OP_RESET_SLOTS: _reset_slots,
    OP_REMOVE: _remove,
    OP_UNDO: _undo
}


def _apply_one(
        operation: Operation,
        events: Sequence[Event],
        context: EditContext
) -> '_Result':
    """ Return what one operation does to the events it names.

        Args:
            operation (Operation):
                What was asked for.

            events (Sequence[Event]):
                The events it names, in the revision's order.

            context (EditContext):
                The run's calendar, opportunities and data model
                reader.

        Raises:
            ValidationError:
                If the operation is not one this knows, is missing what
                it needs, or would leave an event unable to become a
                correct shift.

        Returns:
            result (_Result):
                What changed, what was removed, and the line to log.
    """

    handler = HANDLERS.get(operation.op)

    if handler is None:
        known = ', '.join(EDIT_OPERATIONS)
        message = (
            f'"{operation.op}" is not something that can be done to an '
            f'event. The operations are: {known}.'
        )
        logger.error(message)
        raise ValidationError(message)

    return handler(
        operation=operation,
        events=events,
        context=context
    )


def apply(
        operations: Sequence[Operation],
        events: Sequence[Event],
        calendar: str,
        helpers: Optional[Helpers] = None
) -> Edit:
    """ Return what a call's operations do to a revision's events.

        Applied in the order they arrive, each one seeing what the one
        before it produced, so a call that sets a category and then
        nudges the result does what a reader would expect.  Nothing is
        written: a caller decides when the answer becomes durable, and
        an operation that cannot be applied raises before any of them
        reaches the database.

        Args:
            operations (Sequence[Operation]):
                What the reviewer did, in order.

            events (Sequence[Event]):
                The revision's events, in the order they are read.

            calendar (str):
                Calendar the run was collected from.

            helpers (Helpers, optional):
                Where the data model is read through.  Defaults to
                None, which reads it through a new 'Helpers'.

        Raises:
            ValidationError:
                If an operation is unknown, names an event the revision
                does not hold, is missing what it needs, or would leave
                an event unable to become a correct shift.

        Returns:
            edit (Edit):
                The events as they now are, what was removed, and the
                lines to log.
    """

    context = EditContext(
        calendar=calendar,
        helpers=helpers if helpers is not None else Helpers()
    )

    if not operations:
        message = (
            'An edit has to say what to do. Send at least one '
            'operation.'
        )
        logger.error(message)
        raise ValidationError(message)

    # Keyed by ID and rebuilt into the revision's order at the end, so
    # an edit never reorders the list a reviewer is looking at.
    order = [event.id for event in events]
    current = {event.id: event for event in events}
    removed: List[str] = []
    entries: List[str] = []

    for operation in operations:
        result = _apply_one(
            operation=operation,
            events=_selected(operation=operation, current=current),
            context=context
        )

        current.update(result.changed)

        for event_id in result.removed:
            del current[event_id]
            removed.append(event_id)

        entries.append(result.entry)

    return Edit(
        events=tuple(
            current[event_id]
            for event_id in order
            if event_id in current
        ),
        removed=tuple(removed),
        entries=tuple(entries)
    )


def _selected(
        operation: Operation,
        current: Dict[str, Event]
) -> List[Event]:
    """ Return the events an operation names, in the revision's order.

        Args:
            operation (Operation):
                What was asked for.

            current (Dict[str, Event]):
                The events as they stand, by ID.

        Raises:
            ValidationError:
                If it names nothing, or names an event the revision no
                longer holds.

        Returns:
            events (List[Event]):
                The events it applies to.
    """

    if not operation.event_ids:
        message = (
            f'A "{operation.op}" operation has to name at least one '
            'event.'
        )
        logger.error(message)
        raise ValidationError(message)

    missing = [
        event_id
        for event_id in operation.event_ids
        if event_id not in current
    ]

    if missing:
        # A stale tab is the ordinary way here: the reviewer is looking
        # at a list an earlier edit already changed.
        message = (
            f'This revision no longer holds {", ".join(missing)}. '
            'Reload the run and try again.'
        )
        logger.error(message)
        raise ValidationError(message)

    return [current[event_id] for event_id in operation.event_ids]


def edit(
        connection: sqlite3.Connection,
        run_id: str,
        operations: Sequence[Operation],
        principal_id: str
) -> Optional[Tuple[List[Event], List[LogEntry]]]:
    """ Apply operations to a run's current revision and store them.

        Below both halves, the way a send is: the service answers over
        HTTP and the command line answers from the same database in the
        same process, and an edit worked out twice would let one
        of them change something the other did not.

        The whole call is one transaction.  'apply' has already refused
        anything it cannot do, so what is left is writing; but a write
        that failed partway would leave a revision holding some of an
        action, which is the state a reviewer cannot read.

        Args:
            connection (sqlite3.Connection):
                Connection to write on.

            run_id (str):
                Run whose current revision to edit.

            operations (Sequence[Operation]):
                What the reviewer did, in order.

            principal_id (str):
                Who did it.

        Raises:
            ValidationError:
                If an operation cannot be applied.

            UpstreamError:
                If the revision cannot be written.

        Returns:
            edited (Tuple[List[Event], List[LogEntry]] | None):
                The revision's events as they now are and the entries
                the edit added, or None when there is no such run.
    """

    runs = RunRepository(connection=connection)
    run = runs.get(run_id=run_id)

    if run is None:
        return None

    events = EventRepository(connection=connection)
    revision = run.current_revision
    applied = apply(
        operations=operations,
        events=events.list_all(run_id=run_id, revision=revision),
        calendar=run.calendar
    )

    change_log = ChangeLogRepository(connection=connection)

    with transaction(connection=connection):
        for event_id in applied.removed:
            events.remove(
                run_id=run_id,
                revision=revision,
                event_id=event_id
            )

        for event in applied.events:
            events.replace(
                run_id=run_id,
                revision=revision,
                event=event
            )

        entries = [
            change_log.add(
                run_id=run_id,
                revision=revision,
                principal_id=principal_id,
                recorded=entry
            )
            for entry in applied.entries
        ]

    return list(applied.events), entries
