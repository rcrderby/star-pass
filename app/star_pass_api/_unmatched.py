#!/usr/bin/env python3
""" Titles the data model did not match, kept for the next model edit.

    A title no category matches blocks the send of the run it is in,
    which gets that run out of the door.  What it does not do is
    survive: the run is superseded, and the next person editing
    'shift_info.yml' is working from memory and from whatever they
    scrolled back to in a log.

    So this is a log of its own, belonging to no run, read when the
    model is about to be edited.  **Append-only**: nothing updates an
    entry and nothing deletes one, because how often a title has
    turned up is the evidence for a decision nobody has made yet.

    Most of what it holds is written by collections rather than
    through here: a collection is where a title is discovered to match
    nothing, and a log that depended on somebody remembering to say so
    would hold what people remembered rather than what happened.  This
    endpoint is for the sighting that arrives another way -- somebody
    looking at a blocked event, or at a calendar nobody has collected
    yet.

    No idempotency key.  A run is held to one sighting of a title by
    the repository, so a retry naming one adds nothing on its own; a
    sighting naming no run is one nothing can be the same as, and
    recording it twice means it was seen twice.  Nothing here is
    irreversible, and nothing about a run changes.
"""

# Imports - Python Standard Library
from typing import List

# Imports - Third-Party
from fastapi import APIRouter, status

# Imports - Local
from star_pass._repository import UnmatchedTitleRepository
from star_pass_contract import (
    to_unmatched_title_views,
    to_unmatched_view,
    UnmatchedTitleRequest,
    UnmatchedTitleView
)
from . import _defaults
from ._runs import checked_calendar
from ._security import (
    Principal,
    requires,
    SCOPE_CONFIG_READ,
    SCOPE_RUNS_WRITE
)
from ._storage import in_the_database

router = APIRouter(tags=[_defaults.API_TAG_SERVICE])


@router.get(
    '/unmatched-titles',
    summary='List titles the data model has not matched',
    description=(
        'One entry per title in a calendar, with how many sightings '
        'have been recorded -- one per run it turned up in, plus any '
        'recorded by hand -- and when the first and most recent were. '
        'Newest sighting first, so a title that has just started '
        'turning up is read before one somebody has already decided '
        'about.\n\n'
        'What it is for: the next edit of the shift data model. A '
        'title seen every month is a category the model is missing; '
        'one seen once is an event that happened once, and the count '
        'is what tells them apart.\n\n'
        'Belongs to no run. A run is a window that is eventually '
        'superseded, and what the model is missing outlives it.'
    ),
    response_model=List[UnmatchedTitleView]
)
async def list_unmatched_titles(
        principal: Principal = requires(SCOPE_CONFIG_READ)
) -> List[UnmatchedTitleView]:
    """ Return every title the data model has not matched.

        Args:
            principal (Principal):
                The authenticated caller, which the dependency
                supplies after checking the scope.

        Returns:
            unmatched (List[UnmatchedTitleView]):
                One entry per title in a calendar, newest first.
    """

    del principal

    return to_unmatched_title_views(
        unmatched=await in_the_database(
            lambda connection: UnmatchedTitleRepository(
                connection=connection
            ).list_all()
        )
    )


@router.post(
    '/unmatched-titles',
    status_code=status.HTTP_201_CREATED,
    summary='Record a title the data model did not match',
    description=(
        'Adds one sighting, for a title noticed outside a '
        'collection: collections record what they find themselves.\n\n'
        'A title recorded twice against no run is two sightings and '
        'one entry, because how often a title turns up is what says '
        'whether it is worth an alias and an entry overwritten would '
        'answer "once" forever. A run counts once however often it is '
        'named, so a retry adds nothing.\n\n'
        'Answers with the entry as the log now holds it, this '
        'sighting counted.\n\n'
        'The calendar has to be one the deployment configured, '
        'because the categories a title is matched against belong to '
        'a calendar. The run is optional provenance: the log outlives '
        'the run, and deleting one does not take the reason somebody '
        'was going to edit the model.\n\n'
        'No `Idempotency-Key`. A request naming a run is already '
        'answered the same way twice, and one naming none records '
        'that the title was seen again, which is true.'
    ),
    response_model=UnmatchedTitleView
)
async def record_unmatched_title(
        seen: UnmatchedTitleRequest,
        principal: Principal = requires(SCOPE_RUNS_WRITE)
) -> UnmatchedTitleView:
    """ Record one sighting of a title the model did not match.

        Args:
            seen (UnmatchedTitleRequest):
                The title, the calendar it was seen in, and the run it
                was noticed in when there was one.

            principal (Principal):
                Who recorded it, which the dependency supplies after
                checking the scope.

        Raises:
            HTTPException:
                422 when the calendar is not one this service reads.

        Returns:
            unmatched (UnmatchedTitleView):
                The entry as the log now holds it.
    """

    calendar = checked_calendar(calendar=seen.calendar)

    return to_unmatched_view(
        unmatched=await in_the_database(
            lambda connection: UnmatchedTitleRepository(
                connection=connection
            ).record(
                calendar=calendar,
                title=seen.title,
                run_id=seen.run_id,
                principal_id=principal.id
            )
        )
    )
