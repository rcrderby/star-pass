#!/usr/bin/env python3
""" What a stored event does not say, worked out from what it does.

    The 'Event' record holds facts and nothing else, and its own
    docstring names the four things it deliberately leaves out: how
    long the shift is, whether an opportunity's maximum shortened it,
    whether another event in the revision would create the same shift,
    and whether the event blocks the run for want of a match.  This is
    where those four are worked out.

    Derived rather than stored because each one is a reading of state
    that can change without the event changing.  An opportunity's
    maximum is edited in Amplify; a duplicate appears when a different
    event is edited to collide with this one; whether an event blocks
    a run depends on the roles it has now.  Stored, each would be a
    second copy of a fact with its own way of going stale.

    Pure functions over records, in the core rather than in the
    service: none of this is about HTTP, and the command line client
    shows the same figures the web interface does (D1).
"""

# Imports - Python Standard Library
from datetime import datetime
from typing import Dict, Iterable, Optional

# Imports - Local
from ._defaults import SIMPLE_TIME_FORMAT
from ._records import Event, EventRole, ShiftIdentity

# How many minutes are in an hour, for turning a time of day into one
# number that can be subtracted from another.
MINUTES_PER_HOUR = 60


def shift_identity(
        event: Event,
        role: EventRole
) -> ShiftIdentity:
    """ Return the row one role of an event would send Amplify.

        Written once and used wherever sameness is decided, so that
        the answer to "is this the same shift" cannot come out
        differently in two places (D16).

        Args:
            event (Event):
                The event the shift comes from.

            role (EventRole):
                The opportunity the shift is created under.

        Returns:
            identity (ShiftIdentity):
                Need ID, date, start and end.
    """

    return (
        role.need_id,
        event.date,
        event.shift_start,
        event.shift_end
    )


def _minutes_of_day(
        time_of_day: str
) -> int:
    """ Return a time of day as minutes since midnight.

        Args:
            time_of_day (str):
                A 24-hour time, as the records store one.

        Raises:
            ValueError:
                If the value is not a time.

        Returns:
            minutes (int):
                Minutes from midnight to that time.
    """

    parsed = datetime.strptime(time_of_day, SIMPLE_TIME_FORMAT)

    return parsed.hour * MINUTES_PER_HOUR + parsed.minute


def minutes_between(
        start: str,
        end: str
) -> int:
    """ Return how many minutes separate two times of day.

        Below both callers.  A stored event's shift length is worked
        out this way, and so is the duration Amplify is sent for a
        shift the send is about to create -- and those two have to be
        the same number, because the second is what arrives and the
        first is what a person was shown.

        Negative when the end is earlier than the start.  Reported
        rather than refused: the caller knows whether that is a row to
        block or a figure to display.

        Args:
            start (str):
                A 24-hour time, as the records store one.

            end (str):
                The later time.

        Raises:
            ValueError:
                If either value is not a time.

        Returns:
            minutes (int):
                Minutes from the first to the second.
    """

    return (
        _minutes_of_day(time_of_day=end)
        - _minutes_of_day(time_of_day=start)
    )


def shift_length(
        event: Event
) -> int:
    """ Return how long the shift an event creates lasts, in minutes.

        This is the duration Amplify is given: it takes a start and a
        length, not a start and an end, so the number here is the one
        that reaches it.

        Negative when the event's shift ends before it starts.
        Reported rather than refused, because the collection path
        rejects such an event but an edit can still produce one, and a
        reader is better served by the number than by an exception
        raised while a list was being drawn.

        Args:
            event (Event):
                The event to measure.

        Raises:
            ValueError:
                If the event's shift times are not times.

        Returns:
            minutes (int):
                Length of the shift, which a caller should treat as
                blocking when it is not above zero.
    """

    return minutes_between(
        start=event.shift_start,
        end=event.shift_end
    )


def capping_maximum(
        event: Event
) -> Optional[int]:
    """ Return the maximum that shortened an event's shift, if one did.

        Worked out by comparing the shift against the one the calendar
        and the offsets would have produced on their own: when that
        would have run longer than the opportunity allows, the maximum
        is what decided the length, and a reader is told which number
        did it rather than being left to wonder why the shift is
        shorter than the event.

        An event serves one shift per role and the roles can name
        different opportunities, so the binding maximum is the smallest
        of the ones that applied.  Every category in the data model
        gives its need IDs the same timing today, so there is only ever
        one; nothing enforces that, which is why this does not assume
        it.

        Read from the roles and not from the run's opportunities: the
        offsets and the maximum are what the role was collected with,
        which is what produced the times being explained (D25).

        Args:
            event (Event):
                The event to examine.

        Raises:
            ValueError:
                If the event's times are not times.

        Returns:
            maximum (int | None):
                The maximum that shortened the shift, or None when
                nothing did.
    """

    calendar_length = (
        _minutes_of_day(time_of_day=event.calendar_end)
        - _minutes_of_day(time_of_day=event.calendar_start)
    )
    applied = []

    for role in event.roles:
        if role.max_length is None:
            continue

        uncapped = (
            calendar_length
            + role.offset_end
            - role.offset_start
        )

        if uncapped > role.max_length:
            applied.append(role.max_length)

    return min(applied) if applied else None


def repeated(
        events: Iterable[Event]
) -> Dict[str, str]:
    """ Return which events would create a shift an earlier one already does.

        Two events repeat each other when they would send Amplify the
        same row, and a row is identified by need ID, date, start and
        end (D16) -- never by a count, which cannot say *which* shifts
        already exist.  Sharing a title or a time is not enough: two
        events at the same hour under different opportunities are two
        different shifts and both belong.

        The earlier event is the one kept, so a reader is pointed at
        the one already in the list rather than at the one they are
        looking at.  Earlier means earlier in the sequence given, which
        is the order the revision is read in.

        Args:
            events (Iterable[Event]):
                Every event in the revision, in the order they are
                shown.

        Returns:
            repeats (Dict[str, str]):
                Event ID mapped to the ID of the earlier event it
                repeats.  An event repeating nothing is absent.
    """

    seen: Dict[ShiftIdentity, str] = {}
    repeats: Dict[str, str] = {}

    for event in events:
        for role in event.roles:
            identity = shift_identity(event=event, role=role)

            if identity in seen:
                # An event repeating on two of its roles is still one
                # repeat to a reader, and the first is the one to name.
                repeats.setdefault(event.id, seen[identity])

            else:
                seen[identity] = event.id

    return repeats


def blocks_the_run(
        event: Event
) -> bool:
    """ Return whether an event stops the run being sent.

        True when the event has no role, which is what an unmatched
        title leaves behind: nothing matched, so there is no
        opportunity to create a shift under, and a category that
        resolved to no need ID leaves the same absence.

        A blocked run stops rather than dropping the event, because a
        missing shift is invisible -- the operator finds out when
        volunteers cannot sign up.

        Args:
            event (Event):
                The event to examine.

        Returns:
            blocking (bool):
                Whether the event blocks the run.
    """

    return not event.roles
