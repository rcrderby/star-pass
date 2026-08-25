#!/usr/bin/env python3
""" Tests for what a run's window held and the run did not collect.

    A module of its own rather than more of 'test_api_runs.py': what a
    run holds and what its window held are two questions, and the
    second is answered from rows the collection stored beside the run
    rather than from the run's own.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
from typing import Callable

# Imports - Third-Party
from fastapi.testclient import TestClient

# Imports - Local
from star_pass._records import UncollectedEvent, UNCOLLECTED_SEARCH
from star_pass._repository import UncollectedRepository
from star_pass_api import _defaults
from star_pass_api._problems import PROBLEM_MEDIA_TYPE


def uncollected_path(run_id: str) -> str:
    """ Return the address of what one run's window left out. """
    return f'{_defaults.API_VERSION_PREFIX}/runs/{run_id}/uncollected'


class TestWhatTheWindowHeldAndTheRunLeftOut:
    def test_the_groups_come_back_in_the_order_the_reasons_are_declared(
        self,
        running_client: TestClient,
        not_collected: Callable[[str], list],
        collected: str
    ) -> None:
        # The one a reviewer can act on comes first, whatever order
        # the rows are stored in.
        not_collected(collected)

        response = running_client.get(uncollected_path(run_id=collected))

        assert response.status_code == 200
        assert [group['reason'] for group in response.json()] == [
            'search',
            'excluded',
            'allday',
            'untitled'
        ]

    def test_a_reason_nothing_was_left_out_for_is_not_published(
        self,
        running_client: TestClient,
        uncollected: UncollectedRepository,
        collected: str
    ) -> None:
        # A reader counting the groups is counting what there is to
        # look at, so an empty one would be a group that is not there.
        uncollected.replace(
            run_id=collected,
            uncollected=[
                UncollectedEvent(id='gcal-1', reason=UNCOLLECTED_SEARCH)
            ]
        )

        listed = running_client.get(
            uncollected_path(run_id=collected)
        ).json()

        assert [group['reason'] for group in listed] == ['search']

    def test_an_event_carries_what_the_calendar_said_about_it(
        self,
        running_client: TestClient,
        not_collected: Callable[[str], list],
        collected: str
    ) -> None:
        not_collected(collected)

        listed = running_client.get(
            uncollected_path(run_id=collected)
        ).json()

        assert listed[0]['events'] == [
            {
                'id': 'gcal-11',
                'title': 'Junior Bout',
                'date': '2026-09-11',
                'calendarStart': '18:00',
                'calendarEnd': '20:00',
                'calendarNote': None,
                'addable': True
            }
        ]

    def test_an_all_day_event_carries_its_day_and_no_times(
        self,
        running_client: TestClient,
        not_collected: Callable[[str], list],
        collected: str
    ) -> None:
        not_collected(collected)

        listed = running_client.get(
            uncollected_path(run_id=collected)
        ).json()
        event = listed[2]['events'][0]

        assert event['date'] == '2026-09-09'
        assert event['calendarStart'] is None
        assert event['calendarEnd'] is None

    def test_only_an_event_nobody_looked_for_may_be_pulled_in(
        self,
        running_client: TestClient,
        not_collected: Callable[[str], list],
        collected: str
    ) -> None:
        # The server's answer rather than the client's, so a button
        # and the endpoint behind it cannot disagree.
        not_collected(collected)

        listed = running_client.get(
            uncollected_path(run_id=collected)
        ).json()

        assert [
            (group['reason'], event['addable'])
            for group in listed
            for event in group['events']
        ] == [
            ('search', True),
            ('excluded', False),
            ('allday', False),
            ('untitled', False)
        ]

    def test_a_run_that_left_nothing_out_reads_as_an_empty_list(
        self,
        running_client: TestClient,
        collected: str
    ) -> None:
        # A run whose window held nothing else is a different fact
        # from a run that does not exist, and reads differently.
        response = running_client.get(uncollected_path(run_id=collected))

        assert response.status_code == 200
        assert response.json() == []

    def test_an_unknown_run_is_not_found(
        self,
        running_client: TestClient
    ) -> None:
        response = running_client.get(
            uncollected_path(run_id='no-such-run')
        )

        assert response.status_code == 404
        assert response.headers['content-type'] == PROBLEM_MEDIA_TYPE
        assert 'no-such-run' in response.json()['detail']

    def test_reading_them_needs_a_credential(
        self,
        anonymous_client: TestClient,
        run_id: str
    ) -> None:
        assert anonymous_client.get(
            uncollected_path(run_id=run_id)
        ).status_code == 401
