#!/usr/bin/env python3
""" The shapes the service answers with.

    What a caller sends is in '_requests', which reads this module
    for the base they share and is read by nothing here: a request is
    checked on the way in and a view is built on the way out.

    Separate from the core's records: those describe what is stored,
    these describe what crosses the wire, and the two are allowed to
    differ.  A stored record can gain a column the contract does not
    publish, and the contract can rename a field without rewriting the
    database.

    Field names are camel case on the wire and snake case in Python.
    The contract is read by a browser and by generated clients, where
    camel case is the convention; the alias generator does the
    translation once here rather than at each field.
"""

# Imports - Python Standard Library
from typing import List, Optional

# Imports - Third-Party
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

# Imports - Local
from star_pass._preview import BLOCKER_REASONS
from star_pass._records import (
    JOB_KINDS,
    JOB_STATUSES,
    MATCH_KIND_FUZZY,
    MATCH_KIND_KEYWORD,
    RUN_STATUSES,
    UNCOLLECTED_REASONS
)


# The header a send is claimed under (D16).  Named here rather than in
# the service, because the command line client answering the same
# operation locally reads the key out of it and nothing about the
# spelling belongs to one half.
IDEMPOTENCY_KEY_HEADER = 'Idempotency-Key'


class ApiModel(BaseModel):
    """ The base every shape the service publishes is built on. """

    model_config = ConfigDict(
        alias_generator=to_camel,
        # A caller may send either spelling; the service only ever
        # sends the alias.
        populate_by_name=True
    )


class JobView(ApiModel):
    """ A long operation, as a caller sees it. """

    id: str = Field(
        description='Identifier the job is addressed by.'
    )
    run_id: str = Field(
        description='Run the job is working on.'
    )
    kind: str = Field(
        description=f'What it is doing: {", ".join(JOB_KINDS)}.'
    )
    status: str = Field(
        description=(
            f'Where it is: {", ".join(JOB_STATUSES)}. "interrupted" '
            'means the service stopped while it was in hand, so how '
            'far it got is unknown; resuming one is a deliberate '
            'action, never automatic.'
        )
    )
    created_at: str = Field(
        description='When it was asked for, as an ISO-8601 UTC time.'
    )
    started_at: str | None = Field(
        default=None,
        description='When it began, or null while it is queued.'
    )
    finished_at: str | None = Field(
        default=None,
        description='When it stopped, or null while it has not.'
    )
    detail: str | None = Field(
        default=None,
        description=(
            'Why it failed, when it did and when the reason is one a '
            'caller can act on. A failure the service did not expect '
            'says so without its reason, which is in the service log '
            'against the job.'
        )
    )


class WindowView(ApiModel):
    """ The days a run covers, and the zone they are read in. """

    start: str = Field(
        description='First day the run covers, as an ISO date.'
    )
    end: str = Field(
        description=(
            'Day after the last day the run covers, as an ISO date. '
            'Exclusive, so a run covering one day carries two '
            'consecutive dates. This is the authoritative value: it '
            'is what is stored, sent and compared, and "lastDay" is '
            'the same window said the way a reader means it.'
        )
    )
    last_day: str = Field(
        description=(
            'Last day the run covers, as an ISO date, and as a reader '
            'means it -- the day before "end". Published rather than '
            'worked out by each client, because every client that '
            'shows a window has to say it this way and a second '
            'implementation of one subtraction is a client that can '
            'disagree with the server about which days a run covers.'
        )
    )
    timezone: str = Field(
        description=(
            'Zone the two dates are read in, which is the zone the '
            'calendar is read in and the one the configuration '
            'reports. The server\'s zone is the authoritative one: a '
            'client displays these dates and never works a window out '
            'in the zone of whoever is looking at it.'
        )
    )


class RunCountsView(ApiModel):
    """ What the run's current revision holds. """

    events: int = Field(
        description='Events in the current revision.'
    )
    shifts: int = Field(
        description=(
            'Shifts a send would create. Counted per role rather than '
            'per event, because an event serving both skating and '
            'non-skating officials creates two.'
        )
    )
    unmatched: int = Field(
        description=(
            'Events that would create no shift at all, and so stop '
            'the run being sent. A title that matched nothing has no '
            'opportunity to create a shift under, and a category that '
            'resolved to no need ID leaves the same absence.'
        )
    )
    uncollected: int = Field(
        description=(
            'Things the run\'s window held that did not become '
            'events. Counted over the run rather than the current '
            'revision, because it describes the window the collection '
            'read and editing the events does not change it.'
        )
    )


class RunView(ApiModel):
    """ One collection of calendar events, as a caller sees it. """

    id: str = Field(
        description=(
            'Identifier the run is addressed by. Minted by the '
            'server, and never the path of a file the run produced.'
        )
    )
    calendar: str = Field(
        description='Which configured calendar was collected.'
    )
    window: WindowView = Field(
        description='The days the run covers.'
    )
    status: str = Field(
        description=f'Where the run is: {", ".join(RUN_STATUSES)}.'
    )
    collected_at: str = Field(
        description='When it was created, as an ISO-8601 UTC time.'
    )
    sent_at: str | None = Field(
        default=None,
        description=(
            'When its shifts reached Amplify, or null while they have '
            'not.'
        )
    )
    revised_at: str = Field(
        description=(
            'When it last changed, as an ISO-8601 UTC time. The time '
            'it was collected, for a run nothing has changed yet.'
        )
    )
    current_revision: int = Field(
        description=(
            'Number of the revision now being edited, or 0 before the '
            'first one exists.'
        )
    )
    counts: RunCountsView = Field(
        description='What the current revision holds.'
    )
    active_job_id: str | None = Field(
        default=None,
        description=(
            'Identifier of the job still working on this run, or null '
            'when nothing is. What makes a run somebody walked away '
            'from reattachable: read the job, or follow its events.'
        )
    )


class MatchView(ApiModel):
    """ How an event's title was matched to a category. """

    kind: str = Field(
        description=(
            f'How it matched: "{MATCH_KIND_KEYWORD}" for an alias '
            'whose words all appear in the title, or '
            f'"{MATCH_KIND_FUZZY}" for the fallback.'
        )
    )
    keyword: str | None = Field(
        default=None,
        description='The alias that matched, or null for a fuzzy match.'
    )
    score: int | None = Field(
        default=None,
        description=(
            'Fuzzy confidence from 0 to 100, or null for a keyword '
            'match, which is not scored.'
        )
    )


class EventRoleView(ApiModel):
    """ One opportunity an event creates a shift for. """

    need_id: str = Field(
        description='Amplify need ID the shift is created under.'
    )
    slots: int = Field(
        description='Volunteers wanted.'
    )
    edited: bool = Field(
        description=(
            'Whether a person changed the count from the '
            'opportunity\'s default. Recorded rather than compared '
            'against the default now, because the default can change.'
        )
    )


class EventView(ApiModel):
    """ One calendar event, as the current revision holds it. """

    id: str = Field(
        description='Identifier, unique within the revision.'
    )
    title: str = Field(
        description='Event title, as the calendar gave it.'
    )
    date: str = Field(
        description='Day of the event, as an ISO date.'
    )
    calendar_start: str = Field(
        description='Start time on the calendar, in the run\'s zone.'
    )
    calendar_end: str = Field(
        description='End time on the calendar, in the run\'s zone.'
    )
    shift_start: str = Field(
        description=(
            'Start time of the shift to create, which is the calendar '
            'time plus the opportunity\'s offset.'
        )
    )
    shift_end: str = Field(
        description='End time of the shift to create.'
    )
    length_minutes: int = Field(
        description=(
            'How long the shift lasts, which is the duration Amplify '
            'is given. Not above zero means the shift ends before it '
            'starts, which blocks the send.'
        )
    )
    capped_at: int | None = Field(
        default=None,
        description=(
            'The opportunity maximum that shortened this shift, or '
            'null when nothing did. Present so a reader is told which '
            'number decided the length rather than left wondering why '
            'the shift is shorter than the event.'
        )
    )
    category: str | None = Field(
        default=None,
        description=(
            'Data model category the title matched, or null when '
            'nothing matched.'
        )
    )
    match: MatchView | None = Field(
        default=None,
        description=(
            'How the category was reached, or null when the event was '
            'added by hand or matched nothing. Stored as it happened, '
            'because the data model can change between the day a run '
            'is collected and the day it is read.'
        )
    )
    added_by_hand: bool = Field(
        description=(
            'Whether a person pulled the event in rather than the '
            'search finding it.'
        )
    )
    roles: List[EventRoleView] = Field(
        description='The opportunities this event creates shifts for.'
    )
    duplicate_of: str | None = Field(
        default=None,
        description=(
            'Identifier of an earlier event in this revision that '
            'would create the same shift, or null when none would. '
            'Sameness is the row Amplify receives -- need ID, date, '
            'start and end -- so two events at one hour under '
            'different opportunities are two shifts, not a repeat.'
        )
    )
    blocking: bool = Field(
        description=(
            'Whether this event stops the run being sent. True when '
            'it has no opportunity to create a shift under. The run '
            'stops rather than dropping it, because a missing shift '
            'is invisible until volunteers cannot sign up.'
        )
    )


class OpportunityView(ApiModel):
    """ An Amplify opportunity a run creates shifts under. """

    need_id: str = Field(
        description='Amplify need ID.'
    )
    title: str = Field(
        description='Amplify opportunity title, as displayed.'
    )
    url: str = Field(
        description='Public address of the opportunity.'
    )
    max_length: int | None = Field(
        default=None,
        description=(
            'Longest shift the opportunity accepts, in minutes, or '
            'null when it sets no maximum.'
        )
    )
    offset_start: int = Field(
        description=(
            'Minutes added to an event\'s start to reach the shift\'s.'
        )
    )
    offset_end: int = Field(
        description=(
            'Minutes added to an event\'s end to reach the shift\'s.'
        )
    )
    default_slots: int = Field(
        description='Volunteers wanted per shift, before any edit.'
    )


class LogEntryView(ApiModel):
    """ One line of a run's change log. """

    id: int = Field(
        description=(
            'Identifier, ascending in the order entries were written.'
        )
    )
    revision: int = Field(
        description='Revision that was current when the change was made.'
    )
    logged_at: str = Field(
        description='When the change was made, as an ISO-8601 UTC time.'
    )
    principal_id: str = Field(
        description=(
            'Who made it. One value while the credential is a static '
            'token, and a real subject once an identity provider '
            'issues one, with no change to what records it.'
        )
    )
    entry: str = Field(
        description='What changed, written for a reader.'
    )


class RunDetailView(RunView):
    """ A run with everything the review screen reads at once.

        The events, the opportunities labelling them and the change
        log arrive together because a screen showing one shows all
        three, and reading them separately would let them disagree:
        each read would see the state at a different moment.
    """

    events: List[EventView] = Field(
        description=(
            'The current revision\'s events, by date and start time.'
        )
    )
    opportunities: List[OpportunityView] = Field(
        description=(
            'Amplify titles for every need ID this run touches, '
            'resolved while the run was collected and stored with it. '
            'Every review row is labelled with one, so they are not a '
            'lookup deferred to preview time.'
        )
    )
    log: List[LogEntryView] = Field(
        description=(
            'Every change made to the run, oldest first. Written '
            'where the change is made rather than assembled by '
            'whatever displays it, so it survives a reload and reads '
            'the same in a browser and a terminal.'
        )
    )


class RevisionView(ApiModel):
    """ One numbered version of a run's events. """

    number: int = Field(
        description='Position in the run\'s history, from one.'
    )
    created_at: str = Field(
        description='When it was created, as an ISO-8601 UTC time.'
    )
    label: str = Field(
        description='How the revision is named to a reader.'
    )
    changes: int = Field(
        description=(
            'How many changes were made while this revision was the '
            'current one. Zero means it was sealed and left, which is '
            'what tells a reader which revision in a list is worth '
            'looking at.'
        )
    )
    current: bool = Field(
        description=(
            'Whether this is the revision being edited now. Exactly '
            'one revision of a run is current, and it is the last: '
            'everything below it is history and is never written to '
            'again.'
        )
    )


class UncollectedEventView(ApiModel):
    """ One thing a run's window held that did not become an event. """

    id: str = Field(
        description=(
            'Calendar identifier of the event. The same identifier an '
            'event of the run carries, which is what names one when '
            'it is pulled in.'
        )
    )
    title: str | None = Field(
        default=None,
        description='Event title, or null when it has none.'
    )
    date: str | None = Field(
        default=None,
        description=(
            'Day of the event as an ISO date, in the run\'s own zone, '
            'or null when the calendar gave a value that could not be '
            'read as one.'
        )
    )
    calendar_start: str | None = Field(
        default=None,
        description=(
            'Start time on the calendar, or null for an all-day '
            'event, which has none.'
        )
    )
    calendar_end: str | None = Field(
        default=None,
        description='End time on the calendar, or null for an all-day event.'
    )
    addable: bool = Field(
        description=(
            'Whether this event may be pulled into the run. The '
            'server\'s answer rather than the client\'s, so that a '
            'button and the endpoint behind it cannot disagree: an '
            'event nobody searched for is addable until the run holds '
            'it, and one that cannot become a correct shift is '
            'refused here as well as there.\n\n'
            'An event already pulled in keeps its entry here and '
            'stops being addable. The entry is what a revert gives '
            'back: reverting to the first revision drops the '
            'hand-added events, and this list is where they return '
            'to.'
        )
    )


class UncollectedGroupView(ApiModel):
    """ What a run's window held and the run left out, by reason. """

    reason: str = Field(
        description=(
            f'Why these were left out: {", ".join(UNCOLLECTED_REASONS)}. '
            '"search" is the one no calendar event can carry -- it '
            'means no configured query string returned it, so nobody '
            'looked for it -- and it is the only reason an event may '
            'be pulled in under. The other three describe events that '
            'cannot become a correct shift.'
        )
    )
    events: List[UncollectedEventView] = Field(
        description='The events left out for this reason, earliest first.'
    )


# Described by its scope rather than by how many figures it holds.  A
# docstring here is published, and a count of the fields below it is a
# second statement of something the fields already say -- one that
# needs re-reading every time preview learns to report another figure,
# and that says nothing a reader could not see.
class PreviewTotalsView(ApiModel):
    """ What a send would do, totalled over the whole revision. """

    will_create: int = Field(
        description=(
            'Shifts that would be created. Counted by identity -- '
            'need ID, date, start and end -- so two events asking for '
            'the same row count once, and without the ones Amplify '
            'already holds. This is the number of rows that will '
            'arrive, and the number a send confirms against.'
        )
    )
    already_in_amplify: int = Field(
        description=(
            'Shifts the revision asks for that Amplify already has, '
            'read live from the opportunities themselves rather than '
            'from any record of what this run sent. They are skipped '
            'rather than created again; `skipped` names them.'
        )
    )
    repeated_rows: int = Field(
        description=(
            'How many shifts the revision asks for more than once. '
            'They create one shift, not several; the figure is here '
            'so a reader is told rather than left to wonder why the '
            'total is below the number of rows they can see.'
        )
    )
    blocking_events: int = Field(
        description=(
            'Events that cannot be sent. Above zero means nothing '
            'can be sent at all: the run stops and names them rather '
            'than dropping them, because a missing shift is invisible '
            'until volunteers cannot sign up.'
        )
    )


class PreviewRowView(ApiModel):
    """ What one Amplify opportunity would receive. """

    need_id: str = Field(
        description='Amplify need ID the shifts would be created under.'
    )
    title: str | None = Field(
        default=None,
        description=(
            'The opportunity\'s title, or null when the run stored no '
            'opportunity for this need ID, which means collection did '
            'not resolve one.'
        )
    )
    will_create: int = Field(
        description=(
            'Shifts this opportunity would receive, without the ones '
            'it already holds.'
        )
    )
    already_in_amplify: int = Field(
        description=(
            'Shifts this opportunity is asked for that it already '
            'holds, and which a send would skip. A row where this is '
            'the whole ask and `willCreate` is zero is an opportunity '
            'a send has nothing left to do for.'
        )
    )
    slots: int = Field(
        description=(
            'Volunteers wanted across the shifts that would be '
            'created. A skipped shift asks for nobody: it exists '
            'already, wanting whatever it was created wanting.'
        )
    )
    first_date: str | None = Field(
        default=None,
        description=(
            'Earliest day a shift would be created on, or null when '
            'none would be.'
        )
    )
    last_date: str | None = Field(
        default=None,
        description=(
            'Latest day a shift would be created on, or null when '
            'none would be. Of the shifts that would be created, not '
            'of every event under this opportunity: these are the days '
            'about to arrive in Amplify.'
        )
    )


class SkippedShiftView(ApiModel):
    """ One shift the revision asks for that Amplify already has.

        Named per shift and never only counted (D16). A count says how
        many rows will not arrive; it does not say which, and the
        reader deciding whether that is right is deciding about
        particular days and times.
    """

    need_id: str = Field(
        description=(
            'Opportunity the shift would have been created under.'
        )
    )
    date: str = Field(
        description='Day it falls on, as an ISO date.'
    )
    shift_start: str = Field(
        description='Time of day it starts.'
    )
    shift_end: str = Field(
        description='Time of day it ends.'
    )


class BlockerView(ApiModel):
    """ One reason one event cannot become a shift. """

    event_id: str = Field(
        description='Event that cannot be sent.'
    )
    reason: str = Field(
        description=(
            f'Why: {", ".join(BLOCKER_REASONS)}. An event with two '
            'things wrong with it appears once for each, so fixing '
            'one does not reveal another.'
        )
    )


class PreviewView(ApiModel):
    """ What sending the current revision would create.

        Grouped by opportunity and never by category: several
        categories share one Amplify listing, so grouping by category
        would show that listing twice under two names and split a
        total the reader is about to check against Amplify.

        Every opportunity the revision touches is read live while this
        is answered, so the totals are net of what Amplify already
        holds. The send re-reads the same way inside its own
        transaction, which is what makes the number shown here the
        number of rows that arrive.
    """

    totals: PreviewTotalsView = Field(
        description=(
            'What a send would do, totalled over the whole revision '
            'rather than per opportunity.'
        )
    )
    rows: List[PreviewRowView] = Field(
        description=(
            'One per opportunity the revision asks for a shift under, '
            'by need ID. An opportunity the run resolved but asks '
            'nothing of has no row; one whose shifts Amplify already '
            'holds keeps its row and says so.'
        )
    )
    skipped: List[SkippedShiftView] = Field(
        description=(
            'Every shift Amplify already has, by need ID and then by '
            'when it falls. A send skips exactly these.'
        )
    )
    blockers: List[BlockerView] = Field(
        description=(
            'Every reason an event cannot be sent, in the order the '
            'events are shown.'
        )
    )


class EditView(ApiModel):
    """ A revision after a change, and what the change wrote down. """

    events: List[EventView] = Field(
        description=(
            'The revision\'s events as they now are, in the order they '
            'are stored. Every event, not only the ones that changed: '
            'a reviewer\'s screen is redrawn from this, and a partial '
            'list would leave it guessing what it still holds.'
        )
    )
    log: List[LogEntryView] = Field(
        description=(
            'The entries this call added to the run\'s change log, one '
            'per operation. Written server-side, so the log survives a '
            'reload and reads the same in a browser and a terminal.'
        )
    )


# What the deployment was configured with, rather than anything a run
# holds.  Below, because a reader working through this file is reading
# about runs until they reach these two.
class CategoryView(ApiModel):
    """ One category of the data model, for a calendar that offers it.

        What a reviewer chooses from when an event matched nothing, or
        matched the wrong thing.  The identifier is what an edit
        sends; the label is what the data model calls it, and a
        client shows the Amplify titles for the need IDs where it has
        them, because those are what a shift is created under.
    """

    key: str = Field(
        description=(
            'What an edit names this category by, which is what the '
            '"category" field of a "set_category" operation takes.'
        ),
        examples=['adult_game']
    )
    label: str = Field(
        description=(
            'What the data model calls this category. Written for a '
            'person, and not an Amplify opportunity title: one '
            'category can create shifts under more than one need.'
        ),
        examples=['Adult Games']
    )
    need_ids: List[str] = Field(
        description=(
            'Amplify need IDs an event in this category creates a '
            'shift under, one each. More than one is ordinary -- an '
            'event serving skating and non-skating officials creates '
            'two shifts -- and several categories may share a need.'
        ),
        examples=[['879609', '879610']]
    )


class CalendarView(ApiModel):
    """ One calendar a run may be collected from. """

    key: str = Field(
        description=(
            'What a collection names this calendar by, which is what '
            'the "calendar" field of a collection request takes.'
        ),
        examples=['practices']
    )
    search_terms: List[str] = Field(
        description=(
            'The query strings this calendar\'s window is searched '
            'with, one request each. An empty string searches for '
            'nothing in particular and so returns the whole window, '
            'which is what makes a search miss impossible on a '
            'calendar configured with one: an event left out of a run '
            'for the "search" reason is an event none of these '
            'returned.'
        ),
        examples=[['officials', 'scrimmage']]
    )
    categories: List[CategoryView] = Field(
        description=(
            'The categories this calendar\'s data model offers, which '
            'are what a "set_category" edit may name. The fallback '
            'the model uses when a title matches nothing is not among '
            'them: its need IDs are empty on purpose, so an event put '
            'under it could not become a shift, and offering it would '
            'be offering a choice the write refuses.'
        )
    )


class CredentialView(ApiModel):
    """ What asking Amplify about the service's credential answered. """

    working: bool = Field(
        description=(
            'Whether Amplify accepted a request carrying the '
            'credential this service is running on. False also covers '
            'a credential that is not configured at all, and the '
            'reason says which.'
        ),
        examples=[True]
    )
    last_four: Optional[str] = Field(
        default=None,
        description=(
            'The last four characters of the credential, which is '
            'enough to tell two apart and no use to whoever reads it. '
            'The credential itself is never published, and no '
            'endpoint replaces it: rotation is changing the secret '
            'and restarting (D8). Absent when none is configured.'
        ),
        examples=['4f2a']
    )
    reason: Optional[str] = Field(
        default=None,
        description=(
            'Why the credential did not work, written for a person. '
            'Absent when it did.'
        ),
        examples=[None]
    )


class UnmatchedTitleView(ApiModel):
    """ A title the data model did not match, and how often. """

    calendar: str = Field(
        description='Which configured calendar it was seen in.',
        examples=['events']
    )
    title: str = Field(
        description='The title, as the calendar gave it.',
        examples=['Jet City vs Cherry City']
    )
    times_seen: int = Field(
        description=(
            'How many runs this title turned up in, plus any '
            'sightings recorded by hand. What says whether a title is '
            'worth an alias: one that turns up every month is a '
            'category the model is missing, and one seen once is an '
            'event that happened once. A run counts once however many '
            'events carry the title and however often its window is '
            'collected again.'
        ),
        examples=[3]
    )
    first_seen: str = Field(
        description='When the earliest sighting was recorded, UTC.',
        examples=['2026-08-01T17:04:11Z']
    )
    last_seen: str = Field(
        description='When the most recent one was, UTC.',
        examples=['2026-09-01T16:58:02Z']
    )


class RetentionView(ApiModel):
    """ How long what a run leaves behind is kept. """

    job_log_days: int = Field(
        description=(
            'How long a job\'s event log is kept after the job '
            'finished. The job itself is not removed with it: that a '
            'send ran on a date and how it ended outlives the log of '
            'what it did, which is the part naming volunteers and the '
            'times they were asked to be somewhere.'
        ),
        examples=[90]
    )
    revision_days: int = Field(
        description=(
            'How long a run may go untouched before the revisions '
            'between its first and its current one are removed. '
            'Neither of those two is ever removed: the first is the '
            'run as the calendar gave it, which reverting to is a '
            'published operation, and the current one is what the run '
            'holds now.'
        ),
        examples=[90]
    )
    unmatched_title_days: int = Field(
        description=(
            'The longest a title the data model did not match is kept '
            'without being seen again. A backstop rather than the '
            'rule: what usually removes a title is the model coming '
            'to match it, since that is what recording one is for. '
            'Measured from the most recent sighting, so a title still '
            'turning up keeps its whole count.'
        ),
        examples=[365]
    )


class ConfigView(ApiModel):
    """ What the service resolved from its environment. """

    timezone: str = Field(
        description=(
            'IANA zone a calendar window\'s dates are read in when '
            'they carry no UTC offset. The server\'s zone is the '
            'authoritative one: a client displays it rather than '
            'working a window out in the zone of whoever is looking '
            'at it.'
        ),
        examples=['America/Los_Angeles']
    )
    match_threshold: int = Field(
        description=(
            'Confidence out of 100 a fuzzy title match has to reach '
            'when no alias appears in an event title. Below it the '
            'title is left unmatched, which blocks the send rather '
            'than guessing at an opportunity.'
        ),
        examples=[80]
    )
    excluded_title_terms: List[str] = Field(
        description=(
            'Terms this deployment never collects. An event whose '
            'title contains one of them anywhere is left out of a run '
            'with the "excluded" reason instead of becoming a shift, '
            'and no editing brings it back.'
        ),
        examples=[['canceled', 'cancelled']]
    )
    calendars: List[CalendarView] = Field(
        description=(
            'The calendars a run may be collected from, by key. This '
            'is where a client learns which keys a collection request '
            'accepts, because the keys belong to a deployment rather '
            'than to this contract. The calendar identifiers '
            'themselves are not published: nothing a caller does '
            'names one.'
        )
    )
    retention: RetentionView = Field(
        description=(
            'How long what a run leaves behind is kept. The record of '
            'what a send put into Amplify is deliberately absent, '
            'because it is never removed: duplicate safety reads it '
            'to know which rows a run already created, so a window '
            'there would eventually have a run offering to create '
            'shifts Amplify already holds.'
        )
    )
