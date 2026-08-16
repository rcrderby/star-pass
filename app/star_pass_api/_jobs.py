#!/usr/bin/env python3
""" Reading a job.

    A caller that asked for something long was given an identifier
    rather than made to wait.  This is where they come back with it.
"""

# Imports - Python Standard Library
import sqlite3
from typing import Optional

# Imports - Third-Party
from fastapi import APIRouter, HTTPException, Path, status

# Imports - Local
from star_pass._records import Job
from star_pass._repository import JobRepository
from . import _defaults
from ._schemas import JobView
from ._security import Principal, requires, SCOPE_RUNS_READ
from ._storage import read

router = APIRouter(tags=[_defaults.API_TAG_JOBS])


def _find(
        connection: sqlite3.Connection,
        job_id: str
) -> Optional[Job]:
    """ Read one job.

        Args:
            connection (sqlite3.Connection):
                Connection to read on.

            job_id (str):
                Job to read.

        Returns:
            job (Job | None):
                The job, or None when there is no such job.
    """

    return JobRepository(connection=connection).get(job_id=job_id)


@router.get(
    '/jobs/{job_id}',
    summary='Report where a job has got to',
    description=(
        'Answers for a job whether it is queued, running or over. A '
        'caller watching one polls this, or reads the event stream '
        'for the same job to be told as it happens.'
    ),
    response_model=JobView
)
async def get_job(
        job_id: str = Path(
            description='Identifier the job was created with.'
        ),
        principal: Principal = requires(SCOPE_RUNS_READ)
) -> JobView:
    """ Return one job.

        Args:
            job_id (str):
                Identifier of the job to read.

            principal (Principal):
                The authenticated caller, which the dependency supplies
                after checking the scope.

        Raises:
            HTTPException:
                404 when there is no such job.  Raised here rather than
                left to the repository, which reports a value it cannot
                use and a missing job the same way; only this endpoint
                knows it was asked for one by identifier.

        Returns:
            job (JobView):
                The job as a caller sees it.
    """

    del principal

    job = await read(
        lambda connection: _find(
            connection=connection,
            job_id=job_id
        )
    )

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f'There is no job with the ID "{job_id}".'
        )

    return JobView(
        id=job.id,
        run_id=job.run_id,
        kind=job.kind,
        status=job.status,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        detail=job.detail
    )
