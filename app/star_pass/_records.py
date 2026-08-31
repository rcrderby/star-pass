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
# Every class here holds values and no behavior, so the attribute
# limit does not apply.
# pylint: disable=too-many-instance-attributes

# Imports - Python Standard Library
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

# The row Amplify receives, and so the unit of duplicate safety and
# of idempotency: need ID, date, start and end.  Never a count, which
# cannot say *which* shifts a send would repeat.
#
# Here rather than beside either caller: the sent record stores these
# four columns and '_derived' works them out from an event, and "is
# this the same shift" has one answer.
ShiftIdentity = Tuple[str, str, str, str]

# Statuses a run holds.  The first four are the order it moves
# through them.  'collecting' is set when the run is created, before
# any event exists; 'partly_sent' is reachable because a send that
# fails part way leaves shifts in Amplify that cannot be taken back.
#
# 'failed' is off that path: it is where a run whose **first**
# collection raised comes to rest.  Collecting the window again
# recovers it, and it may not be sent, because it holds no revision.
# A recollection that fails goes back to 'unsent', because what it
# was working over is still there.
RUN_STATUS_COLLECTING = 'collecting'
RUN_STATUS_UNSENT = 'unsent'
RUN_STATUS_PARTLY_SENT = 'partly_sent'
RUN_STATUS_SENT = 'sent'
RUN_STATUS_FAILED = 'failed'
RUN_STATUSES = (
    RUN_STATUS_COLLECTING,
    RUN_STATUS_UNSENT,
    RUN_STATUS_PARTLY_SENT,
    RUN_STATUS_SENT,
    RUN_STATUS_FAILED
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
                deliberate act, and a caller cannot ask for what
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

        Resolved while the run is collected and stored with it, so
        every review row can be labelled with its opportunity title.

        Holds what Amplify says about the listing and nothing else.
        How a shift is timed under it belongs to the role that creates
        the shift.

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

        The timing is the role's, not the opportunity's.  One Amplify
        listing can be named by categories that time it differently,
        so a run can hold two events sending to one listing on
        different timings.

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

        Times are 24-hour 'HH:MM' strings in the league's time zone
        and the date is a separate ISO date.  The calendar times are
        what the calendar said; the shift times are those plus the
        opportunity's offsets, and are what reaches Amplify.

        Shift length, whether a maximum shortened it, whether another
        event would create the same shift, and whether the event
        blocks the run are all derived elsewhere.

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
                Data model category the event is under, or None when
                nothing matched, which blocks the run.

            collected_category (str, optional):
                The category the collection matched, which is what an
                undo puts the event back under and what says whether
                its category has been changed.  None where the
                collection matched nothing, and an undo then puts the
                event back to unassigned, which is where it began.
                That row is also the only one that may be unassigned
                by hand.

            match (Match, optional):
                How the category was reached, or None when the event
                was added by hand or matched nothing.

            added_by_hand (bool):
                Whether a person pulled the event in rather than the
                search finding it.  Reverting to the first revision
                drops these, so they have to be distinguishable.

            calendar_note (str, optional):
                What the calendar's description said, as text, or None
                where the calendar carries no notes or this event had
                none.  Truth about the calendar rather than
                about the run, so an edit never moves it and it is no
                part of what an undo compares.

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
    collected_category: Optional[str] = None
    match: Optional[Match] = None
    added_by_hand: bool = False
    calendar_note: Optional[str] = None
    roles: Tuple[EventRole, ...] = field(default_factory=tuple)


# Why something in a run's window did not become one of its events.
# Three are what the calendar filter drops: an excluded title, an
# all-day event with no times, and an event with no title.  The
# fourth is one the query strings did not return, and it is the only
# one a person may pull in.
# How a revision came to exist.  Stored rather than worked out:
# nothing separates a revision a recollection replaced from one a
# seal opened, and only the revert knows which revision it went back
# to.  An identifier, so each client words it.
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
        most one per title, so the count is the number of runs a title
        turned up in.  What is read back is one entry per title in a
        calendar, with the sightings counted.

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

        Stored while the run is collected, so the review screen shows
        the count without a second calendar read.

        Every field but the identifier and the reason may be absent:
        an untitled event has no title and an all-day event has no
        times.

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

            calendar_note (str, optional):
                What the calendar's description said, as text, kept so
                that an event pulled in by hand carries the note a
                collected one carries: adding reads this row and never
                the calendar.
    """

    id: str
    reason: str
    title: Optional[str] = None
    date: Optional[str] = None
    calendar_start: Optional[str] = None
    calendar_end: Optional[str] = None
    calendar_note: Optional[str] = None


@dataclass(frozen=True)
class LogEntry:
    """ One line of a run's change log.

        Written when the change is made, so the log survives a reload
        and reads the same in a browser and a terminal.

        An operation builds one from its action and values alone.
        Which run, which revision, who and when are stamped on by the
        repository as it stores the entry.

        Attributes:
            action (str):
                What was done, one of 'LOG_ACTIONS'.  An identifier
                rather than the sentence it would make: a sentence
                returned by a service is a wording mistake, and a
                sentence written into a row is a wording mistake with
                a migration attached.  Each client words it.

            subject (str, optional):
                Title of the event it was done to, or None when it
                named more than one.  One event is worth naming and a
                selection is worth counting, so a client reads this
                beside the count.

            subject_count (int):
                How many events it named.

            category (str, optional):
                The category a 'set_category' put them under, as the
                data model names it.  The key rather than the label,
                because what a category is called belongs to whoever
                is showing it.

            shift_time (str, optional):
                The time a 'set_start' or 'set_end' set, as 'HH:MM'.

            minutes (int, optional):
                How far a 'nudge' moved them, negative for earlier.
                Signed rather than split into a size and a direction,
                which is a wording each client makes for itself.

            slots (int, optional):
                How many volunteers a 'set_slots' asked for.

            need_id (str, optional):
                The opportunity a 'set_slots' was about.  The
                identifier rather than the Amplify title, which a
                reader of a run already holds beside it.

            id (int):
                Identifier, ascending in the order entries were
                written.  The repository's to set.

            run_id (str):
                Run the entry belongs to.  The repository's to set.

            revision (int):
                Revision that was current when the change was made.
                The repository's to set.

            logged_at (str):
                When the change was made, as an ISO-8601 UTC
                timestamp.  The repository's to set.

            principal_id (str):
                Who made it.  The repository's to set.  Recorded from
                the first entry, while there is still only one
                principal, so that the column is already there and
                already populated when there is more than one.
    """

    action: str
    subject: Optional[str] = None
    subject_count: int = 1
    category: Optional[str] = None
    shift_time: Optional[str] = None
    minutes: Optional[int] = None
    slots: Optional[int] = None
    need_id: Optional[str] = None
    id: int = 0
    run_id: str = ''
    revision: int = 0
    logged_at: str = ''
    principal_id: str = ''


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

# What an idempotency key may be used on.  Every job is one, because
# a job must not be started twice; an edit is answered in its own
# request and starts no job.  A key is per operation, so the same
# value used on an edit and a send is two reservations.
OPERATION_EDIT = 'edit'
OPERATION_REVERT = 'revert'
OPERATION_SEAL = 'seal'
IDEMPOTENT_OPERATIONS = JOB_KINDS + (
    OPERATION_EDIT,
    OPERATION_REVERT,
    OPERATION_SEAL
)

# What a reviewer may ask to be done to the events in a revision.
# Read by the operation a request carries, the table in '_editing'
# that answers it, and each client's change-log wordings.  A whole
# call of these is one 'edit' to 'IDEMPOTENT_OPERATIONS' above.
OP_SET_CATEGORY = 'set_category'
OP_UNASSIGN = 'unassign'
OP_SET_START = 'set_start'
OP_SET_END = 'set_end'
OP_SET_SLOTS = 'set_slots'
OP_NUDGE = 'nudge'
OP_RESET_SLOTS = 'reset_slots'
OP_REMOVE = 'remove'
OP_UNDO = 'undo'

EDIT_OPERATIONS = (
    OP_SET_CATEGORY,
    OP_UNASSIGN,
    OP_SET_START,
    OP_SET_END,
    OP_SET_SLOTS,
    OP_NUDGE,
    OP_RESET_SLOTS,
    OP_REMOVE,
    OP_UNDO
)

# What a change-log entry can record: every edit, plus pulling in an
# event the collection left out, which changes what the revision
# holds without being an operation over the events in it.
LOG_ADDED = 'added'
LOG_ACTIONS = EDIT_OPERATIONS + (LOG_ADDED,)

# Where a job is in its life.  'interrupted' means the service
# stopped while the job was in hand, so nobody knows how far it got:
# separate from 'failed', which was observed, and from 'running',
# which nothing is doing now.  Resuming one is always a human
# action.
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

# Statuses that mean shifts of this run are in Amplify.  Anything
# that would replace the events describing what was sent is refused
# for a run in one of these.
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
# database, and a sweep must leave alone what it never held.
#
# The role rather than the process.  One service serves a deployment,
# so a job held by 'service' and unfinished at startup belongs to the
# process that just stopped; a command line process waits for its own
# job, so one still unfinished is one whose process is gone.
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
                Who asked for it.

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

        Recorded rather than only streamed, so a client that connects
        late can be given what it missed.  The identifier ascends, so
        "everything after the last one I saw" is a query.

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

        The record duplicate safety rests on, so it is never purged,
        and its first four fields are exactly a 'ShiftIdentity'.

        It is not the whole answer to "does Amplify already have
        this": a shift created by an earlier run or by hand appears in
        no run's sent record, which is why the send path reads the
        live opportunity as well.  This says what *this* run did.

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
                When it was created, as an ISO-8601 UTC timestamp.

            principal_id (str):
                Who sent it.

            idempotency_key (str):
                The key the send was made under.  Kept per shift
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

        Reserved before the write and completed after it, so a second
        request with the same key can tell "the first one is still
        running" from "here is what it returned" and from "nothing has
        asked for this".

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
                Who asked.

            created_at (str):
                When they asked, as an ISO-8601 UTC timestamp.

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
