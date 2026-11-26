#!/usr/bin/env python3
""" Changing the events in a run's current revision.

    A module of its own rather than another endpoint beside the run
    reads: the idempotency key, the shapes an operation arrives in,
    and the refusals are its own.  An edit is answered in the request
    that asked for it, because it touches only this service's own
    database, so there is no job to watch.  The key is worth having
    because an edit is not idempotent -- a nudge applied twice moves a
    shift twice -- so a retry after a lost answer is recognised rather
    than carried out again.

    What the edit does, and the order it does it in, is in
    'star_pass_contract._deciding', shared with the command line
    client: the run read before the key is claimed, the key claimed
    before the write, the answer recorded after it.

    Pulling an event in needs no key: an event the revision already
    holds is refused, so a second arrival of one request is answered
    by the refusal.
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
from ._storage import in_the_database

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
        'One user action, as a list of operations: set the category, '
        'set a shift start or end, set a role\'s volunteer count, '
        'nudge, reset volunteer counts, remove events, or undo an '
        'event\'s changes.\n\nAn action over several rows is one '
        'request, one change log entry, and one revision change. The '
        'operations apply in order, and each sees the result of the '
        'previous operation.\n\n**The service applies the entire '
        'request or none of it.** If an operation would leave an event '
        'unable to become a correct shift, the service refuses the '
        'request and writes no changes.\n\n`set_start` and `set_end` '
        'set the **shift** times sent to Amplify. `undo` restores an '
        'event\'s collected opportunity, shift times, and volunteer '
        'count.\n\nRequires an `Idempotency-Key` header. A retry with '
        'the same key receives the first answer. A key sent with '
        'different operations is refused.'
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
                What this action is claimed under.

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
        await in_the_database(
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
                Who pulled it in.

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
    run = runs.get(run_id=run_id)

    # The event was pulled into this run on this connection a moment
    # ago, so the run is there; read for the calendar, which is what
    # the data model is looked up under to say what has been edited.
    if run is None:
        raise missing_run(run_id=run_id)

    return to_edit_view(
        events=EventRepository(connection=connection).list_all(
            run_id=run_id,
            revision=entry.revision
        ),
        entries=[entry],
        calendar=run.calendar
    )


@router.post(
    '/runs/{run_id}/events',
    status_code=status.HTTP_201_CREATED,
    summary='Pull an event the search missed into this run',
    description=(
        'Adds an uncollected event to the run\'s current revision, by '
        'its identifier in the run\'s uncollected list.\n\n**Only an '
        'event with the `search` reason may be added**: an event no '
        'search term returned. Events excluded by title, all-day '
        'events, and untitled events are refused. An event already in '
        'the revision is also refused, so a repeated request does not '
        'add a duplicate row.\n\nThe added event is matched and timed '
        'the same way a collected event is, and is marked as manually '
        'added. Reverting to revision 1 removes the event and returns '
        'it to the uncollected list.\n\nIf the event has an Amplify '
        'opportunity the run has not read, the service reads its title '
        'from Amplify.\n\nAnswers with the current revision.'
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

    return await in_the_database(
        lambda connection: _pulled_in(
            connection=connection,
            run_id=run_id,
            uncollected_id=asked.uncollected_id,
            principal_id=principal.id
        )
    )
