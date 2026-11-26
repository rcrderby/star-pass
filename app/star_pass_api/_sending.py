#!/usr/bin/env python3
""" Putting a run's shifts into Amplify.

    A module of its own rather than another endpoint beside the run
    reads.  This is the only write in the service that cannot be
    undone, and everything it needs -- the idempotency key, the two
    checks against what Amplify already holds, the refusals -- is here
    rather than mixed in with reading a run.

    **Checked twice, as the plan asks.**  Once here, before a job
    exists, so a caller who cannot send is told why in the answer to
    their own request; and once in the core, against each opportunity
    immediately before the request that writes to it.  The count the
    caller confirmed against is checked against the first of those.

    The key and the check do different jobs and neither replaces the
    other.  The key stops one request being carried out twice; the
    live read stops a row being created twice, whoever created it the
    first time.
"""

# Imports - Third-Party
from fastapi import APIRouter, Header, Path, Request, status

# Imports - Local
from star_pass._records import JOB_KIND_SEND
from star_pass._reporting import Reporter
from star_pass._repository import IdempotencyRepository, JobRepository
from star_pass._send import claim, send
from star_pass_contract import (
    IDEMPOTENCY_KEY_HEADER,
    JobView,
    replayed,
    sendable,
    SendRequest,
    to_job_view
)
from . import _defaults
from ._problems import conflict, unprocessable
from ._runs import missing_run
from ._security import Principal, requires, SCOPE_SEND_EXECUTE
from ._storage import in_database, in_the_database

router = APIRouter(tags=[_defaults.API_TAG_RUNS])


async def _handed_over(
        request: Request,
        job_id: str,
        run_id: str,
        principal_id: str,
        key: str
) -> JobView:
    """ Give the sending to the runner and answer with the job.

        The answer is recorded against the key before it is returned,
        so a retry arriving after this point is given this job rather
        than starting another.

        Args:
            request (Request):
                The request, which carries the runner.

            job_id (str):
                Job the work is recorded against, already queued.

            run_id (str):
                Run to send.

            principal_id (str):
                Who asked.

            key (str):
                The key the send is made under.

        Returns:
            job (JobView):
                The job, as it stands when the answer is sent.
    """

    def work(reporter: Reporter) -> None:
        """ Send, on a connection belonging to the job's thread. """
        in_database(
            lambda connection: send(
                connection=connection,
                run_id=run_id,
                reporter=reporter,
                principal_id=principal_id,
                idempotency_key=key
            )
        )

    request.app.state.runner.submit(job_id=job_id, work=work)

    job = to_job_view(
        job=await in_the_database(
            lambda connection: JobRepository(
                connection=connection
            ).get(job_id=job_id)
        )
    )

    await in_the_database(
        lambda connection: IdempotencyRepository(
            connection=connection
        ).complete(
            operation=JOB_KIND_SEND,
            key=key,
            status_code=status.HTTP_202_ACCEPTED,
            response=job.model_dump(by_alias=True, mode='json')
        )
    )

    return job


@router.post(
    '/runs/{run_id}/send',
    status_code=status.HTTP_202_ACCEPTED,
    summary='Create this run\'s shifts in Amplify',
    description=(
        'Creates every shift in the run\'s current revision that '
        'Amplify does not have. **Sending creates shifts in Amplify, '
        'and it may not be undone.**\n\nSet `expectedShiftCount` to '
        'the preview\'s `totals.willCreate`. If there are changes to '
        'the run or Amplify shifts after the preview, the send is '
        'refused. Read the preview again to see the current number of '
        'shifts.\n\nRequires an `Idempotency-Key` header. A retry with '
        'the same key receives the first answer. A key sent with a '
        'different `expectedShiftCount` is refused.\n\nBefore writing '
        'to each opportunity, the service reads the opportunity from '
        'Amplify and skips the shifts it already has. The service '
        'sends one request per opportunity. If a request\'s answer '
        'does not arrive, the run is `partly_sent`, and sending again '
        'creates only the missing shifts.\n\nAnswers when the job is '
        'created.\n\nYou may not send a run while another job is '
        'working on it, while it is being collected, or while any '
        'event in it is blocking.'
    ),
    response_model=JobView
)
async def send_run(
        request: Request,
        sending: SendRequest,
        run_id: str = Path(
            description='Identifier the run was created with.'
        ),
        idempotency_key: str = Header(
            alias=IDEMPOTENCY_KEY_HEADER,
            min_length=1,
            description=(
                'A value of the caller\'s choosing, unique to this '
                'attempt to send this run. Repeat it when retrying a '
                'request whose answer was lost; choose a new one when '
                'asking for something different.'
            )
        ),
        principal: Principal = requires(SCOPE_SEND_EXECUTE)
) -> JobView:
    """ Send a run's outstanding shifts to Amplify.

        Args:
            request (Request):
                The request, which carries the runner that jobs are
                given to.

            sending (SendRequest):
                How many shifts the operator was told would be created.

            run_id (str):
                Identifier of the run to send.

            idempotency_key (str):
                What this attempt is claimed under.

            principal (Principal):
                The authenticated caller, which the dependency supplies
                after checking the scope.

        Raises:
            HTTPException:
                404 when there is no such run, 409 when the run is not
                one that may be sent, 422 when the key carries a
                different request.

        Returns:
            job (JobView):
                The job sending the run, queued.
    """

    found = await in_the_database(
        lambda connection: sendable(
            connection=connection,
            run_id=run_id,
            expected=sending.expected_shift_count
        )
    )

    if found is None:
        raise missing_run(run_id=run_id)

    run, refusal = found

    if refusal is not None:
        raise conflict(detail=refusal)

    existing, job = await in_the_database(
        lambda connection: claim(
            connection=connection,
            run_id=run.id,
            key=idempotency_key,
            fingerprint=sending.fingerprint(),
            principal_id=principal.id
        )
    )

    if existing is not None:
        return JobView.model_validate(
            replayed(
                record=existing,
                run_id=run.id,
                fingerprint=sending.fingerprint(),
                refuse=unprocessable,
                conflict=conflict
            )
        )

    return await _handed_over(
        request=request,
        job_id=job.id,
        run_id=run.id,
        principal_id=principal.id,
        key=idempotency_key
    )
