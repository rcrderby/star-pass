#!/usr/bin/env python3
""" The numbered versions of a run's events, and moving between them.

    Its own module rather than three more endpoints beside the run
    reads.  Sealing fixes what the run holds now as something to come
    back to; reverting is coming back to it.

    Neither destroys anything.  Each adds a revision holding a copy --
    of the current one when sealing, of an earlier one when reverting
    -- and everything below stays readable at its own number, so a
    revert opens one revision rather than sealing first.

    Both take an 'Idempotency-Key', because neither is idempotent in
    itself: sealing twice is two revisions, and reverting twice is
    two.  A seal carries nothing, so the operation is its own
    fingerprint; a revert carries the revision asked for.

    What each does, and the order it does it in, is in
    'star_pass_contract._deciding', shared with the command line
    client.
"""

# Imports - Python Standard Library
from typing import List

# Imports - Third-Party
from fastapi import APIRouter, Header, Path, status

# Imports - Local
from star_pass._reading import read_run_history
from star_pass_contract import (
    IDEMPOTENCY_KEY_HEADER,
    reverted,
    RevisionView,
    RunDetailView,
    sealed,
    to_revision_views
)
from . import _defaults
from ._runs import missing_run, REFUSALS
from ._security import (
    Principal,
    requires,
    SCOPE_RUNS_READ,
    SCOPE_RUNS_WRITE
)
from ._storage import in_the_database

router = APIRouter(tags=[_defaults.API_TAG_RUNS])


@router.get(
    '/runs/{run_id}/revisions',
    summary='List a run\'s revisions, oldest first',
    description=(
        'Every revision of the run, oldest to newest. Only the current '
        'revision changes. Editing and reverting add a new revision, '
        'and do not change earlier revisions.\n\nEach revision '
        'includes the number of changes made while it was current.'
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

    history = await in_the_database(
        lambda connection: read_run_history(
            connection=connection,
            run_id=run_id
        )
    )

    if history is None:
        raise missing_run(run_id=run_id)

    run, revisions = history

    return to_revision_views(run=run, revisions=revisions)


@router.post(
    '/runs/{run_id}/revisions',
    status_code=status.HTTP_201_CREATED,
    summary='Seal the revision being worked in and open the next',
    description=(
        'Saves the run\'s current events as a numbered revision, and '
        'continues editing in a new revision that copies it. The saved '
        'revision does not change, and you may revert to it later.\n\n'
        'Refused for a run with no collected events.\n\nRequires an '
        '`Idempotency-Key` header. A retry with the same key receives '
        'the first answer. A key already used on this run is treated '
        'as a retry.'
    ),
    response_model=RevisionView
)
async def seal_revision(
        run_id: str = Path(
            description='Identifier the run was created with.'
        ),
        idempotency_key: str = Header(
            alias=IDEMPOTENCY_KEY_HEADER,
            min_length=1,
            description=(
                'A value of the caller\'s choosing, unique to this '
                'action. Repeat it when retrying a request whose '
                'answer was lost; choose a new one to seal again.'
            )
        ),
        principal: Principal = requires(SCOPE_RUNS_WRITE)
) -> RevisionView:
    """ Seal the revision a run is working in and open the next one.

        Args:
            run_id (str):
                Identifier of the run to seal.

            idempotency_key (str):
                What the seal is claimed under, so a retry opens no
                second revision.

            principal (Principal):
                Who is sealing it, which the dependency supplies after
                checking the scope.

        Raises:
            HTTPException:
                404 for a run that is not there, 409 for one with
                nothing collected to seal, and 422 for a key already
                carrying another request.

        Returns:
            opened (RevisionView):
                The revision now being worked in.
    """

    return RevisionView.model_validate(
        await in_the_database(
            lambda connection: sealed(
                connection=connection,
                run_id=run_id,
                key=idempotency_key,
                principal_id=principal.id,
                refusals=REFUSALS
            )
        )
    )


@router.post(
    '/runs/{run_id}/revisions/{number}/revert',
    summary='Take the run back to what an earlier revision held',
    description=(
        'Restores the events of an earlier revision by adding a new '
        'revision that copies it. Editing continues in the new '
        'revision.\n\nReverting does not change any other revision. To '
        'undo a revert, revert to the revision that was current before '
        'it.\n\nReverting to revision 1 removes manually added events '
        'and returns them to the run\'s uncollected list.\n\nAnswers '
        'with the full run.\n\nRequires an `Idempotency-Key` header. A '
        'retry with the same key receives the first answer. A key sent '
        'with a different revision number is refused.'
    ),
    response_model=RunDetailView
)
async def revert_revision(
        run_id: str = Path(
            description='Identifier the run was created with.'
        ),
        number: int = Path(
            ge=1,
            description=(
                'Revision to go back to the contents of, as the '
                'revision list reports it.'
            )
        ),
        idempotency_key: str = Header(
            alias=IDEMPOTENCY_KEY_HEADER,
            min_length=1,
            description=(
                'A value of the caller\'s choosing, unique to this '
                'action. Repeat it when retrying a request whose '
                'answer was lost; choose a new one to revert again.'
            )
        ),
        principal: Principal = requires(SCOPE_RUNS_WRITE)
) -> RunDetailView:
    """ Take a run back to what an earlier revision holds.

        Args:
            run_id (str):
                Identifier of the run to take back.

            number (int):
                Which revision to go back to the contents of.

            idempotency_key (str):
                What the revert is claimed under, so a retry opens no
                second revision.

            principal (Principal):
                Who is reverting it, which the dependency supplies
                after checking the scope.

        Raises:
            HTTPException:
                404 for a run that is not there, 409 for a revision
                the run has never had, and 422 for a key already
                carrying a request for another revision.

        Returns:
            run (RunDetailView):
                The run as it now stands.
    """

    return RunDetailView.model_validate(
        await in_the_database(
            lambda connection: reverted(
                connection=connection,
                run_id=run_id,
                number=number,
                key=idempotency_key,
                principal_id=principal.id,
                refusals=REFUSALS
            )
        )
    )
