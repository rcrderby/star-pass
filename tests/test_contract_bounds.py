#!/usr/bin/env python3
""" What a request may carry, and what it may not.

    Every string field and every list in the request contract has a
    bound.  They sit well above what the page sends, so the tests here
    check both ends: the bound refuses what is over it, and what the
    page actually sends is nowhere near it.

    A field the contract does not name is refused as well, which is
    the other half of what a request may carry.  The views answer the
    opposite way and a test below holds them to it.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Third-Party
import pytest
from pydantic import ValidationError

# Imports - Local
from star_pass_contract._requests import (
    AddEventRequest,
    CollectRequest,
    EditRequest,
    EventOperationRequest,
    RecollectRequest,
    SendRequest,
    WindowRequest,
    MAX_DATE_LENGTH,
    MAX_EVENT_IDS,
    MAX_IDENTIFIER_LENGTH,
    MAX_NAME_LENGTH,
    MAX_OPERATIONS,
    MAX_TITLE_LENGTH,
    UnmatchedTitleRequest
)
from star_pass_contract._schemas import RunView, WindowView


def an_operation(**fields):
    """ Return one operation, with these fields changed. """
    return {'op': 'nudge', 'eventIds': ['gcal-1'], 'minutes': -15, **fields}


class TestAStringHasALimit:
    def test_a_title_at_the_limit_is_taken(self):
        UnmatchedTitleRequest(
            calendar='events',
            title='x' * MAX_TITLE_LENGTH
        )

    def test_a_title_over_the_limit_is_refused(self):
        with pytest.raises(ValidationError):
            UnmatchedTitleRequest(
                calendar='events',
                title='x' * (MAX_TITLE_LENGTH + 1)
            )

    def test_a_long_calendar_name_is_refused(self):
        with pytest.raises(ValidationError):
            CollectRequest(
                calendar='x' * (MAX_NAME_LENGTH + 1),
                window={'start': '2026-09-01', 'end': '2026-10-01'}
            )

    def test_a_long_date_is_refused(self):
        with pytest.raises(ValidationError):
            CollectRequest(
                calendar='events',
                window={
                    'start': '2' * (MAX_DATE_LENGTH + 1),
                    'end': '2026-10-01'
                }
            )

    def test_a_long_identifier_is_refused(self):
        with pytest.raises(ValidationError):
            AddEventRequest(
                uncollectedId='x' * (MAX_IDENTIFIER_LENGTH + 1)
            )


class TestAListHasALimit:
    def test_too_many_event_ids_are_refused(self):
        with pytest.raises(ValidationError):
            EventOperationRequest(
                **an_operation(eventIds=['g'] * (MAX_EVENT_IDS + 1))
            )

    def test_a_long_event_id_is_refused(self):
        # The list is bounded and so is what it holds: a thousand
        # unbounded strings is unbounded.
        with pytest.raises(ValidationError):
            EventOperationRequest(
                **an_operation(
                    eventIds=['x' * (MAX_IDENTIFIER_LENGTH + 1)]
                )
            )

    def test_too_many_operations_are_refused(self):
        with pytest.raises(ValidationError):
            EditRequest(
                operations=[an_operation()] * (MAX_OPERATIONS + 1)
            )


class TestThePageIsWellInsideThem:
    def test_an_edit_over_a_whole_run_is_taken(self):
        # The page sends one operation naming the selection, so a
        # month of events is one operation and a few hundred ids.
        EditRequest(
            operations=[
                an_operation(
                    eventIds=[f'gcal-{number}' for number in range(300)]
                )
            ]
        )


class TestAFieldTheContractDoesNotName:
    """ A misspelling is refused rather than dropped.

        The vocabulary is camel-cased on the way in, which is where a
        spelling is easiest to get wrong, and a dropped field is
        answered with a success and no sign that what was asked for
        did not happen.
    """

    def test_an_unknown_field_is_refused(self):
        with pytest.raises(ValidationError):
            UnmatchedTitleRequest(
                calendar='events',
                title='Adult Scrimmage',
                notAField='anything'
            )

    def test_a_misspelled_field_is_refused(self):
        # 'startInDays' for 'start', say: near enough to be a typo and
        # far enough to mean nothing.
        with pytest.raises(ValidationError):
            WindowRequest(
                start='2026-09-01',
                end='2026-10-01',
                startInDays=1
            )

    @pytest.mark.parametrize(
        'shape, fields',
        [
            (CollectRequest, {
                'calendar': 'events',
                'window': {'start': '2026-09-01', 'end': '2026-10-01'}
            }),
            (RecollectRequest, {'expectedChangeCount': 0}),
            (SendRequest, {'expectedShiftCount': 1}),
            (EditRequest, {'operations': [an_operation()]}),
            (AddEventRequest, {'uncollectedId': 'gcal-1'})
        ]
    )
    def test_every_request_shape_refuses_one(self, shape, fields):
        # Named per shape rather than trusted to the base class, so a
        # request that stopped inheriting it fails here.
        with pytest.raises(ValidationError):
            shape(**fields, notAField='anything')

    def test_the_operation_inside_an_edit_refuses_one(self):
        # The nested shape as well, which is where the vocabulary is
        # densest.
        with pytest.raises(ValidationError):
            EventOperationRequest(**an_operation(notAField='anything'))


class TestAViewStaysOpen:
    """ The answer shapes deliberately do not refuse an extra field.

        Changes within a version are additive, so a response may grow
        one.  A view published as closed would be a promise this
        service is not making, and a generated client validating
        against it would break on the first field added.
    """

    def test_a_view_takes_a_field_it_does_not_name(self):
        WindowView(
            start='2026-09-01',
            end='2026-10-01',
            lastDay='2026-09-30',
            timezone='America/Los_Angeles',
            somethingAddedLater='a value'
        )

    def test_the_base_view_is_open_too(self):
        assert RunView.model_config.get('extra') != 'forbid'
