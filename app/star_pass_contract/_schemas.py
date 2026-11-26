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


# The header a send is claimed under.  Named here rather than in
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
    """ A job that collects or sends a run. """

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
            f'Where it is: {", ".join(JOB_STATUSES)}. `interrupted` '
            'means the process running the job stopped before the job '
            'ended. You may resume an interrupted job with `POST '
            '/v1/jobs/{job_id}/resume`.'
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
            'Why the job failed, when the reason is one a caller can '
            'act on. For an unexpected failure, the reason is in the '
            'service log.'
        )
    )


class WindowView(ApiModel):
    """ A run's date range and time zone. """

    start: str = Field(
        description='First day the run covers, as an ISO date.'
    )
    end: str = Field(
        description=(
            'Day after the last day the run covers, as an ISO date. A '
            'one-day run has two consecutive dates. The service '
            'stores, sends, and compares this value. `lastDay` gives '
            'the same date range by its last day.'
        )
    )
    last_day: str = Field(
        description=(
            'Last day the run covers, as an ISO date: the day before '
            '`end`. Clients display this value.'
        )
    )
    timezone: str = Field(
        description=(
            'The time zone of the two dates. It is the zone the '
            'calendar is read in, and the zone the configuration '
            'reports. Clients display the dates in this zone.'
        )
    )


class RunCountsView(ApiModel):
    """ The current revision's counts. """

    events: int = Field(
        description='Events in the current revision.'
    )
    shifts: int = Field(
        description=(
            'Shifts a send would create, counted per role. An event '
            'with skating and non-skating officials creates two shifts.'
        )
    )
    unmatched: int = Field(
        description=(
            'Events that would create no shift, and block the send. An '
            'event has no opportunity when its title matched no '
            'category, or its category has no need ID.'
        )
    )
    uncollected: int = Field(
        description=(
            'Events in the run\'s date range that are not in the run. '
            'Counted over the run, not the current revision. Editing '
            'events does not change this count.'
        )
    )


class RunView(ApiModel):
    """ A run: one collection of League Calendar events. """

    id: str = Field(
        description='The run\'s identifier, created by the service.'
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
            'When the run last changed, as an ISO 8601 UTC time. For a '
            'run with no changes, the time it was collected.'
        )
    )
    current_revision: int = Field(
        description=(
            'Number of the revision now being edited, or 0 before the '
            'first one exists.'
        )
    )
    counts: RunCountsView = Field(
        description='The current revision\'s counts.'
    )
    active_job_id: str | None = Field(
        default=None,
        description=(
            'Identifier of the job working on this run, or null. To '
            'follow it, read the job or its event stream.'
        )
    )
    interrupted_job_id: str | None = Field(
        default=None,
        description=(
            'Identifier of the run\'s most recent job when it was '
            'interrupted, and null otherwise. A job is interrupted '
            'when the process running it stops before the job ends. '
            'You may resume it with `POST /v1/jobs/{job_id}/resume`.'
        )
    )
    may_delete: bool = Field(
        description=(
            'Whether this run may be deleted. False while the run is '
            'collecting events or sending shifts to Amplify, and after '
            'it sent shifts to Amplify.'
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
            'Similarity score from 0 to 100, or null for a keyword '
            'match.'
        )
    )


class EventRoleView(ApiModel):
    """ One opportunity an event creates a shift for, and the shift's
        timing. Two events may create shifts for the same opportunity
        with different offsets.
    """

    need_id: str = Field(
        description='The Amplify need ID for the shift.'
    )
    slots: int = Field(
        description='Volunteers wanted.'
    )
    edited: bool = Field(
        description=(
            'Whether a person changed the volunteer count from '
            '`defaultSlots`.'
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
    """ One event in the current revision. """

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
    calendar_note: str | None = Field(
        default=None,
        description=(
            'The event\'s League Calendar description, as text, or '
            'null when the calendar has no notes or the event has '
            'none. HTML is converted to text. Up to 1,000 characters. '
            'An event collected before schema version 11 has no note '
            'until its run is collected again.'
        ),
        examples=['Doors at 6 PM, Game at 7 PM']
    )
    shift_start: str = Field(
        description=(
            'Start time of the shift to create: the calendar start '
            'time plus the opportunity\'s offset.'
        )
    )
    shift_end: str = Field(
        description='End time of the shift to create.'
    )
    length_minutes: int = Field(
        description=(
            'The shift\'s length in minutes, as sent to Amplify. A '
            'length of 0 or less means the shift ends before it '
            'starts, and blocks the send.'
        )
    )
    capped_at: int | None = Field(
        default=None,
        description=(
            'The opportunity\'s maximum length, when it shortened this '
            'shift, and null otherwise.'
        )
    )
    category: str | None = Field(
        default=None,
        description=(
            'The data model category the title matched, or null when '
            'the title matched no category.'
        )
    )
    match: MatchView | None = Field(
        default=None,
        description=(
            'How the title matched its category, or null for a '
            'manually added event or a title with no match. Stored at '
            'collection.'
        )
    )
    added_by_hand: bool = Field(
        description=(
            'Whether the event was manually added from the uncollected '
            'list.'
        )
    )
    edited: bool = Field(
        description=(
            'Whether undoing this event\'s changes would change it. '
            'True when its shift times differ from its calendar times '
            'plus the category\'s offsets, or when a person set a '
            'role\'s volunteer count. False when the undo would be '
            'refused, such as when the data model does not have the '
            'event\'s category.'
        )
    )
    roles: List[EventRoleView] = Field(
        description='The opportunities this event creates shifts for.'
    )
    duplicate_of: str | None = Field(
        default=None,
        description=(
            'Identifier of an earlier event in this revision that '
            'would create the same shift, or null. The same shift '
            'means the same need ID, date, start, and end. Two events '
            'at the same time under different opportunities are two '
            'shifts.'
        )
    )
    blocking: bool = Field(
        description=(
            'Whether this event blocks the send. True when the event '
            'has no opportunity.'
        )
    )
    may_unassign: bool = Field(
        description=(
            'Whether the event\'s opportunity may be removed. True '
            'only when the collection matched no category for the '
            'event. To create no shift for a matched event, remove it '
            'from the run.'
        )
    )


class OpportunityView(ApiModel):
    """ An Amplify opportunity a run creates shifts for, as Amplify
        describes it. Each event's role sets the shift's timing.
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
    action: str = Field(
        description=(
            'The action. One of the edit operations, or `added` for an '
            'event added from the uncollected list. Clients word the '
            'action.'
        ),
        examples=['set_category']
    )
    subject: str | None = Field(
        default=None,
        description=(
            'Title of the event the action applied to, or null when it '
            'applied to more than one. Read with `subjectCount`.'
        ),
        examples=['Adult Scrimmages']
    )
    subject_count: int = Field(
        description='How many events it named.',
        examples=[1]
    )
    category: str | None = Field(
        default=None,
        description=(
            'The category key a `set_category` assigned, or null for '
            'other actions. `GET /v1/config` lists each category\'s '
            'label.'
        ),
        examples=['junior_scrimmage']
    )
    shift_time: str | None = Field(
        default=None,
        description=(
            'The time a `set_start` or `set_end` set, as `HH:MM` in '
            'the league\'s own zone, or null for every other action.'
        ),
        examples=['18:15']
    )
    minutes: int | None = Field(
        default=None,
        description=(
            'How many minutes a `nudge` moved the shifts, negative for '
            'earlier, or null for other actions.'
        ),
        examples=[-15]
    )
    slots: int | None = Field(
        default=None,
        description=(
            'How many volunteers a `set_slots` asked for, or null for '
            'every other action.'
        ),
        examples=[4]
    )
    need_id: str | None = Field(
        default=None,
        description=(
            'The need ID a `set_slots` applied to, or null for other '
            'actions.'
        ),
        examples=['905196']
    )


class RunDetailView(RunView):
    """ A run with its events, opportunities, and change log, read
        together.
    """

    events: List[EventView] = Field(
        description=(
            'The current revision\'s events, by date and start time.'
        )
    )
    opportunities: List[OpportunityView] = Field(
        description=(
            'Amplify titles for every need ID in the run, read when '
            'the run was collected.'
        )
    )
    log: List[LogEntryView] = Field(
        description='Every change made to the run, oldest first.'
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
            'How the revision was created: '
            f'{", ".join(REVISION_KINDS)}. Clients word the kind.'
        ),
        examples=['reverted']
    )
    source_revision: int | None = Field(
        default=None,
        description=(
            'The revision this one copies: the revision a revert '
            'restored, or the revision a save saved. Null for the '
            'revisions a collection creates.'
        ),
        examples=[1]
    )
    changes: int = Field(
        description=(
            'How many changes were made while this revision was '
            'current. 0 means the revision was saved with no further '
            'edits.'
        )
    )
    current: bool = Field(
        description=(
            'Whether this is the revision being edited. A run has one '
            'current revision, the latest. Earlier revisions do not '
            'change.'
        )
    )


class UncollectedEventView(ApiModel):
    """ One event in the run's date range that is not in the run. """

    id: str = Field(
        description=(
            'The event\'s League Calendar identifier. An event added '
            'to the run keeps this identifier.'
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
            'Start time on the calendar, or null for an all-day event.'
        )
    )
    calendar_end: str | None = Field(
        default=None,
        description='End time on the calendar, or null for an all-day event.'
    )
    calendar_note: str | None = Field(
        default=None,
        description=(
            'The event\'s League Calendar description, as text, or '
            'null when the calendar has no notes or the event has '
            'none. An event added to the run keeps this note.'
        ),
        examples=['Doors at 6 PM, Game at 7 PM']
    )
    addable: bool = Field(
        description=(
            'Whether this event may be added to the run. True for an '
            'event with the `search` reason until it is added.\n\nAn '
            'added event stays in this list, and is not addable. '
            'Reverting to revision 1 removes added events, and they '
            'become addable again.'
        )
    )


class UncollectedGroupView(ApiModel):
    """ The uncollected events in a run's date range, grouped by reason. """

    reason: str = Field(
        description=(
            'Why these events were not collected: '
            f'{", ".join(UNCOLLECTED_REASONS)}. `search` means no '
            'search term returned the event. Only events with this '
            'reason may be added to the run. The other reasons '
            'describe events that cannot become a correct shift.'
        )
    )
    events: List[UncollectedEventView] = Field(
        description='The events left out for this reason, earliest first.'
    )


class EditView(ApiModel):
    """ The revision after an edit, and the change log entries the edit
        added.
    """

    events: List[EventView] = Field(
        description=(
            'Every event in the revision, in stored order, including '
            'events that did not change.'
        )
    )
    log: List[LogEntryView] = Field(
        description=(
            'The change log entries this request added, one per '
            'operation.'
        )
    )


# What the deployment was configured with, rather than anything a run
# holds.  Below, because a reader working through this file is reading
# about runs until they reach these two.
class CategoryView(ApiModel):
    """ One data model category a calendar offers.

        A reviewer chooses from these to assign an event's opportunity.
        An edit sends the category's key. The label is the data model's
        name for the category. Clients display the Amplify titles for
        its need IDs.
    """

    key: str = Field(
        description=(
            'The category\'s key. A `set_category` operation names the '
            'category by this key.'
        ),
        examples=['adult_game']
    )
    label: str = Field(
        description=(
            'The category\'s name in the data model. This is not an '
            'Amplify opportunity title. One category may create shifts '
            'for more than one opportunity.'
        ),
        examples=['Adult Games']
    )
    need_ids: List[str] = Field(
        description=(
            'The Amplify need IDs an event in this category creates '
            'shifts for, one shift each. An event with skating and '
            'non-skating officials creates two shifts. Several '
            'categories may share a need ID.'
        ),
        examples=[['879609', '879610']]
    )


class CalendarView(ApiModel):
    """ One calendar a run may be collected from. """

    key: str = Field(
        description=(
            'The calendar\'s key. A collection request names the '
            'calendar by this key.'
        ),
        examples=['practices']
    )
    search_terms: List[str] = Field(
        description=(
            'The search terms for this calendar, one League Calendar '
            'request each. A calendar with no search terms lists one '
            'empty term, `""`. An empty term collects all events in '
            'the date range. In a calendar with search terms, events '
            'that do not match a search term are not collected, and '
            'are uncollected with the `search` reason.'
        ),
        examples=[['officials', 'scrimmage']]
    )
    notes: bool = Field(
        description=(
            'Whether this calendar\'s event descriptions are kept with '
            'their events. When true, each event in a run from this '
            'calendar has a `calendarNote`, null for an event with no '
            'description. When false, `calendarNote` is null on every '
            'event.'
        ),
        examples=[True]
    )
    categories: List[CategoryView] = Field(
        description=(
            'The categories a `set_category` operation may name for '
            'this calendar. The fallback for a title with no match is '
            'not included.'
        )
    )


class UnmatchedTitleView(ApiModel):
    """ A title the data model did not match, and how often it was seen. """

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
            'The number of runs the title appeared in, plus manually '
            'recorded sightings. A run counts each title once, no '
            'matter how many events have the title or how many times '
            'the run is re-collected.'
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
    """ How long the service retains each type of run data. """

    job_log_days: int = Field(
        description=(
            'How long a job\'s event log is retained after the job '
            'finishes. The job itself remains.'
        ),
        examples=[90]
    )
    revision_days: int = Field(
        description=(
            'How long a run may go unchanged before its revisions are '
            'removed. The first revision and the current revision '
            'remain.'
        ),
        examples=[90]
    )
    unmatched_title_days: int = Field(
        description=(
            'How long an unmatched title is retained after it was last '
            'seen. A title is also removed after the data model '
            'matches it.'
        ),
        examples=[365]
    )


class CredentialTestLimitView(ApiModel):
    """ How often each credential may be tested. """

    attempts: int = Field(
        description=(
            'Tests allowed per caller in each `windowSeconds` period.'
        ),
        examples=[5]
    )
    window_seconds: int = Field(
        description='The length of the rate limit period, in seconds.',
        examples=[60]
    )


class ConfigView(ApiModel):
    """ The settings the service read from its environment at startup. """

    timezone: str = Field(
        description=(
            'The IANA time zone for dates in a date range that have no '
            'UTC offset. Clients display dates in this zone.'
        ),
        examples=['America/Los_Angeles']
    )
    match_threshold: int = Field(
        description=(
            'The lowest similarity score, from 0 to 100, for a match. '
            'When a title contains no alias, the alias with the '
            'highest score matches if its score is at least this '
            'value. A title with no match has no opportunity, and '
            'blocks the send.'
        ),
        examples=[80]
    )
    excluded_title_terms: List[str] = Field(
        description=(
            'Filtered terms. An event whose title contains a filtered '
            'term is not collected. It is uncollected with the '
            '`excluded` reason, and may not be added to a run.'
        ),
        examples=[['canceled', 'cancelled']]
    )
    calendars: List[CalendarView] = Field(
        description=(
            'The calendars a run may be collected from, by key. '
            'Calendar identifiers are not published.'
        )
    )
    retention: RetentionView = Field(
        description=(
            'How long the service retains each type of run data. '
            'Shifts sent to Amplify are retained indefinitely to '
            'prevent duplicate shifts, and have no entry.'
        )
    )
    credential_test_limit: Optional[CredentialTestLimitView] = Field(
        default=None,
        description=(
            'How often each credential may be tested through the '
            'service. Null where testing is not rate-limited.'
        )
    )
