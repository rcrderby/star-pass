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
from star_pass._records import (
    JOB_KINDS,
    JOB_STATUSES,
    MATCH_KIND_FUZZY,
    MATCH_KIND_KEYWORD,
    REVISION_KINDS,
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
    interrupted_job_id: str | None = Field(
        default=None,
        description=(
            'Identifier of the job this run last ran, when the '
            'service stopped while it was in hand, and null '
            'otherwise. Resuming one is a deliberate act and never '
            'automatic (D10), which means a caller has to be able to '
            'name it -- and an interrupted job is finished, so it is '
            'never the "activeJobId". Only the run\'s most recent job '
            'is reported here: a send that a later one has since '
            'carried out is not something to offer to resume.'
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
    """ One opportunity an event creates a shift for, and how it does.

        The timing is the role's and not the opportunity's: one Amplify
        listing can be named by categories that time it differently, so
        two events in a run may send to one listing on different
        offsets (D25).
    """

    need_id: str = Field(
        description='Amplify need ID the shift is created under.'
    )
    slots: int = Field(
        description='Volunteers wanted.'
    )
    edited: bool = Field(
        description=(
            'Whether a person changed the count from '
            '\'defaultSlots\'. Recorded rather than compared against '
            'the default now, because an event collected again can '
            'arrive with another.'
        )
    )
    offset_start: int = Field(
        description=(
            'Minutes added to the event\'s start to reach the '
            'shift\'s.'
        )
    )
    offset_end: int = Field(
        description=(
            'Minutes added to the event\'s end to reach the shift\'s.'
        )
    )
    max_length: int | None = Field(
        default=None,
        description=(
            'Longest shift the opportunity accepts, in minutes, or '
            'null when it sets no maximum.'
        )
    )
    default_slots: int = Field(
        description=(
            'Volunteers the category asked for, before any edit.'
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
    edited: bool = Field(
        description=(
            'Whether undoing the changes to this event would change '
            'it. True when its shift times no longer follow from the '
            'calendar times and the category\'s offsets, or when a '
            'role wants a number of volunteers somebody set. Answered '
            'here because nothing stored says it: the calendar times '
            'never move, so only the data model says what the shift '
            'times would have been, and a caller working that out '
            'would be a second copy of the timing rules. False as '
            'well when the undo could not be carried out -- a category '
            'that has left the data model -- because that is the '
            'refusal the operation itself would raise, and a row said '
            'to be editable is a row offered a control that fails.'
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
    may_unassign: bool = Field(
        description=(
            'Whether this event may be put back to having no '
            'opportunity. True where the collection matched no '
            'category for it, which is the only row unassigned is a '
            'state of: it is where that row began, so returning it '
            'there is putting it back rather than breaking it. '
            'Answered here rather than worked out by a caller for the '
            'same reason `edited` is - the rule is the one the '
            '`unassign` operation refuses by, and a control offered '
            'where the operation would refuse is a control that '
            'fails. A matched row that should create no shift is '
            'removed from the run instead.'
        )
    )


class OpportunityView(ApiModel):
    """ An Amplify opportunity a run creates shifts under.

        What Amplify says about the listing, and nothing else. How a
        shift is timed under it belongs to the role that creates the
        shift (D25).
    """

    need_id: str = Field(
        description='Amplify need ID.'
    )
    title: str = Field(
        description='Amplify opportunity title, as displayed.'
    )
    url: str = Field(
        description='Public address of the opportunity.'
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
    kind: str = Field(
        description=(
            f'How the revision came to exist: {", ".join(REVISION_KINDS)}. '
            'An identifier rather than a sentence, because a client '
            'that is handed the words cannot word it -- and the '
            'sentence used to be stored on the row, so a change of '
            'wording would have left every revision already recorded '
            'saying the old thing beside a new one saying the new.'
        ),
        examples=['reverted']
    )
    source_revision: int | None = Field(
        default=None,
        description=(
            'The revision this one was made from, which is the '
            'revision its rows were copied from. The one a revert '
            'went back to, or the one a seal fixed; null for the two '
            'a collection fills, which are made from a calendar and '
            'not from a revision.'
        ),
        examples=[1]
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
