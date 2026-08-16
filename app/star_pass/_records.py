#!/usr/bin/env python3
""" The records the repository layer stores and returns.

    One frozen dataclass per thing the database holds.  They are the
    vocabulary the layer speaks: a caller passes one in and gets one
    back, and never sees a row, a column name or a dictionary key that
    a typo would turn into a silent None.

    Frozen because a record is a reading of stored state, not a handle
    on it.  Changing a field would look like changing the database and
    would not, so the way to change stored state is to call the
    repository with the values that replace it.

    Several fields here are derived rather than stored -- a run's
    current revision and the time it was last revised -- and are
    documented as such on the field.  Their queries live in
    '_repository'; the distinction matters to nobody above this layer.
"""
# A record holds one field per stored column, which is more attributes
# than a class carrying behavior should have.  The limit is aimed at
# classes that do something; every class here only holds values.
# pylint: disable=too-many-instance-attributes

# Imports - Python Standard Library
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

# Statuses a run moves through, in the order it moves through them.
# 'collecting' is set when the run is created, before any event exists;
# 'partly_sent' is reachable because a send that fails part way through
# leaves shifts in Amplify that cannot be taken back.
RUN_STATUS_COLLECTING = 'collecting'
RUN_STATUS_UNSENT = 'unsent'
RUN_STATUS_PARTLY_SENT = 'partly_sent'
RUN_STATUS_SENT = 'sent'
RUN_STATUSES = (
    RUN_STATUS_COLLECTING,
    RUN_STATUS_UNSENT,
    RUN_STATUS_PARTLY_SENT,
    RUN_STATUS_SENT
)

# Kinds of title match, from 'Helpers.search_shift_info': an alias
# whose words all appear in the title, or the fuzzy fallback.
MATCH_KIND_KEYWORD = 'keyword'
MATCH_KIND_FUZZY = 'fuzzy'


@dataclass(frozen=True)
class Run:
    """ One collection of calendar events, and what became of it.

        Attributes:
            id (str):
                Server-minted identifier.  A run is addressed by this
                and never by the path of a file it produced.

            calendar (str):
                Which configured calendar was collected.

            window_start (str):
                First day the run covers, as an ISO date in the
                league's own time zone.

            window_end (str):
                Day after the last day the run covers, as an ISO date.
                Exclusive, so a one-day window is two consecutive
                dates.

            status (str):
                One of 'RUN_STATUSES'.

            collected_at (str):
                When the run was created, as an ISO-8601 UTC timestamp.

            sent_at (str, optional):
                When shifts were sent to Amplify, or None when they
                have not been.

            current_revision (int):
                Number of the revision now being edited, or 0 before
                the first one is created.  Derived: the highest
                revision number a run has is the current one.

            revised_at (str):
                When the run last changed, as an ISO-8601 UTC
                timestamp.  Derived from the newest change log entry,
                falling back to 'collected_at' for a run nothing has
                changed yet.

            event_count (int):
                How many events the current revision holds.  Derived.

            shift_count (int):
                How many shifts sending the current revision would
                create.  Derived: an event creates one shift per role,
                so this counts roles and not events.

            unmatched_count (int):
                How many events in the current revision would create
                no shift at all.  Derived, and the figure that says a
                run needs attention: an event whose title matched
                nothing has no category and so no role, and an event
                whose category resolved to no need ID has none either.
                Either way the event cannot become a shift, and a run
                holding one cannot be sent.

            active_job_id (str, optional):
                Identifier of the job still working on the run, or
                None when nothing is.  Derived, and what makes a run
                somebody walked away from reattachable: the run is
                enough to find what is running on it.
    """

    id: str
    calendar: str
    window_start: str
    window_end: str
    status: str
    collected_at: str
    sent_at: Optional[str]
    current_revision: int
    revised_at: str
    event_count: int
    shift_count: int
    unmatched_count: int
    active_job_id: Optional[str]


@dataclass(frozen=True)
class Revision:
    """ A numbered version of a run's events.

        Every revision below the current one is history and is never
        written to again.  Reverting adds a revision holding a copy of
        an earlier one rather than deleting anything, so the record of
        what was done stays complete.

        Attributes:
            run_id (str):
                Run the revision belongs to.

            number (int):
                Position in the run's history, from one.

            created_at (str):
                When the revision was created, as an ISO-8601 UTC
                timestamp.

            label (str):
                How the revision is named to a reader.
    """

    run_id: str
    number: int
    created_at: str
    label: str


@dataclass(frozen=True)
class Opportunity:
    """ An Amplify opportunity a run creates shifts under.

        Resolved while the run is collected and stored with it, not
        looked up when a preview is asked for: every review row is
        labelled with an opportunity title, so a lookup deferred to
        preview time would leave the main screen unable to name
        anything.

        Attributes:
            need_id (str):
                Amplify need ID.

            title (str):
                Amplify opportunity title, as displayed.

            url (str):
                Public address of the opportunity.

            max_length (int, optional):
                Longest shift the opportunity accepts, in minutes, or
                None when it sets no maximum.

            offset_start (int):
                Minutes added to an event's start to reach the shift's.

            offset_end (int):
                Minutes added to an event's end to reach the shift's.

            default_slots (int):
                Volunteers wanted per shift, before any edit.
    """

    need_id: str
    title: str
    url: str
    max_length: Optional[int]
    offset_start: int
    offset_end: int
    default_slots: int


@dataclass(frozen=True)
class Match:
    """ How an event's title was matched to a category.

        Stored rather than derived: the data model can change between
        the day a run is collected and the day it is reviewed, and a
        match recomputed later would describe the model as it is now
        instead of what the run actually did.

        Attributes:
            kind (str):
                'MATCH_KIND_KEYWORD' or 'MATCH_KIND_FUZZY'.

            keyword (str, optional):
                Alias that matched, or None for a fuzzy match.

            score (int, optional):
                Fuzzy confidence from 0 to 100, or None for a keyword
                match, which is not scored.
    """

    kind: str
    keyword: Optional[str] = None
    score: Optional[int] = None


@dataclass(frozen=True)
class EventRole:
    """ One opportunity an event creates shifts for, and how many.

        An event produces a shift per role: a scrimmage wanting both
        skating and non-skating officials carries two.

        Attributes:
            need_id (str):
                Amplify need ID the shift is created under.

            slots (int):
                Volunteers wanted.

            edited (bool):
                Whether a person changed 'slots' from the
                opportunity's default.  Kept so a revision can show
                what was touched, which a comparison against the
                current default could not: the default can change.
    """

    need_id: str
    slots: int
    edited: bool = False


@dataclass(frozen=True)
class Event:
    """ One calendar event as a revision holds it.

        Times are 24-hour 'HH:MM' strings in the league's own time
        zone, and the date is a separate ISO date, because that is how
        an event is read, edited and displayed.  The calendar times are
        what the calendar said; the shift times are those plus the
        opportunity's offsets, and are what reaches Amplify.

        What is not here is derived: how long the shift is, whether an
        opportunity's maximum shortened it, whether another event in
        the revision would create the same shift, and whether the event
        blocks the run for want of a match.

        Attributes:
            id (str):
                Identifier, unique within the revision.

            title (str):
                Event title, as the calendar gave it.

            date (str):
                Day of the event, as an ISO date.

            calendar_start (str):
                Start time on the calendar.

            calendar_end (str):
                End time on the calendar.

            shift_start (str):
                Start time of the shift to create.

            shift_end (str):
                End time of the shift to create.

            category (str, optional):
                Data model category the title matched, or None when
                nothing matched, which blocks the run.

            match (Match, optional):
                How the category was reached, or None when the event
                was added by hand or matched nothing.

            added_by_hand (bool):
                Whether a person pulled the event in rather than the
                search finding it.  Reverting to the first revision
                drops these, so they have to be distinguishable.

            roles (Tuple[EventRole, ...]):
                The opportunities this event creates shifts for.
    """

    id: str
    title: str
    date: str
    calendar_start: str
    calendar_end: str
    shift_start: str
    shift_end: str
    category: Optional[str] = None
    match: Optional[Match] = None
    added_by_hand: bool = False
    roles: Tuple[EventRole, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class LogEntry:
    """ One line of a run's change log.

        Written when the change is made rather than assembled by a
        client, so the log survives a reload and reads the same in a
        browser and a terminal.

        Attributes:
            id (int):
                Identifier, ascending in the order entries were
                written.

            run_id (str):
                Run the entry belongs to.

            revision (int):
                Revision that was current when the change was made.

            logged_at (str):
                When the change was made, as an ISO-8601 UTC timestamp.

            principal_id (str):
                Who made it.  Recorded from the first entry, while
                there is still only one principal, so that the column
                is already there and already populated when there is
                more than one.

            entry (str):
                What changed, written for a reader.
    """

    id: int
    run_id: str
    revision: int
    logged_at: str
    principal_id: str
    entry: str


# What a job is doing.  One per operation that takes long enough that a
# caller is given an identifier and told to watch it, rather than being
# made to wait for it.
JOB_KIND_COLLECT = 'collect'
JOB_KIND_RECOLLECT = 'recollect'
JOB_KIND_SEND = 'send'
JOB_KINDS = (
    JOB_KIND_COLLECT,
    JOB_KIND_RECOLLECT,
    JOB_KIND_SEND
)

# Where a job is in its life.  'interrupted' is the one that needs
# explaining: it means the service stopped while the job was in hand,
# so nobody knows how far it got.  It is separate from 'failed' because
# a failure was observed and an interruption was not, and separate from
# 'running' because nothing is running it now.  Resuming one is a human
# action, never automatic, since a send that resumed itself would write
# to a live volunteer system from state rebuilt after a crash.
JOB_STATUS_QUEUED = 'queued'
JOB_STATUS_RUNNING = 'running'
JOB_STATUS_SUCCEEDED = 'succeeded'
JOB_STATUS_FAILED = 'failed'
JOB_STATUS_INTERRUPTED = 'interrupted'
JOB_STATUSES = (
    JOB_STATUS_QUEUED,
    JOB_STATUS_RUNNING,
    JOB_STATUS_SUCCEEDED,
    JOB_STATUS_FAILED,
    JOB_STATUS_INTERRUPTED
)

# Statuses a job does not leave on its own.  A job in one of these is
# over: 'succeeded' and 'failed' for good, 'interrupted' until somebody
# asks for it to be resumed.
JOB_STATUSES_FINISHED = (
    JOB_STATUS_SUCCEEDED,
    JOB_STATUS_FAILED,
    JOB_STATUS_INTERRUPTED
)

# Statuses a restart ends.  Whatever was running them is gone: the
# process that held the work no longer exists, and a queued job was
# waiting on the same process.
JOB_STATUSES_UNFINISHED = (
    JOB_STATUS_QUEUED,
    JOB_STATUS_RUNNING
)


@dataclass(frozen=True)
class Job:
    """ One long operation, and where it got to.

        Attributes:
            id (str):
                Server-minted identifier.  What a caller is given in
                place of waiting, and what they come back with.

            run_id (str):
                Run the job is working on.

            kind (str):
                One of 'JOB_KINDS'.

            status (str):
                One of 'JOB_STATUSES'.

            principal_id (str):
                Who asked for it (D13).

            created_at (str):
                When it was asked for, as an ISO-8601 UTC timestamp.

            started_at (str, optional):
                When it began, or None while it is still queued.

            finished_at (str, optional):
                When it stopped, or None while it has not.

            detail (str, optional):
                Why it failed, as a summary safe to show a caller, or
                None when it did not.
    """

    id: str
    run_id: str
    kind: str
    status: str
    principal_id: str
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    detail: Optional[str] = None


@dataclass(frozen=True)
class JobEvent:
    """ Something a job reported while it ran.

        Recorded rather than only streamed, so that a client which
        connects late or reconnects can be given what it missed: the
        identifier ascends, so "everything after the last one I saw" is
        a query rather than a guess.

        Attributes:
            id (int):
                Identifier, ascending in the order events were
                recorded.

            job_id (str):
                Job that reported it.

            recorded_at (str):
                When it was reported, as an ISO-8601 UTC timestamp.

            kind (str):
                What happened, named by the reporting method that said
                so.

            payload (Dict[str, Any]):
                What the event carried, which differs by kind.
    """

    id: int
    job_id: str
    recorded_at: str
    kind: str
    payload: Dict[str, Any]
