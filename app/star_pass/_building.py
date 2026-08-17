#!/usr/bin/env python3
""" What a run stores about an event, and about the opportunity it names.

    Below both callers.  A collection builds these for every event a
    calendar window held, and pulling an event in by hand builds one
    for the event nobody searched for -- and the two have to produce
    the same thing.  A hand-added event that reached its shift times a
    second way would be a row the reviewer could not tell from a
    collected one until Amplify received a different shift.

    Nothing here reads a calendar or a database.  It is given what the
    calendar said and the category the title reached, and returns the
    records a revision holds; the caller decides where those came from
    and when they become durable.
"""

# Imports - Python Standard Library
from datetime import datetime

# Imports - Local
from . import _defaults
from ._helpers import CategoryMatch, Helpers
from ._opportunities import public_url, read_need, title_of
from ._records import Event, Opportunity
from ._shift_timing import RoleTiming, role_timings, shift_times

# Constants
ISO_DATE_FORMAT = _defaults.ISO_DATE_FORMAT
SIMPLE_TIME_FORMAT = _defaults.SIMPLE_TIME_FORMAT


def event_from(
        identifier: str,
        title: str,
        start: datetime,
        end: datetime,
        matched: CategoryMatch,
        *,
        added_by_hand: bool = False
) -> Event:
    """ Return one event as a revision holds it.

        Args:
            identifier (str):
                The calendar's identifier for the event, which is what
                a revision addresses it by.

            title (str):
                Event title, as the calendar gave it.

            start (datetime):
                When the event starts, in the zone the calendar is
                read in.

            end (datetime):
                When it ends, in the same zone.

            matched (CategoryMatch):
                The category its title reached.

            added_by_hand (bool):
                Whether a person pulled it in rather than the search
                finding it.  Defaults to False, which is every event a
                collection builds.

        Raises:
            ValidationError:
                If the event cannot become a correct shift.

        Returns:
            event (Event):
                The event, with a role per need ID it serves.
    """

    timings = role_timings(matched=matched, title=title)

    # An event serving no opportunity has no shift to time.  It is
    # stored with the calendar's own times, and blocks the run for
    # having no role at all.
    shift_start, shift_end = (
        shift_times(
            start=start,
            end=end,
            timings=timings,
            title=title
        )
        if timings
        else (
            start.strftime(SIMPLE_TIME_FORMAT),
            end.strftime(SIMPLE_TIME_FORMAT)
        )
    )

    return Event(
        id=identifier,
        title=title,
        date=start.strftime(ISO_DATE_FORMAT),
        calendar_start=start.strftime(SIMPLE_TIME_FORMAT),
        calendar_end=end.strftime(SIMPLE_TIME_FORMAT),
        shift_start=shift_start,
        shift_end=shift_end,
        category=matched.category,
        match=matched.match,
        added_by_hand=added_by_hand,
        roles=tuple(timing.role for timing in timings)
    )


def opportunity_read(
        helpers: Helpers,
        need_id: str,
        timing: RoleTiming
) -> Opportunity:
    """ Return the opportunity a need ID names, as Amplify calls it.

        The read and the record are one function because both callers
        want both: a collection labels every need ID its events
        reached, and a hand-added event labels the ones the run has
        never read.  Split, the reading would be written twice and one
        of them would eventually store a run's own guess at a title.

        Args:
            helpers (Helpers):
                What the read is sent through.

            need_id (str):
                Amplify need ID.

            timing (RoleTiming):
                What the data model says about it.

        Raises:
            UpstreamError:
                If the opportunity cannot be read.

        Returns:
            opportunity (Opportunity):
                The opportunity as the run stores it.
    """

    return Opportunity(
        need_id=need_id,
        title=title_of(
            need=read_need(helpers=helpers, need_id=need_id)
        ),
        url=public_url(need_id=need_id),
        max_length=timing.max_length,
        offset_start=timing.offset_start,
        offset_end=timing.offset_end,
        default_slots=timing.role.slots
    )
