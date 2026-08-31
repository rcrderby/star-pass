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

        Named per shift and never only counted. A count says how
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
            'by title, and by need ID where Amplify gave no title or '
            'two share one. Ordered by what a client draws rather '
            'than by the need ID, which is on no screen. An '
            'opportunity the run resolved but asks nothing of has no '
            'row; one whose shifts Amplify already holds keeps its '
            'row and says so.'
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
