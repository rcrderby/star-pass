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

# The row Amplify receives, and so the unit of duplicate safety and of
# idempotency (D16): need ID, date, start and end.  Never a count -- a
# count cannot say *which* shifts a send would repeat.
#
# Here rather than with the function that builds one, because the
# record of what was sent stores exactly these four columns and
# '_derived' works them out from an event.  Written in either place it
# would be a second answer to "is this the same shift", which is the
# one question D16 says must have only one.
ShiftIdentity = Tuple[str, str, str, str]

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
# Named as a set for the reason the other enumerations are: a client
# words each of these for a reader, and a kind nobody worded should be
# a failing test rather than an identifier on a screen.
MATCH_KINDS = (
    MATCH_KIND_KEYWORD,
    MATCH_KIND_FUZZY
)


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

            uncollected_count (int):
                How many things the run's window held that did not
                become events.  Derived by counting the rows the
                collection stored, so the figure beside the run and
                the list behind it are one answer.

            active_job_id (str, optional):
                Identifier of the job still working on the run, or
                None when nothing is.  Derived, and what makes a run
                somebody walked away from reattachable: the run is
                enough to find what is running on it.

            interrupted_job_id (str, optional):
                Identifier of the job the run's last one was, when it
                was left interrupted, and None otherwise.  Derived,
                and the other half of the same idea: resuming one is a
                deliberate act (D10), and a caller cannot ask for what
                it has no way to name.  Only the run's *last* job is
                reported, because a send a later one has since
                finished is not something to offer to resume.
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
    uncollected_count: int
    active_job_id: Optional[str]
    interrupted_job_id: Optional[str]


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

            kind (str):
                How the revision came to exist, one of
                'REVISION_KINDS'.

            source_revision (int, optional):
                The revision it was made from, where that is a fact
                about it rather than something a reader can work out.
                None for the two a collection fills, which are made
                from a calendar and not from a revision.

            change_count (int):
                How many changes were made while this revision was the
                current one.  Derived from the change log, and the
                figure that tells a reader which revision in a list is
                worth looking at: a revision nothing was done in is
                one somebody sealed and left.
    """

    run_id: str
    number: int
    created_at: str
    kind: str
    source_revision: Optional[int]
    change_count: int


@dataclass(frozen=True)
class Opportunity:
    """ An Amplify opportunity a run creates shifts under.

        Resolved while the run is collected and stored with it, not
        looked up when a preview is asked for: every review row is
        labelled with an opportunity title, so a lookup deferred to
        preview time would leave the main screen unable to name
        anything.

        **What Amplify says about the listing, and nothing else.**  How
        a shift is timed under it belongs to the role that creates the
        shift, because one listing can be named by categories that time
        it differently (D25).

        Attributes:
            need_id (str):
                Amplify need ID.

            title (str):
                Amplify opportunity title, as displayed.

            url (str):
                Public address of the opportunity.
    """

    need_id: str
    title: str
    url: str


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
    """ One opportunity an event creates shifts for, and how it does.

        An event produces a shift per role: a scrimmage wanting both
        skating and non-skating officials carries two.

        **The timing is the role's, not the opportunity's.**  What a
        shift asks of its event is decided by the category the event
        matched, and one Amplify listing can be named by categories
        that time it differently -- need 905196 is named by three, on
        three sets of offsets.  Recorded per role, so a run can hold
        two events sending to one listing on different timings (D25).

        Attributes:
            need_id (str):
                Amplify need ID the shift is created under.

            slots (int):
                Volunteers wanted.

            edited (bool):
                Whether a person changed 'slots' from
                'default_slots'.  Kept so a revision can show what was
                touched, which a comparison against the default could
                not: an event collected again can arrive with another.

            offset_start (int):
                Minutes added to the event's start to reach the
                shift's.

            offset_end (int):
                Minutes added to the event's end to reach the shift's.

            max_length (int, optional):
                Longest shift the opportunity accepts, in minutes, or
                None when it sets no maximum.

            default_slots (int):
                Volunteers the category asked for, before any edit.
                Stored beside 'slots' rather than looked up, for the
                reason 'edited' is stored: what to go back to is what
                this event was collected with.
    """

    need_id: str
    slots: int
    edited: bool = False
    offset_start: int = 0
    offset_end: int = 0
    max_length: Optional[int] = None
    default_slots: int = 0


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


# Why something in a run's window did not become one of its events.
# Three of them are what the calendar filter drops: a title the
# deployment never collects, an all-day event with no times to build a
# shift from, and an event with no title to match.  The fourth is the
# one the filter never sees -- an event the configured query strings
# did not return -- and it is the only one a person may pull in, since
# the other three describe events that cannot become a correct shift
# rather than events nobody looked for.
# How a revision came to exist.  Stored rather than worked out: the
# first is always revision 1 and the third always continues from the
# revision below it, but nothing else separates a revision a
# recollection replaced from one a seal opened, and only the revert
# knows which revision it went back to.
#
# An identifier rather than the sentence it used to be.  The sentence
# was written by the core, stored in the row, and printed unchanged by
# both clients -- so neither could word it, and changing the wording
# would have left every revision already recorded saying the old
# thing beside a new one saying the new.
REVISION_COLLECTED = 'collected'
REVISION_RECOLLECTED = 'recollected'
REVISION_CONTINUED = 'continued'
REVISION_REVERTED = 'reverted'
REVISION_KINDS = (
    REVISION_COLLECTED,
    REVISION_RECOLLECTED,
    REVISION_CONTINUED,
    REVISION_REVERTED
)

UNCOLLECTED_SEARCH = 'search'
UNCOLLECTED_EXCLUDED = 'excluded'
UNCOLLECTED_ALL_DAY = 'allday'
UNCOLLECTED_UNTITLED = 'untitled'
UNCOLLECTED_REASONS = (
    UNCOLLECTED_SEARCH,
    UNCOLLECTED_EXCLUDED,
    UNCOLLECTED_ALL_DAY,
    UNCOLLECTED_UNTITLED
)


@dataclass(frozen=True)
class UnmatchedTitle:
    """ A title the data model did not match, and how often it has been.

        What is stored is a **sighting**, and a run contributes at
        most one of them per title: a window holding the same
        unmatched title four times saw one title, and collecting that
        window again is one window read twice rather than a title that
        came back.  So the count is the number of **runs** a title
        turned up in, which is the question being asked of it.  What
        is read back is one entry per title in a calendar, with the
        sightings counted, because a list showing the same title
        eleven times is a list nobody works through.

        Attributes:
            calendar (str):
                Which configured calendar the title was seen in.  Part
                of the identity rather than a note beside it: the
                categories a title is matched against belong to a
                calendar, so the same title can be matched in one and
                unmatched in another.

            title (str):
                The title, as the calendar gave it.

            times_seen (int):
                How many sightings have been recorded: one per run the
                title turned up in, plus any recorded by hand.

            first_seen (str):
                When the earliest was recorded, ISO-8601 UTC.

            last_seen (str):
                When the most recent was, ISO-8601 UTC.
    """

    calendar: str
    title: str
    times_seen: int
    first_seen: str
    last_seen: str


@dataclass(frozen=True)
class UncollectedEvent:
    """ Something in a run's window that did not become an event.

        Stored while the run is collected rather than worked out when
        somebody asks: the count is shown on every load of the review
        screen, and reading the calendar again to produce it would
        make looking at a run cost a Google request and give the run
        a second source of truth about its own window.

        Every field but the identifier and the reason may be absent,
        because the reasons describe exactly the events that are
        missing something: an untitled event has no title and an
        all-day event has no times.

        Attributes:
            id (str):
                Calendar identifier of the event.  The same identifier
                an event of the run carries, so a row that was later
                pulled in can be recognised.

            reason (str):
                One of 'UNCOLLECTED_REASONS'.

            title (str, optional):
                Event title, or None when it has none.

            date (str, optional):
                Day of the event as an ISO date, in the league's own
                time zone, or None when the calendar gave a value that
                could not be read as one.

            calendar_start (str, optional):
                Start time on the calendar, or None for an all-day
                event, which has none.

            calendar_end (str, optional):
                End time on the calendar, or None for an all-day
                event.
    """

    id: str
    reason: str
    title: Optional[str] = None
    date: Optional[str] = None
    calendar_start: Optional[str] = None
    calendar_end: Optional[str] = None


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

# What an idempotency key may be used on.  Every job is one of these,
# because a job is asked for once and must not be started twice; but
# an edit is answered in the request that asked for it and starts no
# job, so the two vocabularies are not the same one.  A key is per
# operation, so the same value used on an edit and a send is two
# reservations rather than one replaying the other's answer.
OPERATION_EDIT = 'edit'
OPERATION_REVERT = 'revert'
OPERATION_SEAL = 'seal'
IDEMPOTENT_OPERATIONS = JOB_KINDS + (
    OPERATION_EDIT,
    OPERATION_REVERT,
    OPERATION_SEAL
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

# Statuses that mean shifts of this run are in Amplify.  Amplify has
# no way to take a shift back, so anything that would replace the
# events describing what was sent is refused for a run in one of
# these.
RUN_STATUSES_SENT = (
    RUN_STATUS_PARTLY_SENT,
    RUN_STATUS_SENT
)

# Statuses a restart ends.  Whatever was running them is gone: the
# process that held the work no longer exists, and a queued job was
# waiting on the same process.
JOB_STATUSES_UNFINISHED = (
    JOB_STATUS_QUEUED,
    JOB_STATUS_RUNNING
)


# Who is holding a job, and so who may end it when it is found
# unfinished.  The service and the command line write into one
# database (D2), and a sweep of what a stopped process left behind has
# to leave alone what it never held: a command line run that swept
# everything unfinished would mark a live send interrupted.
#
# The role rather than the process.  One service serves a deployment
# (D5), so a job held by 'service' and still unfinished at startup
# belongs to the process that just stopped; a command line process is
# short-lived and waits for its own job, so one still unfinished is
# one whose process is gone.
JOB_HOLDER_SERVICE = 'service'
JOB_HOLDER_LOCAL = 'local-cli'
JOB_HOLDERS = (
    JOB_HOLDER_SERVICE,
    JOB_HOLDER_LOCAL
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

            held_by (str):
                Which of 'JOB_HOLDERS' is running it.  Separate from
                'principal_id', which says who asked: a person may ask
                a service to do something the service then holds, and
                only the holder may end the job when it is found
                unfinished.

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
    held_by: str
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


@dataclass(frozen=True)
class SentShift:
    """ One row a send put into Amplify, and who put it there.

        The record duplicate safety rests on, so it is never purged
        (D12) and its first four fields are exactly a 'ShiftIdentity':
        a send that is retried asks what it already created, and an
        answer assembled from anything else would be a second opinion.

        It is not the whole answer to "does Amplify already have this".
        Amplify is the authority, and a shift created by an earlier run
        or by hand appears in no run's sent record; that is why the
        send path reads the live opportunity as well.  This says what
        *this* run did, which is what a retry needs and what a live
        read cannot tell it.

        Attributes:
            run_id (str):
                Run whose send created the shift.

            need_id (str):
                Amplify need ID the shift was created under.

            date (str):
                Day of the shift, as an ISO date.

            shift_start (str):
                Start time of the shift, in the league's own time zone.

            shift_end (str):
                End time of the shift, in the league's own time zone.

            sent_at (str):
                When it was created, as an ISO-8601 UTC timestamp
                (D13).

            principal_id (str):
                Who sent it (D13).

            idempotency_key (str):
                The key the send was made under (D13).  Kept per shift
                rather than only per request, so that the rows one
                attempt created can be told from the rows another did.
    """

    run_id: str
    need_id: str
    date: str
    shift_start: str
    shift_end: str
    sent_at: str
    principal_id: str
    idempotency_key: str


@dataclass(frozen=True)
class IdempotencyRecord:
    """ A write that was asked for once, and what it answered.

        Reserved before the write and completed after it, so the record
        exists while the work is still running.  That gap is the point:
        a second request arriving with the same key finds a reservation
        with no response yet and knows the first one is still in hand,
        which is a different answer from "here is what it returned"
        and a different one again from "nothing has asked for this".

        Attributes:
            operation (str):
                Which write the key was used for, one of
                'IDEMPOTENT_OPERATIONS'.  Part of the key, so the same
                value used on two operations is two reservations
                rather than one operation replaying the other's
                answer.

            key (str):
                What the caller supplied, unread and uninterpreted.

            run_id (str):
                Run the write acts on.

            fingerprint (str):
                What the request asked for, as the caller summarized
                it.  Compared on a replay: the key is a promise that
                the request is the same one, and a replay that asks
                for something else has broken the promise rather than
                earned the first answer.

            principal_id (str):
                Who asked (D13).

            created_at (str):
                When they asked, as an ISO-8601 UTC timestamp (D13).

            status_code (int, optional):
                The status the write answered with, or None while it
                is still running.

            response (Dict[str, Any], optional):
                The body it answered with, or None while it is still
                running.  Stored so that a replay is answered from
                here instead of writing again.
    """

    operation: str
    key: str
    run_id: str
    fingerprint: str
    principal_id: str
    created_at: str
    status_code: Optional[int] = None
    response: Optional[Dict[str, Any]] = None
