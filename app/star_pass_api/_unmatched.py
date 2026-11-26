#!/usr/bin/env python3
""" Titles the data model did not match, kept for the next model edit.

    A title no category matches blocks the send of the run it is in,
    and the run is eventually superseded.  This is a log of its own,
    belonging to no run, read when 'shift_info.yml' is about to be
    edited.

    Append-only: nothing updates an entry and nothing deletes one,
    because how often a title has turned up is the evidence for the
    edit.

    Most of what it holds is written by collections.  This endpoint is
    for the sighting that arrives another way -- somebody looking at a
    blocked event, or at a calendar nobody has collected yet.

    No idempotency key.  The repository holds a run to one sighting of
    a title, so a retry naming one adds nothing; a sighting naming no
    run is one nothing can be the same as, and recording it twice
    means it was seen twice.
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
        'One entry per title and calendar, newest to oldest, with the '
        'number of sightings and when the title was first and last '
        'seen. Each run the title appears in adds one sighting, and so '
        'does each manually recorded sighting.\n\nA title that appears '
        'routinely is likely a category missing from the data model. A '
        'title seen once may be a one-time event.\n\nAny unmatched '
        'titles from a run remain in the log after the run is deleted.'
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
        'Records one sighting of a title found outside a collection. '
        'Collections record their own sightings.\n\nA title recorded '
        'twice with no run is two sightings in one entry. A run counts '
        'each title once, so a retry that names the same run adds no '
        'sighting.\n\nAnswers with the updated entry.\n\nThe calendar '
        'must be one the deployment configured. The run is optional. '
        'Any unmatched titles from a run remain in the log after the '
        'run is deleted.\n\nTakes no `Idempotency-Key`.'
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
