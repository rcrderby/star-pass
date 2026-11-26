#!/usr/bin/env python3
""" The shapes a preview answers with.

    What sending a revision would create, worked out before it does.
    Its own module beside '_schemas.py', which the thousand-line cap
    the linter holds a module to had run out of room in -- and these
    are the five to move, because the preview is one answer with a
    boundary of its own: the core works it out in '_preview.py' for
    the same reason, and nothing outside it builds one of these.

    Read back into '_schemas.py' by nothing.  A caller reaches them
    through the package, which is where every published shape is
    named whichever file it is written in.
"""

# Imports - Python Standard Library
from typing import List

# Imports - Third-Party
from pydantic import Field

# Imports - Local
from star_pass._preview import BLOCKER_REASONS
from ._schemas import ApiModel


# Described by its scope rather than by how many figures it holds.  A
# docstring here is published, and a count of the fields below it is a
# second statement of something the fields already say -- one that
# needs re-reading every time preview learns to report another figure,
# and that says nothing a reader could not see.
class PreviewTotalsView(ApiModel):
    """ What a send would do, totaled over the entire revision. """

    will_create: int = Field(
        description=(
            'Shifts a send would create, not including shifts already '
            'in Amplify. Counted by need ID, date, start, and end. Two '
            'events that would create the same shift count once. A '
            'send confirms against this number.'
        )
    )
    already_in_amplify: int = Field(
        description=(
            'Shifts in the revision that Amplify already has, read '
            'from the opportunities in Amplify. A send skips them.'
        )
    )
    repeated_rows: int = Field(
        description=(
            'How many shifts the revision includes more than once. '
            'Each repeated shift is created once.'
        )
    )
    blocking_events: int = Field(
        description=(
            'Events that cannot be sent. While this is above 0, the '
            'run may not be sent.'
        )
    )


class PreviewRowView(ApiModel):
    """ What one Amplify opportunity would receive. """

    need_id: str = Field(
        description='The Amplify need ID for the shifts.'
    )
    title: str | None = Field(
        default=None,
        description=(
            'The opportunity\'s title, or null when the collection did '
            'not read a title for this need ID.'
        )
    )
    will_create: int = Field(
        description=(
            'Shifts this opportunity would receive, not including '
            'shifts it already has.'
        )
    )
    already_in_amplify: int = Field(
        description=(
            'Shifts this opportunity already has. A send skips them. '
            'When `willCreate` is 0, a send creates no shifts for this '
            'opportunity.'
        )
    )
    slots: int = Field(
        description=(
            'Volunteer count across the shifts a send would create. '
            'Skipped shifts are not included.'
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
    """ One shift in the revision that Amplify already has. Each skipped
        shift is listed by date and time.
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
    """ One reason an event cannot become a shift. """

    event_id: str = Field(
        description='Event that cannot be sent.'
    )
    reason: str = Field(
        description=(
            f'Why: {", ".join(BLOCKER_REASONS)}. An event with two '
            'reasons is listed twice.'
        )
    )


class PreviewView(ApiModel):
    """ What sending the current revision would create, grouped by
        Amplify opportunity. Several categories may share one
        opportunity.

        The service reads every opportunity from Amplify to answer. The
        totals do not include shifts already in Amplify. A send checks
        Amplify again before it writes.
    """

    totals: PreviewTotalsView = Field(
        description=(
            'What a send would do, totaled over the entire revision.'
        )
    )
    rows: List[PreviewRowView] = Field(
        description=(
            'One row per opportunity the revision creates shifts for, '
            'by title, and by need ID when Amplify gave no title or '
            'two opportunities share one. In the order a client '
            'displays them. An opportunity with no shifts in the '
            'revision has no row. An opportunity whose shifts are all '
            'in Amplify keeps its row.'
        )
    )
    skipped: List[SkippedShiftView] = Field(
        description=(
            'Every shift Amplify already has, by need ID and then by '
            'time. A send skips these shifts.'
        )
    )
    blockers: List[BlockerView] = Field(
        description=(
            'Every reason an event cannot be sent, in the order the '
            'events are shown.'
        )
    )
