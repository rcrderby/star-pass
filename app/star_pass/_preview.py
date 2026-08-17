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

    **What Amplify already has is subtracted, not mentioned.**  The
    shifts an opportunity already holds are read live, by
    '_opportunities.shifts_in_amplify', and a shift the revision asks
    for that is already there is reported as skipped rather than
    counted in what would be created.  The send path re-asks the same
    way inside its own transaction, so the number somebody confirmed
    against is the number of rows that will arrive.  A count that
    included rows Amplify already holds would be a promise the send
    could not keep.

    The live answer is a parameter rather than something read here.
    This module is pure, so a caller cannot be told what a send would
    do without having asked Amplify first -- there is no default that
    quietly means "nothing exists yet".
"""

# Imports - Python Standard Library
from dataclasses import dataclass
from typing import (
    AbstractSet,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Set,
    Tuple
)

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
class SkippedShift:
    """ One shift the revision asks for that Amplify already has.

        Named per shift and never only counted (D16).  A count says how
        many rows will not arrive; it does not say which, and the
        reader deciding whether that is right is deciding about
        particular days and times.

        Attributes:
            need_id (str):
                Opportunity the shift would have been created under.

            date (str):
                Day it falls on, as an ISO date.

            shift_start (str):
                Time of day it starts.

            shift_end (str):
                Time of day it ends.
    """

    need_id: str
    date: str
    shift_start: str
    shift_end: str


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
                so two events sending the same row count once, and
                without the ones Amplify already holds.

            already_in_amplify (int):
                How many of the shifts this opportunity is asked for
                are already there, and so would be skipped.

            slots (int):
                Volunteers wanted across the shifts that would be
                created.  A shift that is skipped asks for nobody: it
                exists already, with whatever it was created wanting.

            first_date (str, optional):
                Earliest day a shift would be created on, or None when
                none would be.

            last_date (str, optional):
                Latest day a shift would be created on, or None when
                none would be.  Of the shifts that would be created,
                not of every event under this opportunity: a reader
                checking these dates against Amplify is checking what
                is about to arrive.
    """

    need_id: str
    title: Optional[str]
    will_create: int
    already_in_amplify: int
    slots: int
    first_date: Optional[str]
    last_date: Optional[str]


@dataclass(frozen=True)
class Preview:
    """ What sending a revision would do.

        Attributes:
            will_create (int):
                Shifts that would be created in total, without the ones
                Amplify already holds.

            already_in_amplify (int):
                Shifts the revision asks for that Amplify already has.
                They are skipped rather than sent again, and 'skipped'
                names them.

            repeated_rows (int):
                How many shifts the revision asks for more than once.
                They create one shift, not several, and the figure is
                here so a reader is told rather than left to wonder
                why the total is below the number of rows.

            blocking_events (int):
                Events that cannot be sent.  Above zero means nothing
                can be sent at all.

            rows (Tuple[PreviewRow, ...]):
                One per opportunity the revision asks for a shift
                under, by need ID.  An opportunity every one of whose
                shifts already exists keeps its row, saying so.

            skipped (Tuple[SkippedShift, ...]):
                Every shift Amplify already has, by need ID and then by
                when it falls.

            blockers (Tuple[Blocker, ...]):
                Every reason an event cannot be sent, in the order the
                events were given.  One event with two things wrong
                with it appears twice.
    """

    will_create: int
    already_in_amplify: int
    repeated_rows: int
    blocking_events: int
    rows: Tuple[PreviewRow, ...]
    skipped: Tuple[SkippedShift, ...]
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


def _dates(
        identities: Iterable[ShiftIdentity]
) -> Tuple[Optional[str], Optional[str]]:
    """ Return the first and last day a set of shifts falls on.

        Args:
            identities (Iterable[ShiftIdentity]):
                The shifts to bound.

        Returns:
            bounds (Tuple[str | None, str | None]):
                Earliest and latest day, or two Nones when there are no
                shifts to bound.
    """

    # Position 1 of an identity is the date it falls on.
    dates = sorted(identity[1] for identity in identities)

    return (dates[0], dates[-1]) if dates else (None, None)


def _row(
        need_id: str,
        opportunity: Optional[Opportunity],
        creating: List[ShiftIdentity],
        skipping: int,
        slots: int
) -> PreviewRow:
    """ Return what one opportunity would receive.

        Args:
            need_id (str):
                The opportunity's need ID.

            opportunity (Opportunity, optional):
                The stored opportunity, or None when the run has none
                for this need ID.

            creating (List[ShiftIdentity]):
                The distinct shifts that would be created under it.

            skipping (int):
                How many more it is asked for that Amplify already has.

            slots (int):
                Volunteers wanted across the ones being created.

        Returns:
            row (PreviewRow):
                What the opportunity would receive.
    """

    first_date, last_date = _dates(identities=creating)

    return PreviewRow(
        need_id=need_id,
        title=opportunity.title if opportunity is not None else None,
        will_create=len(creating),
        already_in_amplify=skipping,
        slots=slots,
        first_date=first_date,
        last_date=last_date
    )


def _skipped(
        identities: Iterable[ShiftIdentity]
) -> Tuple[SkippedShift, ...]:
    """ Return the shifts Amplify already has, in a settled order.

        Sorted rather than left in whatever order a set iterated in: a
        reader comparing two previews of one run is comparing lists,
        and a list that reordered itself between readings would look
        like a change.

        Args:
            identities (Iterable[ShiftIdentity]):
                The shifts that would be skipped.

        Returns:
            skipped (Tuple[SkippedShift, ...]):
                One per shift, by need ID and then by when it falls.
    """

    return tuple(
        SkippedShift(
            need_id=need_id,
            date=date,
            shift_start=shift_start,
            shift_end=shift_end
        )
        for need_id, date, shift_start, shift_end in sorted(identities)
    )


@dataclass
class _Gathered:
    """ What one pass over a revision's events found.

        Mutable and private, unlike everything else here: it is the
        working state of a single pass, filled in as the events are
        read, and it exists so that the reading and the reporting are
        two things rather than one long one.

        Attributes:
            seen (Set[ShiftIdentity]):
                Every distinct shift the revision asks for, whether
                Amplify has it or not.

            creating (Dict[str, List[ShiftIdentity]]):
                The shifts that would be created, by need ID.  An
                opportunity every one of whose shifts already exists
                is here with an empty list, because it still has a row
                to show.

            skipping (Dict[str, int]):
                How many of each opportunity's shifts already exist.

            wanted (Dict[str, int]):
                Volunteers asked for across the shifts being created,
                by need ID.

            blockers (List[Blocker]):
                Every reason an event cannot be sent.

            blocked (int):
                How many events cannot be sent.  Not the length of
                'blockers': one event with two things wrong with it is
                two reasons and one event.

            repeats (int):
                How many shifts the revision asks for more than once.
    """

    seen: Set[ShiftIdentity]
    creating: Dict[str, List[ShiftIdentity]]
    skipping: Dict[str, int]
    wanted: Dict[str, int]
    blockers: List[Blocker]
    blocked: int
    repeats: int


def _gather(
        events: Iterable[Event],
        existing: AbstractSet[ShiftIdentity]
) -> _Gathered:
    """ Read a revision's events once, and report what they ask for.

        Args:
            events (Iterable[Event]):
                Every event in the revision, in the order they are
                shown.

            existing (AbstractSet[ShiftIdentity]):
                The shifts Amplify already holds.

        Raises:
            ValueError:
                If an event's shift times are not times.

        Returns:
            gathered (_Gathered):
                What the pass found.
    """

    found = _Gathered(
        seen=set(),
        creating={},
        skipping={},
        wanted={},
        blockers=[],
        blocked=0,
        repeats=0
    )

    for event in events:
        reasons = blockers(event=event)

        if reasons:
            # A blocked event creates nothing, so it is counted as a
            # reason to stop rather than as a shift that would arrive.
            found.blocked += 1
            found.blockers.extend(
                Blocker(event_id=event.id, reason=reason)
                for reason in reasons
            )
            continue

        for role in event.roles:
            identity = shift_identity(event=event, role=role)
            need_id = role.need_id

            if identity in found.seen:
                found.repeats += 1
                continue

            found.seen.add(identity)

            if identity in existing:
                # Asked for, and already there.  The opportunity keeps
                # a place in the grouping without the shift becoming
                # something that would arrive.
                found.skipping[need_id] = found.skipping.get(need_id, 0) + 1
                found.creating.setdefault(need_id, [])
                continue

            found.creating.setdefault(need_id, []).append(identity)
            found.wanted[need_id] = found.wanted.get(need_id, 0) + role.slots

    return found


def preview(
        events: Iterable[Event],
        opportunities: Mapping[str, Opportunity],
        existing: AbstractSet[ShiftIdentity]
) -> Preview:
    """ Return what sending a revision would create.

        Args:
            events (Iterable[Event]):
                Every event in the revision, in the order they are
                shown.

            opportunities (Mapping[str, Opportunity]):
                The run's opportunities, by need ID, which label the
                rows.

            existing (AbstractSet[ShiftIdentity]):
                The shifts Amplify already holds, as
                '_opportunities.shifts_in_amplify' reads them.  Empty
                is a real answer -- the opportunities hold nothing yet
                -- and is never a stand-in for not having asked.

        Raises:
            ValueError:
                If an event's shift times are not times.

        Returns:
            preview (Preview):
                What a send would do.
    """

    found = _gather(events=events, existing=existing)
    already = found.seen & existing

    return Preview(
        will_create=len(found.seen) - len(already),
        already_in_amplify=len(already),
        repeated_rows=found.repeats,
        blocking_events=found.blocked,
        rows=tuple(
            _row(
                need_id=need_id,
                opportunity=opportunities.get(need_id),
                creating=identities,
                skipping=found.skipping.get(need_id, 0),
                slots=found.wanted.get(need_id, 0)
            )
            for need_id, identities in sorted(found.creating.items())
        ),
        skipped=_skipped(identities=already),
        blockers=tuple(found.blockers)
    )
