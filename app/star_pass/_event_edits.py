#!/usr/bin/env python3
""" What one event becomes when a reviewer changes it.

    Below '_editing', which decides what a reviewer asked for and what
    to write in the change log.  This module knows only how a single
    event changes: where its shift runs, which opportunities it serves
    and how many volunteers each of those wants.

    **The calendar times never move.**  They are what the calendar
    said, and a run keeps them so it can always say what it started
    from.  The shift times are what reaches Amplify, and they are what
    a reviewer sets, nudges and resets.  That is what lets an undo
    recompute the original from the calendar times and the category's
    offsets rather than storing a copy of it.
"""

# Imports - Python Standard Library
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Dict, List, Optional

# Imports - Local
from . import _defaults
from ._exceptions import ValidationError
from ._helpers import Helpers
from ._logging import get_logger
from ._records import Event, EventRole, Opportunity
from ._shift_timing import (
    MINUTES_PER_DAY,
    RoleTiming,
    role_timings,
    shift_times
)

# Constants
ISO_DATE_FORMAT = _defaults.ISO_DATE_FORMAT
SIMPLE_TIME_FORMAT = _defaults.SIMPLE_TIME_FORMAT

# Module logger
logger = get_logger(__name__)


@dataclass(frozen=True)
class EditContext:
    """ What every operation needs and none of them decides.

        Gathered once rather than threaded through each operation
        separately: the calendar, the data model reader and the run's
        opportunities are read the same way whatever is being done, and
        seven parameters is a signature nobody reads.

        Attributes:
            calendar (str):
                Calendar the run was collected from.

            helpers (Helpers):
                Where the shift data model is read through.

            opportunities (Dict[str, Opportunity]):
                The run's opportunities, by need ID.
    """

    calendar: str
    helpers: Helpers
    opportunities: Dict[str, Opportunity]

    def default_slots(
            self,
            need_id: str
    ) -> int:
        """ Return what an opportunity asks for by default.

            Args:
                need_id (str):
                    The opportunity's need ID.

            Raises:
                ValidationError:
                    If the run holds no such opportunity.

            Returns:
                slots (int):
                    Volunteers wanted, before any edit.
        """

        opportunity = self.opportunities.get(need_id)

        if opportunity is None:
            message = (
                f'This run holds no opportunity for need {need_id}, so '
                'there is no usual number of volunteers to go back to.'
            )
            logger.error(message)
            raise ValidationError(message)

        return opportunity.default_slots

    def opportunity_name(
            self,
            need_id: str
    ) -> str:
        """ Return what to call an opportunity in a log entry.

            Args:
                need_id (str):
                    The opportunity's need ID.

            Returns:
                name (str):
                    Its Amplify title, or the need ID when the run
                    holds no title for it -- a log entry is worth
                    writing either way.
        """

        opportunity = self.opportunities.get(need_id)

        if opportunity is None:
            return f'need {need_id}'

        return f'"{opportunity.title}"'


def _minutes_of(
        time: str,
        label: str
) -> int:
    """ Return a time of day as minutes since midnight.

        Times of day rather than moments: both of an event's times
        belong to the same day, and the arithmetic is minutes within
        it.  Reading them as instants would invite a shift to move by
        an hour on the two days a year the offset changes.

        Args:
            time (str):
                A time of day, as 'HH:MM'.

            label (str):
                What to call the value in the message, so a reader is
                told which of theirs is wrong.

        Raises:
            ValidationError:
                If the value is not a time of day.

        Returns:
            minutes (int):
                Minutes from midnight.
    """

    try:
        parsed = datetime.strptime(time, SIMPLE_TIME_FORMAT)

    except (TypeError, ValueError) as error:
        message = (
            f'The {label} "{time}" is not a time of day this can use. '
            'Give it as HH:MM, such as 18:15.'
        )
        logger.error(message)
        raise ValidationError(message) from error

    return parsed.hour * 60 + parsed.minute


def _as_time(
        minutes: int
) -> str:
    """ Return minutes since midnight as a time of day.

        Args:
            minutes (int):
                Minutes from midnight, inside one day.

        Returns:
            time (str):
                The same, as 'HH:MM'.
    """

    return f'{minutes // 60:02d}:{minutes % 60:02d}'


def timed(
        event: Event,
        shift_start: str,
        shift_end: str
) -> Event:
    """ Return an event with new shift times, checked as storable.

        The maximum is not applied here.  A maximum shortens the shift
        the offsets produced; a person setting a time has overridden
        that, and silently pulling their end time back in would read as
        the edit not having worked.

        Args:
            event (Event):
                The event as it stands.

            shift_start (str):
                The shift start it should now have, as 'HH:MM'.

            shift_end (str):
                The shift end it should now have.

        Raises:
            ValidationError:
                If the shift would end no later than it starts.  It
                cannot leave its day here: a time of day parses to
                23:59 at the latest, and a nudge checks the day's
                bounds before it formats one.

        Returns:
            event (Event):
                The event, retimed.
    """

    started = _minutes_of(time=shift_start, label='start time')
    ended = _minutes_of(time=shift_end, label='end time')

    if ended <= started:
        message = (
            f'"{event.title}" would create a shift from {shift_start} '
            f'to {shift_end}, which ends no later than it starts. A '
            'shift ends after it starts.'
        )
        logger.error(message)
        raise ValidationError(message)

    return replace(
        event,
        shift_start=shift_start,
        shift_end=shift_end
    )


def timings_for(
        event: Event,
        calendar: str,
        helpers: Helpers
) -> List[RoleTiming]:
    """ Return what the event's category asks of it.

        Read from the data model rather than from the event, because an
        event stores which opportunities it serves and how many
        volunteers each wants, and not the offsets that produced its
        times.  An event with no category asks for nothing, which is
        what leaves it holding the calendar's own times.

        Args:
            event (Event):
                The event whose category to read.

            calendar (str):
                Calendar the run was collected from.

            helpers (Helpers):
                Where the data model is read through.

        Raises:
            ValidationError:
                If the category is no longer in the data model, or its
                need IDs disagree about their offsets.

        Returns:
            timings (List[RoleTiming]):
                One per need ID that can become a shift.
    """

    if event.category is None:
        return []

    return role_timings(
        matched=helpers.category_named(
            gcal_name=calendar,
            category=event.category
        ),
        title=event.title
    )


def as_collected(
        event: Event,
        calendar: str,
        helpers: Helpers
) -> Event:
    """ Return an event with its edits undone.

        Recomputed from the calendar times and the category rather than
        restored from a stored copy: the calendar times never move, so
        the same rules that produced the event at collection produce it
        again here.  Slots go back to what the category asks for, and
        stop being marked as edited.

        Args:
            event (Event):
                The event as it stands.

            calendar (str):
                Calendar the run was collected from.

            helpers (Helpers):
                Where the data model is read through.

        Raises:
            ValidationError:
                If the event cannot become a correct shift.

        Returns:
            event (Event):
                The event as collection would produce it now.
    """

    timings = timings_for(
        event=event,
        calendar=calendar,
        helpers=helpers
    )

    if not timings:
        return replace(
            event,
            shift_start=event.calendar_start,
            shift_end=event.calendar_end,
            roles=()
        )

    start = datetime.strptime(
        f'{event.date} {event.calendar_start}',
        f'{ISO_DATE_FORMAT} {SIMPLE_TIME_FORMAT}'
    )
    end = datetime.strptime(
        f'{event.date} {event.calendar_end}',
        f'{ISO_DATE_FORMAT} {SIMPLE_TIME_FORMAT}'
    )
    shift_start, shift_end = shift_times(
        start=start,
        end=end,
        timings=timings,
        title=event.title
    )

    return replace(
        event,
        shift_start=shift_start,
        shift_end=shift_end,
        roles=tuple(timing.role for timing in timings)
    )


def required(
        value: Optional[object],
        name: str,
        op: str
) -> object:
    """ Return an operation's field, or say which one is missing.

        Args:
            value (object, optional):
                What the caller supplied.

            name (str):
                The field's name, as a caller writes it.

            op (str):
                The operation that wants it.

        Raises:
            ValidationError:
                If the field was not supplied.

        Returns:
            value (object):
                The value, once it is known to be there.
    """

    if value is None:
        message = f'A "{op}" operation needs a "{name}".'
        logger.error(message)
        raise ValidationError(message)

    return value


def nudged(
        event: Event,
        minutes: int
) -> Event:
    """ Return an event with both shift times moved.

        Args:
            event (Event):
                The event as it stands.

            minutes (int):
                How far to move them.  Negative moves them earlier.

        Raises:
            ValidationError:
                If the move would take the shift out of its day.

        Returns:
            event (Event):
                The event, moved.
    """

    started = _minutes_of(time=event.shift_start, label='start time')
    ended = _minutes_of(time=event.shift_end, label='end time')

    if started + minutes < 0 or ended + minutes >= MINUTES_PER_DAY:
        moved = 'later' if minutes > 0 else 'earlier'
        message = (
            f'"{event.title}" would leave its day if it moved '
            f'{abs(minutes)} minutes {moved}. An event stores its '
            'times as times of day, so a shift cannot cross midnight '
            'in either direction.'
        )
        logger.error(message)
        raise ValidationError(message)

    return timed(
        event=event,
        shift_start=_as_time(minutes=started + minutes),
        shift_end=_as_time(minutes=ended + minutes)
    )


def with_slots(
        event: Event,
        need_id: str,
        slots: int
) -> Event:
    """ Return an event with one role's slots set.

        Args:
            event (Event):
                The event as it stands.

            need_id (str):
                Which of its roles to set.

            slots (int):
                Volunteers wanted.

        Raises:
            ValidationError:
                If the event serves no such opportunity, or the number
                is not one a shift can ask for.

        Returns:
            event (Event):
                The event, with that role changed and marked as edited.
    """

    if slots < 0:
        message = (
            f'{slots} volunteers cannot be wanted on "{event.title}". '
            'Ask for none or more.'
        )
        logger.error(message)
        raise ValidationError(message)

    if need_id not in {role.need_id for role in event.roles}:
        message = (
            f'"{event.title}" does not create a shift under need '
            f'{need_id}, so there are no volunteers to set for it.'
        )
        logger.error(message)
        raise ValidationError(message)

    return replace(
        event,
        roles=tuple(
            replace(role, slots=slots, edited=True)
            if role.need_id == need_id
            else role
            for role in event.roles
        )
    )


def slots_reset(
        event: Event,
        context: EditContext
) -> Event:
    """ Return an event whose roles want what the opportunity asks.

        The run's own opportunities supply the number, not the data
        model as it stands now.  A run records what the opportunity
        wanted when it was collected, and resetting to today's model
        would quietly move a number the reviewer never touched.

        Args:
            event (Event):
                The event as it stands.

            context (_Context):
                The run's opportunities, by need ID.

        Raises:
            ValidationError:
                If the run holds no opportunity for one of its roles.

        Returns:
            event (Event):
                The event, with every role back to its default.
    """

    return replace(
        event,
        roles=tuple(
            EventRole(
                need_id=role.need_id,
                slots=context.default_slots(need_id=role.need_id),
                edited=False
            )
            for role in event.roles
        )
    )


def was_edited(
        event: Event,
        calendar: str,
        helpers: Helpers
) -> bool:
    """ Return whether a person has changed this event.

        The same arithmetic 'undo' runs, asked as a question rather
        than applied: an event is edited when putting it back as
        collection produced it would change it.  Written here rather
        than worked out from the stored fields because there is nothing
        stored to work it out from -- the calendar times never move, so
        an event that was nudged is one whose shift times no longer
        follow from them, and only the category's offsets say what they
        would have been.  A caller that compared them itself would be a
        second copy of '_shift_timing'.

        Covers the roles as well as the times, because undo resets
        both: a row whose volunteers were changed is a row undo would
        change, and offering no way back from it because only the times
        are looked at would be a control that lies about what it does.

        Args:
            event (Event):
                The event as it stands.

            calendar (str):
                Calendar the run was collected from.

            helpers (Helpers):
                Where the data model is read through.

        Returns:
            edited (bool):
                Whether undoing would change it.  False when the undo
                could not be carried out at all -- a category that has
                left the data model, or need IDs that now disagree
                about their offsets -- because that is the same refusal
                the operation itself would raise, and a row said to be
                editable is a row offered a control that fails.  A
                reading of a run answers rather than failing because
                the model moved under it.
    """

    try:
        return as_collected(
            event=event,
            calendar=calendar,
            helpers=helpers
        ) != event

    except ValidationError:
        return False
