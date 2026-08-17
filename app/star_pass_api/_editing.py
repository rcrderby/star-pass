#!/usr/bin/env python3
""" Changing the events in a run's current revision.

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

    **Pulling an event in needs no key.**  An event the revision
    already holds is refused, so a second arrival of one request finds
    the run holding what it asked for and says so -- which is the
    guard a key would be standing in for, and a stronger one, for the
    reason resuming a job needs no key either.  Both answer with the
    revision as it now is, because the screen that asked is redrawn
    from it.
"""

# Imports - Python Standard Library
import sqlite3

# Imports - Third-Party
from fastapi import APIRouter, Header, Path, status

# Imports - Local
from star_pass._adding import add_event as pull_in
from star_pass._repository import EventRepository, RunRepository
from star_pass_contract import (
    AddEventRequest,
    edited,
    EditRequest,
    EditView,
    IDEMPOTENCY_KEY_HEADER,
    to_edit_view,
    WriteRefusals
)
from . import _defaults
from ._problems import conflict, unprocessable
from ._runs import missing_run
from ._security import Principal, requires, SCOPE_RUNS_WRITE
from ._storage import read

router = APIRouter(tags=[_defaults.API_TAG_RUNS])

# How this half says no.  A status code belongs to the transport, so
# the shared sequence is given these rather than choosing them.
REFUSALS = WriteRefusals(
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


def _pulled_in(
        connection: sqlite3.Connection,
        run_id: str,
        uncollected_id: str,
        principal_id: str
) -> EditView:
    """ Pull an event in and return the revision it joined.

        The whole revision rather than the event that arrived, for the
        reason an edit answers with the whole revision: the figures
        beside a row are answers about the revision as a whole, and
        one more event changes them for rows nobody named.

        Args:
            connection (sqlite3.Connection):
                Connection to write on.

            run_id (str):
                Run whose current revision to add to.

            uncollected_id (str):
                The event to pull in.

            principal_id (str):
                Who pulled it in (D13).

        Raises:
            HTTPException:
                404 when there is no such run.

            ValidationError:
                If the event may not be pulled into this run.

            UpstreamError:
                If an opportunity it names cannot be read.

        Returns:
            added (EditView):
                The revision as it now is, and what was logged.
    """

    added = pull_in(
        connection=connection,
        run_id=run_id,
        event_id=uncollected_id,
        principal_id=principal_id
    )

    if added is None:
        raise missing_run(run_id=run_id)

    _, entry = added
    runs = RunRepository(connection=connection)

    return to_edit_view(
        events=EventRepository(connection=connection).list_all(
            run_id=run_id,
            revision=entry.revision
        ),
        opportunities=runs.get_opportunities(run_id=run_id),
        entries=[entry]
    )


@router.post(
    '/runs/{run_id}/events',
    status_code=status.HTTP_201_CREATED,
    summary='Pull an event the search missed into this run',
    description=(
        'Adds to the run\'s current revision one of the events its '
        'window held and the collection did not take, named by the '
        'identifier the "uncollected" list carries.\n\n'
        '**Only an event nobody searched for may be pulled in.** The '
        'other three reasons -- an excluded title, an all-day event, '
        'an untitled one -- describe events that cannot become a '
        'correct shift, and naming one is refused here rather than '
        'left to a client to avoid. So is naming an event the '
        'revision already holds, which is what makes a second arrival '
        'of one request a refusal rather than a second row: no '
        'idempotency key is needed, for the reason resuming a job '
        'needs none.\n\n'
        'The event that arrives is the one a collection would have '
        'produced, matched to a category and timed the same way. It '
        'is marked as added by hand, because reverting to the first '
        'revision drops the events a person pulled in and returns '
        'them to the uncollected list -- which is why the entry there '
        'is kept rather than deleted.\n\n'
        'The run gains any Amplify opportunity the event names and '
        'the run has not read, so that the row can be labelled. That '
        'is the one upstream request this makes.\n\n'
        'Answers with the revision as it now is, because the screen '
        'that asked is redrawn from it.'
    ),
    response_model=EditView
)
async def add_event(
        asked: AddEventRequest,
        run_id: str = Path(
            description='Identifier the run was created with.'
        ),
        principal: Principal = requires(SCOPE_RUNS_WRITE)
) -> EditView:
    """ Pull one of a run's uncollected events into its revision.

        Args:
            asked (AddEventRequest):
                Which event to pull in.

            run_id (str):
                Identifier of the run to add to.

            principal (Principal):
                The authenticated caller, which the dependency supplies
                after checking the scope.

        Raises:
            HTTPException:
                404 when there is no such run.

            ValidationError:
                If the event may not be pulled into this run, which is
                answered as a 422 carrying the reason.

            UpstreamError:
                If an opportunity it names cannot be read.

        Returns:
            added (EditView):
                The revision as it now is, and what was logged.
    """

    return await read(
        lambda connection: _pulled_in(
            connection=connection,
            run_id=run_id,
            uncollected_id=asked.uncollected_id,
            principal_id=principal.id
        )
    )
