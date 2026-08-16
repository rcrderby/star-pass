#!/usr/bin/env python3
""" Reading runs, one in full, its history and what it would send.

    The first callers of the repository layer's run and revision side:
    the list a person opens the tool on, the run itself with
    everything the review screen reads at once, the numbered versions
    its events have been through, and what sending it would create.

    No domain logic lives here, and no shaping either.  A route
    decides what to read and what a failure looks like; the
    contract package turns
    what was read into what a caller is shown, because the command
    line client shows the same answers from the same database and the
    two must not drift (D1, D2).
"""

# Imports - Python Standard Library
from typing import List

# Imports - Third-Party
from fastapi import APIRouter, HTTPException, Path, status

# Imports - Local
from star_pass._reading import (
    read_run_detail,
    read_run_for_send,
    read_run_history
)
from star_pass._repository import RunRepository
from star_pass_contract import (
    no_such_run,
    PreviewView,
    RevisionView,
    RunDetailView,
    RunView,
    to_detail_view,
    to_preview_view,
    to_revision_views,
    to_run_view
)
from . import _defaults
from ._security import Principal, requires, SCOPE_RUNS_READ
from ._storage import read

router = APIRouter(tags=[_defaults.API_TAG_RUNS])


def _missing(
        run_id: str
) -> HTTPException:
    """ Return the failure for a run that is not there.

        Raised by the endpoint rather than left to the repository,
        which reports a value it cannot use and a missing run the same
        way; only the endpoint knows it was asked for one by
        identifier.

        Args:
            run_id (str):
                What the caller asked for.

        Returns:
            error (HTTPException):
                A 404 naming the run.
    """

    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=no_such_run(run_id=run_id)
    )


@router.get(
    '/runs',
    summary='List the runs, newest first',
    description=(
        'Every run the service holds, most recently collected first, '
        'including one still being collected. Each carries what its '
        'current revision holds and the job still working on it, so '
        'the list is enough to decide what to open without reading '
        'each run in turn.'
    ),
    response_model=List[RunView]
)
async def list_runs(
        principal: Principal = requires(SCOPE_RUNS_READ)
) -> List[RunView]:
    """ Return every run.

        Args:
            principal (Principal):
                The authenticated caller, which the dependency supplies
                after checking the scope.

        Returns:
            runs (List[RunView]):
                Every run, newest first.
    """

    del principal

    runs = await read(
        lambda connection: RunRepository(
            connection=connection
        ).list_all()
    )

    return [to_run_view(run=run) for run in runs]


@router.get(
    '/runs/{run_id}',
    summary='Read one run in full',
    description=(
        'The run, the events of its current revision, the Amplify '
        'opportunities labelling them, and the log of everything done '
        'to it. Read together because a screen showing one shows all '
        'of them, and separate reads could disagree.\n\n'
        'Each event carries what its stored row does not say: how long '
        'the shift is, the maximum that shortened it, whether an '
        'earlier event would create the same shift, and whether it '
        'blocks the send.'
    ),
    response_model=RunDetailView
)
async def get_run(
        run_id: str = Path(
            description='Identifier the run was created with.'
        ),
        principal: Principal = requires(SCOPE_RUNS_READ)
) -> RunDetailView:
    """ Return one run and everything shown beside it.

        Args:
            run_id (str):
                Identifier of the run to read.

            principal (Principal):
                The authenticated caller, which the dependency supplies
                after checking the scope.

        Raises:
            HTTPException:
                404 when there is no such run.

        Returns:
            run (RunDetailView):
                The run in full.
    """

    del principal

    detail = await read(
        lambda connection: read_run_detail(
            connection=connection,
            run_id=run_id
        )
    )

    if detail is None:
        raise _missing(run_id=run_id)

    return to_detail_view(detail=detail)


@router.get(
    '/runs/{run_id}/revisions',
    summary='List a run\'s revisions, oldest first',
    description=(
        'Every numbered version of the run\'s events, in the order '
        'they were made. Everything below the current revision is '
        'history and is never written to again: editing adds a '
        'revision holding a copy, and reverting does the same rather '
        'than deleting anything, so the record of what was done '
        'survives being undone.\n\n'
        'Each carries how many changes were made while it was '
        'current, which is what says whether a revision is worth '
        'looking at.'
    ),
    response_model=List[RevisionView]
)
async def list_revisions(
        run_id: str = Path(
            description='Identifier the run was created with.'
        ),
        principal: Principal = requires(SCOPE_RUNS_READ)
) -> List[RevisionView]:
    """ Return a run's revisions.

        Args:
            run_id (str):
                Identifier of the run to read the history of.

            principal (Principal):
                The authenticated caller, which the dependency supplies
                after checking the scope.

        Raises:
            HTTPException:
                404 when there is no such run.  A run that exists and
                has no revision yet answers with an empty list, which
                is a different fact and reads differently.

        Returns:
            revisions (List[RevisionView]):
                Every revision of the run, oldest first.
    """

    del principal

    history = await read(
        lambda connection: read_run_history(
            connection=connection,
            run_id=run_id
        )
    )

    if history is None:
        raise _missing(run_id=run_id)

    run, revisions = history

    return to_revision_views(run=run, revisions=revisions)


@router.get(
    '/runs/{run_id}/preview',
    summary='Report what sending this run would create',
    description=(
        'What a send would do, grouped by Amplify opportunity and '
        'never by category: several categories share one listing, so '
        'grouping by category would show it twice under two names and '
        'split a total the reader is about to check against Amplify.\n\n'
        'Shifts are counted by identity -- need ID, date, start and '
        'end -- so two events asking for the same row count once, and '
        'a reader is told how many rows repeat rather than left to '
        'wonder why the total is below what they can see.\n\n'
        'An event that cannot become a shift stops the whole send and '
        'is named with every reason it cannot, so fixing one does not '
        'reveal another.\n\n'
        '**This does not yet say which shifts Amplify already has.** '
        'That needs a read of the live opportunity, which arrives with '
        'the send path that re-checks the same thing inside its '
        'transaction, so that both ask the question the same way. '
        'Until then the totals describe what the stored revision would '
        'create, and some of it may already exist.'
    ),
    response_model=PreviewView
)
async def get_preview(
        run_id: str = Path(
            description='Identifier the run was created with.'
        ),
        principal: Principal = requires(SCOPE_RUNS_READ)
) -> PreviewView:
    """ Return what sending the run's current revision would create.

        Args:
            run_id (str):
                Identifier of the run to preview.

            principal (Principal):
                The authenticated caller, which the dependency supplies
                after checking the scope.

        Raises:
            HTTPException:
                404 when there is no such run.

        Returns:
            preview (PreviewView):
                What a send would do.
    """

    del principal

    gathered = await read(
        lambda connection: read_run_for_send(
            connection=connection,
            run_id=run_id
        )
    )

    if gathered is None:
        raise _missing(run_id=run_id)

    events, opportunities = gathered

    return to_preview_view(
        events=events,
        opportunities=opportunities
    )
