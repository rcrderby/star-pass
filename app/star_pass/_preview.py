#!/usr/bin/env python3
""" What sending a revision would create, worked out before it does.

    Grouped by opportunity, because several categories can share one
    Amplify listing.  Counted by shift identity - need ID, date, start
    and end - because two events that would send the same row create
    one shift.

    What Amplify already holds is subtracted rather than mentioned:
    the shifts an opportunity holds are read live and passed in, and a
    row already there is reported as skipped.  The live answer is a
    parameter rather than read here, so this module stays pure and no
    caller is given a figure without having asked Amplify first.

    The send works from the same two answers, 'asked_for' and
    'split_by_existing', so a preview reports what a send creates.
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
    Sequence,
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
class PlannedShift:
    """ One shift a revision asks for, and what it asks Amplify for.

        The first four fields are exactly a 'ShiftIdentity' (D16), so
        'identity' is what decides whether Amplify already has this
        row.  The fifth is the only thing a send adds to it.

        Attributes:
            need_id, date, shift_start, shift_end (str):
                The row, as '_derived.shift_identity' builds one.

            slots (int):
                Volunteers wanted.
    """

    need_id: str
    date: str
    shift_start: str
    shift_end: str
    slots: int

    @property
    def identity(self) -> ShiftIdentity:
        """ Return the row this shift is, for comparing with another.

            Args:
                None.

            Returns:
                identity (ShiftIdentity):
                    Need ID, date, start and end.
        """

        return (
            self.need_id,
            self.date,
            self.shift_start,
            self.shift_end
        )


@dataclass(frozen=True)
class Asked:
    """ What a revision asks for, before Amplify has been consulted.

        Attributes:
            by_opportunity (Dict[str, Tuple[PlannedShift, ...]]):
                The distinct shifts asked for, by need ID, in the order
                the events were read.  An opportunity nothing sendable
                names is absent rather than empty.

            blockers (Tuple[Blocker, ...]):
                Every reason an event cannot be sent, in the order the
                events were given.

            blocking_events (int):
                How many events cannot be sent.  Not the length of
                'blockers': one event with two things wrong with it is
                two reasons and one event.

            repeated_rows (int):
                How many shifts the revision asks for more than once.
    """

    by_opportunity: Dict[str, Tuple[PlannedShift, ...]]
    blockers: Tuple[Blocker, ...]
    blocking_events: int
    repeated_rows: int


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
        shifts: Iterable[PlannedShift]
) -> Tuple[Optional[str], Optional[str]]:
    """ Return the first and last day a set of shifts falls on.

        Args:
            shifts (Iterable[PlannedShift]):
                The shifts to bound.

        Returns:
            bounds (Tuple[str | None, str | None]):
                Earliest and latest day, or two Nones when there are no
                shifts to bound.
    """

    dates = sorted(shift.date for shift in shifts)

    return (dates[0], dates[-1]) if dates else (None, None)


def _row(
        need_id: str,
        opportunity: Optional[Opportunity],
        creating: Sequence[PlannedShift],
        already: Sequence[PlannedShift]
) -> PreviewRow:
    """ Return what one opportunity would receive.

        Args:
            need_id (str):
                The opportunity's need ID.

            opportunity (Opportunity, optional):
                The stored opportunity, or None when the run has none
                for this need ID.

            creating (Sequence[PlannedShift]):
                The distinct shifts that would be created under it.

            already (Sequence[PlannedShift]):
                The ones it is asked for that Amplify already has.

        Returns:
            row (PreviewRow):
                What the opportunity would receive.
    """

    first_date, last_date = _dates(shifts=creating)

    return PreviewRow(
        need_id=need_id,
        title=opportunity.title if opportunity is not None else None,
        will_create=len(creating),
        already_in_amplify=len(already),
        slots=sum(shift.slots for shift in creating),
        first_date=first_date,
        last_date=last_date
    )


def _ordered(rows: Iterable[PreviewRow]) -> Tuple[PreviewRow, ...]:
    """ Return the rows in the order a reader reads them.

        By the title, not by the need ID the split is keyed on: each
        client draws the title, so a table ordered by the ID looks to
        a reader like a table in no order at all.

        Sorted on the same fallback the clients draw, and folded:
        unfolded, every capital sorts before every lower case letter.

        Two opportunities Amplify gave one title stay in need ID
        order, because the sort is stable.  The *skipped* list is left
        alone; its order is published as by need ID.

        Args:
            rows (Iterable[PreviewRow]):
                The rows, in whatever order they were built.

        Returns:
            ordered (Tuple[PreviewRow, ...]):
                Them, by title.
    """

    return tuple(
        sorted(
            rows,
            key=lambda row: (row.title or row.need_id).casefold()
        )
    )


def _skipped(
        shifts: Iterable[PlannedShift]
) -> Tuple[SkippedShift, ...]:
    """ Return the shifts Amplify already has, in a settled order.

        Sorted rather than left in the order the opportunities were
        read: a reader comparing two previews of one run is comparing
        lists, and a list that reordered itself between readings would
        look like a change.

        The volunteers a skipped shift would have asked for are not
        carried over.  It exists already, wanting whatever it was
        created wanting, and a number here would read as a number
        Amplify holds.

        Args:
            shifts (Iterable[PlannedShift]):
                The shifts that would be skipped.

        Returns:
            skipped (Tuple[SkippedShift, ...]):
                One per shift, by need ID and then by when it falls.
    """

    return tuple(
        SkippedShift(
            need_id=shift.need_id,
            date=shift.date,
            shift_start=shift.shift_start,
            shift_end=shift.shift_end
        )
        for shift in sorted(shifts, key=lambda shift: shift.identity)
    )


def asked_for(
        events: Iterable[Event]
) -> Asked:
    """ Return what a revision asks for, before Amplify is consulted.

        The one place that decides which rows a revision means: which
        events cannot become shifts at all, which of the rest repeat
        each other, and which distinct shift each surviving role
        describes.  The preview reports it and the send creates it, and
        a second reading of the same events would let those two differ
        about a row nobody would notice was missing.

        Args:
            events (Iterable[Event]):
                Every event in the revision, in the order they are
                shown.

        Raises:
            ValueError:
                If an event's shift times are not times.

        Returns:
            asked (Asked):
                What the revision asks for.
    """

    by_opportunity: Dict[str, List[PlannedShift]] = {}
    found: List[Blocker] = []
    seen: Set[ShiftIdentity] = set()
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
            by_opportunity.setdefault(role.need_id, []).append(
                PlannedShift(
                    need_id=role.need_id,
                    date=event.date,
                    shift_start=event.shift_start,
                    shift_end=event.shift_end,
                    slots=role.slots
                )
            )

    return Asked(
        by_opportunity={
            need_id: tuple(shifts)
            for need_id, shifts in by_opportunity.items()
        },
        blockers=tuple(found),
        blocking_events=blocked,
        repeated_rows=repeats
    )


def split_by_existing(
        shifts: Iterable[PlannedShift],
        existing: AbstractSet[ShiftIdentity]
) -> Tuple[Tuple[PlannedShift, ...], Tuple[PlannedShift, ...]]:
    """ Return which shifts would arrive and which are already there.

        The one place that decides it, for the same reason 'asked_for'
        is the one place that decides what is asked for.  The preview
        reports the second group as skipped and the send declines to
        create it, and a send that split them differently would create
        a row a person was told would not arrive.

        Args:
            shifts (Iterable[PlannedShift]):
                The shifts to split, as 'asked_for' groups them.

            existing (AbstractSet[ShiftIdentity]):
                The shifts Amplify already holds, as
                '_opportunities.shifts_in_amplify' reads them.  Empty
                is a real answer -- the opportunities hold nothing yet
                -- and is never a stand-in for not having asked.

        Returns:
            split (Tuple[Tuple[PlannedShift, ...], ...]):
                The shifts that would be created, and the ones Amplify
                already has, in that order.
    """

    creating = []
    already = []

    for shift in shifts:
        if shift.identity in existing:
            already.append(shift)
        else:
            creating.append(shift)

    return tuple(creating), tuple(already)


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
                '_opportunities.shifts_in_amplify' reads them.

        Raises:
            ValueError:
                If an event's shift times are not times.

        Returns:
            preview (Preview):
                What a send would do.
    """

    asked = asked_for(events=events)
    split = {
        need_id: split_by_existing(shifts=shifts, existing=existing)
        for need_id, shifts in sorted(asked.by_opportunity.items())
    }
    skipping = [
        shift
        for _creating, already in split.values()
        for shift in already
    ]

    return Preview(
        will_create=sum(
            len(creating) for creating, _already in split.values()
        ),
        already_in_amplify=len(skipping),
        repeated_rows=asked.repeated_rows,
        blocking_events=asked.blocking_events,
        rows=_ordered(
            _row(
                need_id=need_id,
                opportunity=opportunities.get(need_id),
                creating=creating,
                already=already
            )
            for need_id, (creating, already) in split.items()
        ),
        skipped=_skipped(shifts=skipping),
        blockers=asked.blockers
    )
