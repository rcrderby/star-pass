#!/usr/bin/env python3
""" Pulling into a run an event the search missed.

    The one thing a reviewer can add to a revision, and it is not a
    free hand: what may be pulled in is a row the collection already
    stored, under the one reason that means nobody looked for the
    event.  The other three reasons describe events that cannot become
    a correct shift -- an excluded title, an all-day event, an untitled
    one -- and they are refused here rather than by a disabled button,
    because a button and the operation behind it would eventually
    disagree.

    In the core, not the service.  Nothing here is about HTTP, and the
    event it builds is the one a collection would have built, through
    the same '_building' both call (D1).

    **The row it came from stays.**  The event is added to the current
    revision and the record of what the window left out is untouched,
    which is what lets reverting to the first revision drop the
    hand-added events and leave the reviewer looking at the list they
    started from.  What keeps it off that list meanwhile is the
    revision holding it, not the row being gone.

    **A pulled-in event may name an opportunity the run has never
    read.** Nobody searched for this event, so its category is not
    necessarily one the collection met, and the run has to gain the
    opportunity before it can label the row. That is the one upstream
    request this operation makes, and it is made only for a need ID
    the run does not already hold.
"""

# Imports - Python Standard Library
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# Imports - Local
from ._building import event_from, opportunity_read
from ._database import transaction
from ._exceptions import ValidationError
from ._helpers import Helpers
from ._logging import get_logger
from ._records import (
    Event,
    LogEntry,
    Opportunity,
    Run,
    UncollectedEvent,
    UNCOLLECTED_SEARCH
)
from ._repository import (
    ChangeLogRepository,
    EventRepository,
    RunRepository,
    UncollectedRepository
)
from ._shift_timing import RoleTiming, role_timings

# Constants
# What the change log says about a pulled-in event.  It names the
# reason as well as the title, because "why is this here" is the
# question a later reader of the log has about a row no search found.
ADDED_ENTRY = 'Added "{title}", which no configured search returned.'

# Module logger
logger = get_logger(__name__)


def _refuse(
        message: str
) -> ValidationError:
    """ Return the failure for something that will not be added.

        Logged where it is built rather than by each caller, so a
        refusal reaches the service log whichever of them raised it.

        Args:
            message (str):
                What the caller is told.

        Returns:
            error (ValidationError):
                The failure to raise.
    """

    logger.error(message)

    return ValidationError(message)


def _addable(
        uncollected: Optional[UncollectedEvent],
        run_id: str,
        event_id: str
) -> UncollectedEvent:
    """ Return the row to pull in, or refuse to pull anything in.

        Args:
            uncollected (UncollectedEvent | None):
                What the run left out under that identifier, if
                anything.

            run_id (str):
                Run being added to, for the message.

            event_id (str):
                What was asked for, for the message.

        Raises:
            ValidationError:
                If there is no such row, or it is not one that may be
                pulled in.

        Returns:
            uncollected (UncollectedEvent):
                The row to build an event from.
    """

    if uncollected is None:
        raise _refuse(
            f'Run {run_id} left nothing out with the identifier '
            f'"{event_id}". Only an event the run recorded as not '
            'collected may be pulled into it.'
        )

    if uncollected.reason != UNCOLLECTED_SEARCH:
        raise _refuse(
            f'"{event_id}" was left out of run {run_id} because it is '
            f'{uncollected.reason}, which describes an event that '
            'cannot become a correct shift. Only an event no '
            'configured search returned may be pulled in.'
        )

    if not uncollected.title:
        raise _refuse(
            f'"{event_id}" has no title to match to an opportunity, so '
            'it cannot become a shift.'
        )

    return uncollected


def _moments(
        uncollected: UncollectedEvent
) -> Tuple[datetime, datetime]:
    """ Return when a stored row says its event ran.

        Read without a zone.  The stored values are already in the
        zone the calendar was read in, and everything done with them
        -- adding the offsets, measuring the shift, reading its hour --
        is arithmetic within one day, which a zone would only give a
        second chance to be wrong about.

        Args:
            uncollected (UncollectedEvent):
                The row to read.

        Raises:
            ValidationError:
                If it does not carry a day and both of its times.

        Returns:
            moments (Tuple[datetime, datetime]):
                When the event starts and ends.
    """

    if not (
        uncollected.date
        and uncollected.calendar_start
        and uncollected.calendar_end
    ):
        raise _refuse(
            f'"{uncollected.id}" does not carry a day and two times, '
            'so there is nothing to build a shift from. Recollect the '
            'run if the calendar has been corrected since.'
        )

    return (
        datetime.fromisoformat(
            f'{uncollected.date}T{uncollected.calendar_start}'
        ),
        datetime.fromisoformat(
            f'{uncollected.date}T{uncollected.calendar_end}'
        )
    )


def _agrees(
        timing: RoleTiming,
        opportunity: Opportunity
) -> None:
    """ Fail when an event times an opportunity the run already holds.

        A run records one set of offsets per opportunity, so an event
        arriving with another set describes a shift the run cannot
        store beside the ones it has.  Refused for the reason a
        collection refuses the same disagreement between two of its
        own categories.

        Args:
            timing (RoleTiming):
                What the event being added asks for.

            opportunity (Opportunity):
                What the run already records.

        Raises:
            ValidationError:
                If the two disagree.

        Returns:
            None.
    """

    if (
        timing.offset_start,
        timing.offset_end,
        timing.max_length
    ) != (
        opportunity.offset_start,
        opportunity.offset_end,
        opportunity.max_length
    ):
        raise _refuse(
            f'This event times need ID {opportunity.need_id} '
            'differently from the way the run already records it. A '
            'run records one set of offsets per opportunity, so those '
            'cannot both be stored. Recollect the run to read the '
            'data model again.'
        )

    return None


def _opportunities_for(
        timings: List[RoleTiming],
        held: Dict[str, Opportunity],
        helpers: Helpers
) -> List[Opportunity]:
    """ Return the opportunities the run has to gain, if any.

        Amplify is asked only about a need ID the run does not
        already hold.  The titles it already has were read when it was
        collected, and reading them again would spend a request to
        learn what is stored.

        Args:
            timings (List[RoleTiming]):
                What the event's roles ask for.

            held (Dict[str, Opportunity]):
                What the run already records, by need ID.

            helpers (Helpers):
                What the opportunity reads are sent through.

        Raises:
            ValidationError:
                If the event times one the run holds differently.

            UpstreamError:
                If an opportunity cannot be read.

        Returns:
            gained (List[Opportunity]):
                One per need ID the run does not hold yet.
    """

    gained = []

    for timing in timings:
        need_id = timing.role.need_id

        if need_id in held:
            _agrees(timing=timing, opportunity=held[need_id])

            continue

        gained.append(
            opportunity_read(
                helpers=helpers,
                need_id=need_id,
                timing=timing
            )
        )

    return gained


def _built(
        run: Run,
        uncollected: UncollectedEvent,
        held: Dict[str, Opportunity]
) -> Tuple[Event, List[Opportunity]]:
    """ Return what the row becomes and what the run gains for it.

        The two together, because both come from one match: the
        category the title reached decides the event's roles and its
        shift times, and the same categories name the opportunities
        the run has to be able to label them with.

        Args:
            run (Run):
                The run being added to, which names the calendar the
                title is matched against.

            uncollected (UncollectedEvent):
                The row to pull in, which has already been found
                addable.

            held (Dict[str, Opportunity]):
                What the run already records, by need ID.

        Raises:
            ValidationError:
                If the event cannot become a correct shift, or it
                times an opportunity the run holds differently.

            UpstreamError:
                If an opportunity it names cannot be read.

        Returns:
            built (Tuple[Event, List[Opportunity]]):
                The event as the revision will hold it, and the
                opportunities the run does not hold yet.
    """

    helpers = Helpers()
    matched = helpers.match_shift_info(
        gcal_name=run.calendar,
        need_name=uncollected.title
    )
    start, end = _moments(uncollected=uncollected)

    return (
        event_from(
            identifier=uncollected.id,
            title=uncollected.title,
            start=start,
            end=end,
            matched=matched,
            added_by_hand=True
        ),
        _opportunities_for(
            timings=role_timings(
                matched=matched,
                title=uncollected.title
            ),
            held=held,
            helpers=helpers
        )
    )


def add_event(
        connection: sqlite3.Connection,
        run_id: str,
        event_id: str,
        principal_id: str
) -> Optional[Tuple[Event, LogEntry]]:
    """ Pull an event nobody searched for into a run's revision.

        Args:
            connection (sqlite3.Connection):
                Connection to write on.

            run_id (str):
                Run whose current revision to add to.

            event_id (str):
                The calendar's identifier for the event, as the run's
                record of what it left out carries it.

            principal_id (str):
                Who pulled it in (D13).

        Raises:
            ValidationError:
                If the run has collected nothing yet, if there is no
                such row, if it is not one that may be pulled in, if
                the revision already holds it, or if it cannot become
                a correct shift.

            UpstreamError:
                If an opportunity the event names cannot be read.

        Returns:
            added (Tuple[Event, LogEntry] | None):
                The event as the revision now holds it and the entry
                written about it, or None when there is no such run.
    """

    runs = RunRepository(connection=connection)
    run = runs.get(run_id=run_id)

    if run is None:
        return None

    revision = run.current_revision

    if revision == 0:
        raise _refuse(
            f'Run {run_id} has collected nothing yet, so there is no '
            'revision to add an event to.'
        )

    events = EventRepository(connection=connection)

    if events.get(
        run_id=run_id,
        revision=revision,
        event_id=event_id
    ) is not None:
        raise _refuse(
            f'Revision {revision} of run {run_id} already holds '
            f'"{event_id}".'
        )

    uncollected = _addable(
        uncollected=UncollectedRepository(connection=connection).get(
            run_id=run_id,
            event_id=event_id
        ),
        run_id=run_id,
        event_id=event_id
    )
    held = {
        opportunity.need_id: opportunity
        for opportunity in runs.get_opportunities(run_id=run_id)
    }
    event, gained = _built(
        run=run,
        uncollected=uncollected,
        held=held
    )

    with transaction(connection=connection):
        events.add(
            run_id=run_id,
            revision=revision,
            event=event
        )

        if gained:
            runs.set_opportunities(
                run_id=run_id,
                opportunities=list(held.values()) + gained
            )

        entry = ChangeLogRepository(connection=connection).add(
            run_id=run_id,
            revision=revision,
            principal_id=principal_id,
            entry=ADDED_ENTRY.format(title=uncollected.title)
        )

    message = (
        f'Pulled "{uncollected.id}" into revision {revision} of run '
        f'{run_id}'
    )
    logger.info(message)

    return event, entry
