#!/usr/bin/env python3
""" What sending a revision would create, worked out before it does.

    A person about to write to a live volunteer system is shown this
    first, and the confirmation restates it (D11).  So the numbers here
    are the ones somebody decides on, and every one of them has to mean
    exactly what it says.

    Grouped by opportunity and never by category.  Several categories
    share one Amplify listing, so grouping by category would show the
    same listing twice under two names and split a total the reader is
    about to check against Amplify itself.

    Counted by shift identity -- need ID, date, start and end (D16) --
    and never by how many events there are.  Two events that would send
    the same row create one shift, and a count of events would promise
    two.

    In the core rather than the service, because the command line
    client previews the same run and must be shown the same figures
    (D1).

    **What is not here yet: which shifts Amplify already has.**  That
    needs a read of the live opportunity, which is written with the
    send path that re-checks the same thing inside its transaction, so
    that both ask the question the same way.  Until then this answers
    what the stored revision would create, and a caller is not told
    that some of it already exists.
"""

# Imports - Python Standard Library
from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Optional, Set, Tuple

# Imports - Local
from ._derived import shift_identity, shift_length
from ._records import Event, Opportunity, ShiftIdentity

# Why an event cannot become a shift.  Each is a thing the person
# reviewing the run has to fix; the run stops rather than dropping the
# event, because a missing shift is invisible until volunteers cannot
# sign up.
BLOCKER_NO_OPPORTUNITY = 'no_opportunity'
BLOCKER_ENDS_BEFORE_START = 'ends_before_start'
BLOCKER_NO_SLOTS = 'no_slots'
BLOCKER_REASONS = (
    BLOCKER_NO_OPPORTUNITY,
    BLOCKER_ENDS_BEFORE_START,
    BLOCKER_NO_SLOTS
)


@dataclass(frozen=True)
class Blocker:
    """ One reason one event cannot become a shift.

        Attributes:
            event_id (str):
                Event that cannot be sent.

            reason (str):
                One of 'BLOCKER_REASONS'.
    """

    event_id: str
    reason: str


@dataclass(frozen=True)
class PreviewRow:
    """ What one Amplify opportunity would receive.

        Attributes:
            need_id (str):
                Amplify need ID the shifts would be created under.

            title (str, optional):
                The opportunity's title, or None when the run stored
                no opportunity for this need ID, which means
                collection did not resolve one.

            will_create (int):
                How many shifts would be created, counted by identity,
                so two events sending the same row count once.

            slots (int):
                Volunteers wanted across those shifts.

            first_date (str):
                Earliest day a shift would be created on.

            last_date (str):
                Latest day a shift would be created on.  Of the shifts
                that would be created, not of every event under this
                opportunity: a reader checking these dates against
                Amplify is checking what is about to arrive.
    """

    need_id: str
    title: Optional[str]
    will_create: int
    slots: int
    first_date: str
    last_date: str


@dataclass(frozen=True)
class Preview:
    """ What sending a revision would do.

        Attributes:
            will_create (int):
                Shifts that would be created in total.

            repeated_rows (int):
                How many shifts the revision asks for more than once.
                They create one shift, not several, and the figure is
                here so a reader is told rather than left to wonder
                why the total is below the number of rows.

            blocking_events (int):
                Events that cannot be sent.  Above zero means nothing
                can be sent at all.

            rows (Tuple[PreviewRow, ...]):
                One per opportunity that would receive a shift, by
                need ID.

            blockers (Tuple[Blocker, ...]):
                Every reason an event cannot be sent, in the order the
                events were given.  One event with two things wrong
                with it appears twice.
    """

    will_create: int
    repeated_rows: int
    blocking_events: int
    rows: Tuple[PreviewRow, ...]
    blockers: Tuple[Blocker, ...]


def blockers(
        event: Event
) -> Tuple[str, ...]:
    """ Return every reason an event cannot become a shift.

        All of them rather than the first, because a person fixing one
        and finding another would be back where they started.

        Args:
            event (Event):
                The event to examine.

        Raises:
            ValueError:
                If the event's shift times are not times.

        Returns:
            reasons (Tuple[str, ...]):
                Reasons from 'BLOCKER_REASONS', empty for an event
                that can be sent.
    """

    found = []

    if not event.roles:
        found.append(BLOCKER_NO_OPPORTUNITY)

    if shift_length(event=event) <= 0:
        # Amplify is sent a start and a duration, so a shift ending
        # when or before it starts is a row it would reject.
        found.append(BLOCKER_ENDS_BEFORE_START)

    if any(role.slots <= 0 for role in event.roles):
        found.append(BLOCKER_NO_SLOTS)

    return tuple(found)


def _row(
        need_id: str,
        opportunity: Optional[Opportunity],
        identities: List[ShiftIdentity],
        slots: int
) -> PreviewRow:
    """ Return what one opportunity would receive.

        Args:
            need_id (str):
                The opportunity's need ID.

            opportunity (Opportunity, optional):
                The stored opportunity, or None when the run has none
                for this need ID.

            identities (List[ShiftIdentity]):
                The distinct shifts that would be created under it.

            slots (int):
                Volunteers wanted across them.

        Returns:
            row (PreviewRow):
                What the opportunity would receive.
    """

    # Position 1 of an identity is the date it falls on.
    dates = sorted(identity[1] for identity in identities)

    return PreviewRow(
        need_id=need_id,
        title=opportunity.title if opportunity is not None else None,
        will_create=len(identities),
        slots=slots,
        first_date=dates[0],
        last_date=dates[-1]
    )


def preview(
        events: Iterable[Event],
        opportunities: Mapping[str, Opportunity]
) -> Preview:
    """ Return what sending a revision would create.

        Args:
            events (Iterable[Event]):
                Every event in the revision, in the order they are
                shown.

            opportunities (Mapping[str, Opportunity]):
                The run's opportunities, by need ID, which label the
                rows.

        Raises:
            ValueError:
                If an event's shift times are not times.

        Returns:
            preview (Preview):
                What a send would do.
    """

    seen: Set[ShiftIdentity] = set()
    grouped: Dict[str, List[ShiftIdentity]] = {}
    wanted: Dict[str, int] = {}
    found: List[Blocker] = []
    blocked = 0
    repeats = 0

    for event in events:
        reasons = blockers(event=event)

        if reasons:
            # A blocked event creates nothing, so it is counted as a
            # reason to stop rather than as a shift that would arrive.
            blocked += 1
            found.extend(
                Blocker(event_id=event.id, reason=reason)
                for reason in reasons
            )
            continue

        for role in event.roles:
            identity = shift_identity(event=event, role=role)

            if identity in seen:
                repeats += 1
                continue

            seen.add(identity)
            grouped.setdefault(role.need_id, []).append(identity)
            wanted[role.need_id] = wanted.get(role.need_id, 0) + role.slots

    rows = tuple(
        _row(
            need_id=need_id,
            opportunity=opportunities.get(need_id),
            identities=identities,
            slots=wanted[need_id]
        )
        for need_id, identities in sorted(grouped.items())
    )

    return Preview(
        will_create=len(seen),
        repeated_rows=repeats,
        blocking_events=blocked,
        rows=rows,
        blockers=tuple(found)
    )
