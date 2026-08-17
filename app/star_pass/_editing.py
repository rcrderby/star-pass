#!/usr/bin/env python3
""" Editing the events in a run's current revision.

    One user action is one call carrying a list of operations, so a
    bulk action over thirty selected rows is one request, one log entry
    and one revision delta rather than thirty of each.

    In the core, not the service.  Nothing here is about HTTP, and the
    command line client edits a run without one (D2).  What an edit
    means has to be decided in one place for the same reason a refusal
    does: a service and a command line that worked it out separately
    would eventually disagree about what a nudge did, and nothing would
    say so.

    **An edit moves the shift times; the calendar times never move.**
    The calendar times are what the calendar said, and a run keeps them
    so it can always say what it started from.  The shift times are
    what reaches Amplify, and they are what a reviewer sets, nudges and
    resets.  That is what lets 'undo' recompute the original from the
    calendar times and the category's offsets instead of storing a copy
    of it.

    **An edit that cannot become a correct shift is refused whole.**
    The operations in one call are applied together or not at all, so a
    bulk nudge that would push one event of thirty past midnight leaves
    all thirty as they were.  A partly applied action is worse than a
    refused one: the reviewer cannot see which rows moved.
"""

# Imports - Python Standard Library
import sqlite3
from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Sequence, Tuple

# Imports - Local
from ._event_edits import (
    as_collected,
    EditContext,
    nudged,
    required,
    slots_reset,
    timed,
    with_slots
)
from ._database import transaction
from ._exceptions import ValidationError
from ._helpers import Helpers
from ._logging import get_logger
from ._records import Event, LogEntry, Opportunity
from ._repository import (
    ChangeLogRepository,
    EventRepository,
    RunRepository
)

# What a caller may ask for.  Named here rather than left as loose
# strings so the contract, the command line and this module cannot
# drift apart about what an operation is called.
OP_SET_CATEGORY = 'set_category'
OP_SET_START = 'set_start'
OP_SET_END = 'set_end'
OP_SET_SLOTS = 'set_slots'
OP_NUDGE = 'nudge'
OP_RESET_SLOTS = 'reset_slots'
OP_REMOVE = 'remove'
OP_UNDO = 'undo'

OPERATIONS = (
    OP_SET_CATEGORY,
    OP_SET_START,
    OP_SET_END,
    OP_SET_SLOTS,
    OP_NUDGE,
    OP_RESET_SLOTS,
    OP_REMOVE,
    OP_UNDO
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

            entries (Tuple[str, ...]):
                One line per operation, written for a reader.  The
                caller writes these to the change log, because when an
                entry is durable is the caller's business.
    """

    events: Tuple[Event, ...]
    removed: Tuple[str, ...]
    entries: Tuple[str, ...]


@dataclass(frozen=True)
class _Result:
    """ What one operation did.

        Attributes:
            entry (str):
                The line to log, written for a reader.

            changed (Dict[str, Event]):
                The events it changed, by ID.  Empty for an operation
                that only removes.

            removed (Tuple[str, ...]):
                Identifiers it took out of the revision.
    """

    entry: str
    changed: Dict[str, Event] = field(default_factory=dict)
    removed: Tuple[str, ...] = ()


def _named(
        events: Sequence[Event]
) -> str:
    """ Return what to call a set of events in a log entry.

        One event is worth naming; a selection is worth counting.  A
        log line listing thirty titles is one nobody reads.

        Args:
            events (Sequence[Event]):
                The events an operation applied to.

        Returns:
            name (str):
                The title in quotes, or a count.
    """

    if len(events) == 1:
        return f'"{events[0].title}"'

    return f'{len(events)} events'


def _remove(
        operation: Operation,
        events: Sequence[Event],
        context: EditContext
) -> '_Result':
    """ Take the named events out of the revision. """

    del operation, context

    return _Result(
        removed=tuple(event.id for event in events),
        entry=f'Removed {_named(events)}.'
    )


def _set_category(
        operation: Operation,
        events: Sequence[Event],
        context: EditContext
) -> '_Result':
    """ Put the named events under a category a person chose. """

    category = required(
        value=operation.category,
        name='category',
        op=operation.op
    )

    return _Result(
        changed={
            event.id: as_collected(
                event=replace(event, category=category, match=None),
                calendar=context.calendar,
                helpers=context.helpers
            )
            for event in events
        },
        entry=f'Set the category of {_named(events)} to "{category}".'
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
        entry=f'Set the shift start of {_named(events)} to {time}.'
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
        entry=f'Set the shift end of {_named(events)} to {time}.'
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
    moved = 'later' if minutes > 0 else 'earlier'

    return _Result(
        changed={
            event.id: nudged(event=event, minutes=minutes)
            for event in events
        },
        entry=f'Moved {_named(events)} {abs(minutes)} minutes {moved}.'
    )


def _set_slots(
        operation: Operation,
        events: Sequence[Event],
        context: EditContext
) -> '_Result':
    """ Set how many volunteers one role wants. """

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
        entry=(
            f'Set {slots} volunteers wanted on {_named(events)} for '
            f'{context.opportunity_name(need_id)}.'
        )
    )


def _reset_slots(
        operation: Operation,
        events: Sequence[Event],
        context: EditContext
) -> '_Result':
    """ Put every role back to what its opportunity asks for. """

    del operation

    return _Result(
        changed={
            event.id: slots_reset(event=event, context=context)
            for event in events
        },
        entry=(
            f'Reset the volunteers wanted on {_named(events)} to what '
            'the opportunity asks for.'
        )
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
        entry=f'Undid the changes to {_named(events)}.'
    )


# What each operation does.  A table rather than a chain of branches,
# so what a caller may ask for and what answers it are one list: an
# operation named in the contract with no handler here is a KeyError
# at the point of use rather than a branch that silently falls
# through.
HANDLERS = {
    OP_SET_CATEGORY: _set_category,
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
        known = ', '.join(OPERATIONS)
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
        opportunities: Sequence[Opportunity],
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

            opportunities (Sequence[Opportunity]):
                The run's opportunities, for what each asks by default.

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
        helpers=helpers if helpers is not None else Helpers(),
        opportunities={
            opportunity.need_id: opportunity
            for opportunity in opportunities
        }
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
        same process (D2), and an edit worked out twice would let one
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
                Who did it (D13).

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
        opportunities=runs.get_opportunities(run_id=run_id),
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
                entry=entry
            )
            for entry in applied.entries
        ]

    return list(applied.events), entries
