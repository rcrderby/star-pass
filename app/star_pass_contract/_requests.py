#!/usr/bin/env python3
""" The shapes a caller sends.

    Separate from the shapes the service answers with, which are in
    '_schemas'.  The two are read at different moments and for
    different reasons -- a request is checked on the way in and a view
    is built on the way out -- and neither reads the other, so the one
    module they shared was one that only ever grew.

    Every one of these inherits 'ApiModel', so a caller may send
    either spelling of a field name and the service publishes the camel
    case one.
"""

# Imports - Python Standard Library
from typing import List, Optional

# Imports - Third-Party
from pydantic import Field

# Imports - Local
from ._schemas import ApiModel


class WindowRequest(ApiModel):
    """ The days a collection is asked to cover.

        No zone, unlike the window a run answers with.  The server's
        zone is the authoritative one, and a client that sent its own
        would be deciding which days a run covers from wherever the
        person happened to be sitting (D16).
    """

    start: str = Field(
        description=(
            'First day to cover, as an ISO date. Read in the '
            'server\'s time zone.'
        ),
        examples=['2026-09-01']
    )
    end: str = Field(
        description=(
            'Day after the last day to cover, as an ISO date. '
            'Exclusive, so a one-day window is two consecutive dates. '
            'There is no limit on how long a window may be.'
        ),
        examples=['2026-10-01']
    )


class CollectRequest(ApiModel):
    """ Which calendar to collect, and over which days. """

    calendar: str = Field(
        description=(
            'Which configured calendar to read. One the deployment '
            'has configured; the names are not part of this contract, '
            'because they are a property of a deployment rather than '
            'of the API. A name that is not configured is refused, '
            'and the refusal lists the ones that are.'
        ),
        examples=['events']
    )
    window: WindowRequest = Field(
        description='The days to cover.'
    )


class RecollectRequest(ApiModel):
    """ What the operator was shown before asking to collect again. """

    expected_change_count: int = Field(
        ge=0,
        description=(
            'How many changes the operator was told a recollection '
            'would discard. Collecting again replaces the run\'s '
            'events with what the calendar has now, so any editing '
            'done since it was collected is left behind in the '
            'revision it was done in.\n\n'
            'The service refuses when this does not match what the '
            'run actually holds. That is the stale-tab case: a number '
            'read from a page somebody left open describes a run that '
            'has moved on, and a confirmation dialog cannot tell the '
            'difference. Read the run again and ask again with what '
            'it says now.'
        ),
        examples=[0]
    )


class SendRequest(ApiModel):
    """ What the operator was shown before asking to send. """

    expected_shift_count: int = Field(
        ge=0,
        description=(
            'How many shifts the operator was told a send would '
            'create. This is the preview\'s `totals.willCreate`, which '
            'is net of what Amplify already holds -- the number of '
            'rows that will arrive, and so the number the confirmation '
            'restates.\n\n'
            'The service refuses when this does not match what a send '
            'would create now. Two things move it: the run being '
            'edited, and Amplify itself gaining or losing a shift. '
            'Both mean the number somebody confirmed against described '
            'a moment that has passed. Read the preview again and ask '
            'again with what it says now.'
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


class EventOperationRequest(ApiModel):
    """ One thing a reviewer did, over one or more events. """

    op: str = Field(
        description=(
            'What was done. One of: `set_category`, `set_start`, '
            '`set_end`, `set_slots`, `nudge`, `reset_slots`, `remove`, '
            '`undo`.\n\n'
            '`set_start` and `set_end` name the **shift** times, which '
            'are what reaches Amplify. An event\'s calendar times '
            'never move: they are what the calendar said, and they are '
            'what `undo` works back from.'
        ),
        examples=['nudge']
    )
    event_ids: List[str] = Field(
        min_length=1,
        description=(
            'The events this applies to. A selection of thirty rows is '
            'one operation naming thirty, which is one log entry '
            'rather than thirty.'
        ),
        examples=[['gcal-1', 'gcal-2']]
    )
    category: Optional[str] = Field(
        default=None,
        description='Category to set, for `set_category`.',
        examples=['adult_game']
    )
    time: Optional[str] = Field(
        default=None,
        description=(
            'Time of day to set, for `set_start` and `set_end`, as '
            '`HH:MM` in the league\'s own zone.'
        ),
        examples=['18:15']
    )
    need_id: Optional[str] = Field(
        default=None,
        description=(
            'Which of an event\'s roles to set, for `set_slots`. A '
            'role rather than the event, because an event serving '
            'skating and non-skating officials wants different '
            'numbers of each.'
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


class EditRequest(ApiModel):
    """ One user action, as the operations it is made of. """

    operations: List[EventOperationRequest] = Field(
        min_length=1,
        description=(
            'What to do, in order. Each one sees what the one before '
            'it produced.\n\n'
            'The whole list is applied or none of it is: an operation '
            'that would leave an event unable to become a correct '
            'shift refuses the call, and nothing is written. A partly '
            'applied action is worse than a refused one, because the '
            'reviewer cannot see which rows moved.'
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


class AddEventRequest(ApiModel):
    """ Which of the events nobody searched for to pull into the run. """

    uncollected_id: str = Field(
        min_length=1,
        description=(
            'Identifier of the event to pull in, as the run\'s record '
            'of what it did not collect carries it. Only an event '
            'that record marks addable may be named: the other '
            'reasons describe events that cannot become a correct '
            'shift, and naming one is refused here rather than left '
            'to a client to avoid.'
        ),
        examples=['1a2b3c4d5e6f7g8h9i0j']
    )
