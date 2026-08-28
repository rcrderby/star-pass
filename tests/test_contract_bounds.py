#!/usr/bin/env python3
""" What a request may carry.

    Every string field and every list in the request contract has a
    bound.  They sit well above what the page sends, so the tests here
    check both ends: the bound refuses what is over it, and what the
    page actually sends is nowhere near it.
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
    MAX_DATE_LENGTH,
    MAX_EVENT_IDS,
    MAX_IDENTIFIER_LENGTH,
    MAX_NAME_LENGTH,
    MAX_OPERATIONS,
    MAX_TITLE_LENGTH,
    UnmatchedTitleRequest
)


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
