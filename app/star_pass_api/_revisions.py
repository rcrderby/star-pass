#!/usr/bin/env python3
""" The numbered versions of a run's events, and moving between them.

    Its own module rather than three more endpoints beside the run
    reads, because what a revision is for is its own subject: reading
    them is history, and the two writes are the pair that makes the
    history worth keeping.  Sealing fixes what the run holds now as
    something to come back to; reverting is coming back to it.

    **Neither destroys anything, so neither has to.**  Each adds a
    revision holding a copy -- of the current one when sealing, of an
    earlier one when reverting -- and everything below stays readable
    at its own number.  That is why a revert opens **one** revision:
    the revision it leaves is already safe, so sealing it first would
    only add a revision holding an identical copy of the one before
    it.

    Both take an 'Idempotency-Key', because neither is idempotent in
    itself: sealing twice is two revisions, and reverting twice is
    two.  What the key remembers differs, and that is the whole
    difference between them as requests -- a seal carries nothing, so
    the operation is its own fingerprint, while a revert carries the
    revision asked for.

    What each does, and the order it does it in, is in
    'star_pass_contract._deciding': the command line client answers
    from the same database (D2), and the sequence is the decision.
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
        'Fixes what the run holds now as a numbered revision and '
        'moves the work to a new one holding a copy of it. Editing '
        'changes the revision a run is working in as it goes, so this '
        'is what makes a point in that work something to come back '
        'to.\n\n'
        'Nothing is deleted and nothing is lost: the revision that '
        'was current keeps its rows and stays readable at its own '
        'number, which is what reverting to it later reads.\n\n'
        'A run that has collected nothing is refused. The first '
        'revision belongs to the collection, which labels it for what '
        'filled it.\n\n'
        'Requires an `Idempotency-Key` header. Sealing is not '
        'idempotent in itself -- twice is two revisions -- so a retry '
        'after a lost answer is given the first answer rather than '
        'opening a second one. The request carries nothing else, so a '
        'key already used on this run is a replay whatever it is sent '
        'with.'
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
                second revision (D13, D16).

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
        'Puts the run back to the events one of its earlier '
        'revisions holds, by adding a revision holding a copy of '
        'that one. The work carries on there.\n\n'
        'One revision per revert, and nothing between the two is '
        'touched: every revision the run has been through stays '
        'readable at its own number, so a revert can itself be '
        'reverted by going back to the revision that was current '
        'before it.\n\n'
        'Reverting to revision 1 also drops the events somebody '
        'pulled in by hand, because revision 1 is the run as the '
        'calendar gave it. Those events return to the list of what '
        'the collection left out, ready to be pulled in again -- the '
        'rows describing them were never deleted.\n\n'
        'Answers with the run in full, because every row on the '
        'screen that asked has changed.\n\n'
        'Requires an `Idempotency-Key` header. Reverting twice is two '
        'revisions, so a retry after a lost answer is given the first '
        'answer rather than opening a second one. The key remembers '
        'which revision was asked for: sent again naming a different '
        'one, it is refused rather than answered from the first.'
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
                second revision (D13, D16).

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
