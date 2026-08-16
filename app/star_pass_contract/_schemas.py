#!/usr/bin/env python3
""" The shapes the service sends and receives.

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
from typing import List

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
    RUN_STATUSES
)


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
            'consecutive dates.'
        )
    )
    timezone: str = Field(
        description=(
            'Zone the two dates are read in. The server\'s zone is '
            'the authoritative one: a client displays these dates and '
            'never works a window out in the zone of whoever is '
            'looking at it.'
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
            'the same row count once.'
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
        description='Shifts this opportunity would receive.'
    )
    slots: int = Field(
        description='Volunteers wanted across those shifts.'
    )
    first_date: str = Field(
        description='Earliest day a shift would be created on.'
    )
    last_date: str = Field(
        description=(
            'Latest day a shift would be created on. Of the shifts '
            'that would be created, not of every event under this '
            'opportunity: these are the days about to arrive in '
            'Amplify.'
        )
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
    """

    totals: PreviewTotalsView = Field(
        description=(
            'What a send would do, totalled over the whole revision '
            'rather than per opportunity.'
        )
    )
    rows: List[PreviewRowView] = Field(
        description=(
            'One per opportunity that would receive a shift, by need '
            'ID. An opportunity the run resolved but would send '
            'nothing to has no row.'
        )
    )
    blockers: List[BlockerView] = Field(
        description=(
            'Every reason an event cannot be sent, in the order the '
            'events are shown.'
        )
    )
