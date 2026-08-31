#!/usr/bin/env python3
""" What a category asks of an event, and the shift times it produces.

    Below both callers.  Collection works these out from a calendar
    item, and an edit works them out again whenever the answer could
    change -- a different category, a different time.  Written twice,
    the two would eventually disagree, and the disagreement would show
    up as a run that previews one shift and sends another.

    **What cannot be expressed.**  An event holds one pair of shift
    times and a role per need ID, so a category whose need IDs disagree
    about their offsets describes two different shifts and cannot be
    stored as one event.  Two categories timing one Amplify listing
    differently are storable, because the roles carry their timing
    separately; one event needing two pairs of shift times is not.

    A shift running past midnight cannot be read back either, because
    the times are stored as times of day.  Both are refused here, so a
    collection and an edit refuse them alike.
"""

# Imports - Python Standard Library
from datetime import datetime, timedelta
from typing import List, Sequence, Tuple

# Imports - Local
from . import _defaults
from ._exceptions import ValidationError
from ._helpers import CategoryMatch
from ._logging import get_logger
from ._records import EventRole

# Constants
SIMPLE_TIME_FORMAT = _defaults.SIMPLE_TIME_FORMAT

# How many minutes a day holds, for saying that a shift ran past the
# end of one.
MINUTES_PER_DAY = 24 * 60

# Module logger
logger = get_logger(__name__)


def role_timings(
        matched: CategoryMatch,
        title: str
) -> List[EventRole]:
    """ Return what each of a category's need IDs asks for.

        A need ID that is empty contributes nothing.  That is what the
        review fallback holds, and what a category with an unfilled
        need ID holds: either way the event creates no shift and stops
        the run, which the caller reports rather than this.

        Args:
            matched (CategoryMatch):
                The category the event's title reached, or the one a
                person chose for it.

            title (str):
                The event's title, for the message when the category
                cannot be stored as one event.

        Raises:
            ValidationError:
                If the category's need IDs disagree about their
                offsets, which one event cannot express.

        Returns:
            timings (List[EventRole]):
                One per need ID that can become a shift, carrying
                what the category asks of it.
    """

    timings = [
        EventRole(
            need_id=str(need['id']),
            slots=int(need['slots']),
            offset_start=int(need.get('offset_start', 0)),
            offset_end=int(need.get('offset_end', 0)),
            max_length=need.get('max_length'),
            default_slots=int(need['slots'])
        )
        for need in matched.need_details.get('need_ids', ())
        if str(need.get('id', '')) != ''
    ]

    offsets = {
        (timing.offset_start, timing.offset_end)
        for timing in timings
    }

    if len(offsets) > 1:
        message = (
            f'The "{matched.category}" category, which "{title}" '
            'matched, gives its need IDs different start and end '
            'offsets. An event records one pair of shift times for '
            'every role it serves, so those need IDs describe two '
            'different shifts and cannot be collected as one event. '
            'Give them the same offsets, or split them into separate '
            'categories.'
        )
        logger.error(message)
        raise ValidationError(message)

    return timings


def shift_times(
        start: datetime,
        end: datetime,
        timings: Sequence[EventRole],
        title: str
) -> Tuple[str, str]:
    """ Return the times the shift an event creates runs between.

        The offsets move the calendar's times, and the opportunity's
        maximum shortens the result when it is longer than the
        opportunity accepts.  The stored times are the ones Amplify is
        given, so the maximum is applied here rather than left for a
        reader to apply.

        Args:
            start (datetime):
                When the event starts, in the league's zone.

            end (datetime):
                When it ends.

            timings (Sequence[EventRole]):
                The event's roles.  All of them agree about the
                offsets by the time this is called.

            title (str):
                The event's title, for the messages.

        Raises:
            ValidationError:
                If the offsets leave the shift ending no later than it
                starts, or running past the end of the day.

        Returns:
            times (Tuple[str, str]):
                The shift's start and end, as times of day.
    """

    first = timings[0]
    shift_start = start + timedelta(minutes=first.offset_start)
    shift_end = end + timedelta(minutes=first.offset_end)
    minutes = round((shift_end - shift_start).total_seconds() / 60)

    if minutes <= 0:
        message = (
            f'"{title}" would create a shift ending no later than it '
            f'starts ({minutes} minutes). The offsets on its category '
            'are wrong for this event.'
        )
        logger.error(message)
        raise ValidationError(message)

    # The smallest maximum among the roles is the one that binds, the
    # same way a reader works out which maximum shortened a shift.
    maximums = [
        role.max_length
        for role in timings
        if role.max_length is not None
    ]

    if maximums and minutes > min(maximums):
        minutes = min(maximums)
        shift_end = shift_start + timedelta(minutes=minutes)

    started = shift_start.hour * 60 + shift_start.minute

    if started + minutes >= MINUTES_PER_DAY:
        message = (
            f'"{title}" would create a shift running past the end of '
            'the day. An event stores its times as times of day, so a '
            'shift crossing midnight cannot be read back as the one '
            'that was stored.'
        )
        logger.error(message)
        raise ValidationError(message)

    return (
        shift_start.strftime(SIMPLE_TIME_FORMAT),
        shift_end.strftime(SIMPLE_TIME_FORMAT)
    )
