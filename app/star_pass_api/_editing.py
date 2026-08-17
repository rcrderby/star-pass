#!/usr/bin/env python3
""" Editing the events in a run's current revision.

    A module of its own rather than another endpoint beside the run
    reads.  This is the endpoint a reviewer uses most -- the review
    screen saves as they work -- and what it needs is its own: the
    idempotency key, the shapes an operation arrives in, and the
    refusals.

    **Answered in the request that asked for it.**  An edit is fast and
    touches only this service's own database, so there is no job to
    watch: the answer carries the revision as it now is and the entries
    the edit wrote.  That is also why the key is worth having.  An edit
    is not idempotent in itself -- a nudge applied twice moves a shift
    twice -- so a retry after a lost answer has to be recognised rather
    than carried out again.

    What the edit does, and the order it does it in, is in
    'star_pass_contract._deciding': the command line client answers the
    same operation from the same database (D2), and the sequence -- the
    run read before the key is claimed, the key claimed before the
    write, the answer recorded after it -- is the decision.
"""

# Imports - Third-Party
from fastapi import APIRouter, Header, Path, status

# Imports - Local
from star_pass_contract import (
    edited,
    EditRefusals,
    EditRequest,
    EditView,
    IDEMPOTENCY_KEY_HEADER
)
from . import _defaults
from ._problems import conflict, unprocessable
from ._runs import missing_run
from ._security import Principal, requires, SCOPE_RUNS_WRITE
from ._storage import read

router = APIRouter(tags=[_defaults.API_TAG_RUNS])

# How this half says no.  A status code belongs to the transport, so
# the shared sequence is given these rather than choosing them.
REFUSALS = EditRefusals(
    missing=missing_run,
    conflict=conflict,
    refuse=unprocessable
)


@router.patch(
    '/runs/{run_id}/events',
    status_code=status.HTTP_200_OK,
    summary='Edit the events in this run\'s current revision',
    description=(
        'One user action, sent as the operations it is made of: set '
        'the opportunity, set a shift start or end, set how many '
        'volunteers one role wants, nudge a selection, put slots back '
        'to usual, remove events, undo an event\'s changes.\n\n'
        'Sent as a list so a bulk action over thirty selected rows is '
        'one request, one log entry and one revision delta rather than '
        'thirty of each. The operations apply in order, each seeing '
        'what the one before it produced.\n\n'
        '**The whole call is applied or none of it is.** An operation '
        'that would leave an event unable to become a correct shift '
        'refuses the request and nothing is written, because a partly '
        'applied action is one the reviewer cannot see the shape of.\n\n'
        '`set_start` and `set_end` name the **shift** times, which are '
        'what reaches Amplify. An event\'s calendar times never move: '
        'they are what the calendar said, and they are what `undo` '
        'works back from.\n\n'
        'Requires an `Idempotency-Key` header. An edit is not '
        'idempotent in itself -- a nudge applied twice moves a shift '
        'twice -- so a retry after a lost answer is given the first '
        'answer rather than being carried out again. A key carrying '
        'different operations is refused rather than answered from the '
        'first request, because a key is a promise that the request is '
        'the one already made.'
    ),
    response_model=EditView
)
async def edit_events(
        asked: EditRequest,
        run_id: str = Path(
            description='Identifier the run was created with.'
        ),
        idempotency_key: str = Header(
            alias=IDEMPOTENCY_KEY_HEADER,
            min_length=1,
            description=(
                'A value of the caller\'s choosing, unique to this '
                'action. Repeat it when retrying a request whose '
                'answer was lost; choose a new one for a new action.'
            )
        ),
        principal: Principal = requires(SCOPE_RUNS_WRITE)
) -> EditView:
    """ Apply one action's operations to a run's current revision.

        Args:
            asked (EditRequest):
                What the reviewer did.

            run_id (str):
                Identifier of the run to edit.

            idempotency_key (str):
                What this action is claimed under (D13, D16).

            principal (Principal):
                The authenticated caller, which the dependency supplies
                after checking the scope.

        Raises:
            HTTPException:
                404 when there is no such run, 409 when an operation
                cannot be applied, 422 when the key carries a different
                request.

        Returns:
            edited (EditView):
                The revision as it now is, and what was logged.
    """

    return EditView.model_validate(
        await read(
            lambda connection: edited(
                connection=connection,
                run_id=run_id,
                asked=asked,
                key=idempotency_key,
                principal_id=principal.id,
                refusals=REFUSALS
            )
        )
    )
