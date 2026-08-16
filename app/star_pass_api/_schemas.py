#!/usr/bin/env python3
""" The shapes the service sends and receives.

    Separate from the core's records: those describe what is stored,
    these describe what crosses the wire, and the two are allowed to
    differ.  A stored record can gain a column the contract does not
    publish, and the contract can rename a field without rewriting the
    database.

    Field names are camel case on the wire and snake case in Python.
    The contract is read by a browser and by generated clients, where
    camel case is the convention; the alias generator does the
    translation once here rather than at each field.
"""

# Imports - Third-Party
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

# Imports - Local
from star_pass._records import JOB_KINDS, JOB_STATUSES


class ApiModel(BaseModel):
    """ The base every shape the service publishes is built on. """

    model_config = ConfigDict(
        alias_generator=to_camel,
        # A caller may send either spelling; the service only ever
        # sends the alias.
        populate_by_name=True
    )


class JobView(ApiModel):
    """ A long operation, as a caller sees it. """

    id: str = Field(
        description='Identifier the job is addressed by.'
    )
    run_id: str = Field(
        description='Run the job is working on.'
    )
    kind: str = Field(
        description=f'What it is doing: {", ".join(JOB_KINDS)}.'
    )
    status: str = Field(
        description=(
            f'Where it is: {", ".join(JOB_STATUSES)}. "interrupted" '
            'means the service stopped while it was in hand, so how '
            'far it got is unknown; resuming one is a deliberate '
            'action, never automatic.'
        )
    )
    created_at: str = Field(
        description='When it was asked for, as an ISO-8601 UTC time.'
    )
    started_at: str | None = Field(
        default=None,
        description='When it began, or null while it is queued.'
    )
    finished_at: str | None = Field(
        default=None,
        description='When it stopped, or null while it has not.'
    )
    detail: str | None = Field(
        default=None,
        description=(
            'Why it failed, when it did and when the reason is one a '
            'caller can act on. A failure the service did not expect '
            'says so without its reason, which is in the service log '
            'against the job.'
        )
    )
