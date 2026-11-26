#!/usr/bin/env python3
""" The shapes a caller sends.

    Separate from the shapes the service answers with, which are in
    '_schemas'.  The two are read at different moments and for
    different reasons -- a request is checked on the way in and a view
    is built on the way out -- and neither reads the other, so the one
    module they shared was one that only ever grew.

    Every one of these inherits 'RequestModel' below, so a caller may
    send either spelling of a field name and a field the service does
    not know is refused rather than dropped.
"""

# Imports - Python Standard Library
from typing import Annotated, List, Optional

# Imports - Third-Party
from pydantic import ConfigDict, Field, StringConstraints

# Imports - Local
from ._schemas import ApiModel


class RequestModel(ApiModel):
    """ The base every shape a caller sends is built on.

        Unknown fields are refused rather than dropped.  A misspelled
        one is otherwise answered with a success and no sign that what
        was asked for did not happen, and the vocabulary is camel-cased
        on the way in, which is where a spelling is easiest to get
        wrong.

        The views in '_schemas' deliberately do not do this.  Changes
        within a version are additive, so a response may grow a field,
        and a schema published as closed would be a promise this
        service is not making.
    """

    model_config = ConfigDict(extra='forbid')


# What a request may carry.  Every bound is well above what the page
# sends, and none of them is absent.
MAX_NAME_LENGTH = 64
MAX_IDENTIFIER_LENGTH = 128
MAX_TIME_LENGTH = 16
MAX_DATE_LENGTH = 32
MAX_TITLE_LENGTH = 1024
MAX_EVENT_IDS = 1000
MAX_OPERATIONS = 100

# An identifier, bounded wherever one appears in a list.
Identifier = Annotated[
    str,
    StringConstraints(max_length=MAX_IDENTIFIER_LENGTH)
]


class WindowRequest(RequestModel):
    """ The days a collection covers. The service reads the dates in its
        own time zone.
    """

    start: str = Field(
        max_length=MAX_DATE_LENGTH,
        description=(
            'First day to cover, as an ISO date. Read in the '
            'server\'s time zone.'
        ),
        examples=['2026-09-01']
    )
    end: str = Field(
        max_length=MAX_DATE_LENGTH,
        description=(
            'Day after the last day to cover, as an ISO date. A '
            'one-day date range is two consecutive dates. The date '
            'range has no length limit.'
        ),
        examples=['2026-10-01']
    )


class CollectRequest(RequestModel):
    """ The calendar and date range to collect. """

    calendar: str = Field(
        max_length=MAX_NAME_LENGTH,
        description=(
            'The configured calendar to read. `GET /v1/config` lists '
            'the configured calendars. A calendar that is not '
            'configured is refused, and the refusal lists the '
            'configured calendars.'
        ),
        examples=['events']
    )
    window: WindowRequest = Field(
        description='The days to cover.'
    )


class RecollectRequest(RequestModel):
    """ The number of changes collecting the run again discards. """

    expected_change_count: int = Field(
        ge=0,
        description=(
            'The number of changes collecting the run again discards, '
            'as `GET /v1/runs/{run_id}/revisions` reports for the '
            'current revision. Collecting a run again discards any '
            'changes made to it since it was collected.\n\nIf the '
            'number does not match, the run is not collected again. '
            'Read the revisions again, then send the current number.'
        ),
        examples=[0]
    )


class UnmatchedTitleRequest(RequestModel):
    """ A title the data model did not match, to record in the unmatched
        title log.
    """

    calendar: str = Field(
        max_length=MAX_NAME_LENGTH,
        description=(
            'The configured calendar the title was seen in. A title '
            'may match in one calendar and not in another.'
        ),
        examples=['events']
    )
    title: str = Field(
        min_length=1,
        max_length=MAX_TITLE_LENGTH,
        description='The title, exactly as the calendar gave it.',
        examples=['Jet City vs Cherry City']
    )
    run_id: Optional[str] = Field(
        default=None,
        max_length=MAX_IDENTIFIER_LENGTH,
        description=(
            'The run the title was found in, if any. Any unmatched '
            'titles from a run remain in the log after the run is '
            'deleted.'
        ),
        examples=['3f2b1c...']
    )


class SendRequest(RequestModel):
    """ The number of shifts the preview reported a send would create. """

    expected_shift_count: int = Field(
        ge=0,
        description=(
            'The number of shifts the preview reports a send would '
            'create: `totals.willCreate`. It does not include shifts '
            'already in Amplify.\n\nIf there are changes to the run or '
            'Amplify shifts after the preview, the send is refused. '
            'Read the preview again, then send the current number.'
        ),
        examples=[12]
    )

    def fingerprint(self) -> str:
        """ Return what this request asks for, as a key remembers it.

            Compared when a request arrives on a key already in use.
            Built here rather than by each half, so that one of them
            cannot decide two requests are the same while the other
            decides they differ.

            Args:
                None.

            Returns:
                fingerprint (str):
                    What the request asked for.
        """

        return f'expected_shift_count={self.expected_shift_count}'


class EventOperationRequest(RequestModel):
    """ One operation, applied to one or more events. """

    op: str = Field(
        max_length=MAX_NAME_LENGTH,
        description=(
            'The operation. One of: `set_category`, `unassign`, '
            '`set_start`, `set_end`, `set_slots`, `nudge`, '
            '`reset_slots`, `remove`, `undo`.\n\n`set_start` and '
            '`set_end` set the **shift** times sent to Amplify. `undo` '
            'restores an event\'s collected opportunity, shift times, '
            'and volunteer count.\n\n`unassign` removes an event\'s '
            'opportunity, and is refused for an event whose '
            '`mayUnassign` is false. To create no shift for a matched '
            'event, use `remove`.'
        ),
        examples=['nudge']
    )
    event_ids: List[Identifier] = Field(
        min_length=1,
        max_length=MAX_EVENT_IDS,
        description=(
            'The events this operation applies to. An operation on '
            'several events is one change log entry.'
        ),
        examples=[['gcal-1', 'gcal-2']]
    )
    category: Optional[str] = Field(
        default=None,
        max_length=MAX_NAME_LENGTH,
        description='Category to set, for `set_category`.',
        examples=['adult_game']
    )
    time: Optional[str] = Field(
        default=None,
        max_length=MAX_TIME_LENGTH,
        description=(
            'Time of day to set, for `set_start` and `set_end`, as '
            '`HH:MM` in the league\'s own zone.'
        ),
        examples=['18:15']
    )
    need_id: Optional[str] = Field(
        default=None,
        max_length=MAX_IDENTIFIER_LENGTH,
        description=(
            'The need ID of the role to set, for `set_slots`. Each '
            'role of an event has its own volunteer count.'
        ),
        examples=['879609']
    )
    slots: Optional[int] = Field(
        default=None,
        ge=0,
        description='Volunteers wanted, for `set_slots`.',
        examples=[4]
    )
    minutes: Optional[int] = Field(
        default=None,
        description=(
            'How far to move both shift times, for `nudge`. Negative '
            'moves the shift earlier.'
        ),
        examples=[-15]
    )


class EditRequest(RequestModel):
    """ One user action, as a list of operations. """

    operations: List[EventOperationRequest] = Field(
        min_length=1,
        max_length=MAX_OPERATIONS,
        description=(
            'The operations, in order. Each sees the result of the '
            'previous operation.\n\nThe service applies the entire '
            'list or none of it. If an operation would leave an event '
            'unable to become a correct shift, the service refuses the '
            'request and writes no changes.'
        )
    )

    def fingerprint(self) -> str:
        """ Return the operations this request asks for.

            An edit is claimed on what it does, field by field, so a
            retry carrying a different nudge is a different request
            rather than a replay of the first one.

            Args:
                None.

            Returns:
                fingerprint (str):
                    Every operation, in order, as name and value pairs.
        """

        return '|'.join(
            ','.join(
                f'{name}={value}'
                for name, value in sorted(
                    operation.model_dump(exclude_none=True).items()
                )
            )
            for operation in self.operations
        )


class AddEventRequest(RequestModel):
    """ The uncollected event to add to the run. """

    uncollected_id: str = Field(
        min_length=1,
        max_length=MAX_IDENTIFIER_LENGTH,
        description=(
            'Identifier of the event to add, from the run\'s '
            'uncollected list. Only an event whose `addable` is true '
            'may be added.'
        ),
        examples=['1a2b3c4d5e6f7g8h9i0j']
    )
