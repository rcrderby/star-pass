#!/usr/bin/env python3
""" Asking the service what the data model has not matched.

    What the log does is pinned in 'test_unmatched_repository.py'.
    These tests ask what the endpoints add: that a sighting is
    recorded under a calendar the deployment actually reads, that the
    answer carries the count rather than the row, and that reading the
    log needs no run to exist.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
from pathlib import Path
from typing import Any, Callable, Dict, List

# Imports - Third-Party
import pytest
from fastapi.testclient import TestClient

# Imports - Local
from star_pass_api import _defaults
from star_pass_api._problems import PROBLEM_MEDIA_TYPE

# Constants
UNMATCHED_PATH = f'{_defaults.API_VERSION_PREFIX}/unmatched-titles'

# A title the model has no alias for, in a calendar the test
# deployment configures.
TITLE = 'Jet City vs Cherry City'
CALENDAR = 'events'


@pytest.fixture(name='record')
def fixture_record(
    authenticated_client: TestClient,
    service_database: Path
) -> Callable[..., Any]:
    """ Return a way to record one sighting of a title. """
    del service_database

    def send(**overrides: Any) -> Any:
        """ Ask, and return what the service answered. """
        body: dict = {'calendar': CALENDAR, 'title': TITLE}
        body.update(overrides)

        return authenticated_client.post(UNMATCHED_PATH, json=body)

    return send


@pytest.fixture(name='listed')
def fixture_listed(
    authenticated_client: TestClient,
    service_database: Path
) -> Callable[[], List[Dict[str, Any]]]:
    """ Return a way to read the log. """
    del service_database

    def read() -> List[Dict[str, Any]]:
        """ Read it, failing the test if it was refused. """
        response = authenticated_client.get(UNMATCHED_PATH)

        assert response.status_code == 200

        return response.json()

    return read


class TestRecordingATitle:
    def test_the_entry_is_reported_as_created(
        self,
        record: Callable[..., Any]
    ) -> None:
        answer = record()

        assert answer.status_code == 201
        assert answer.json()['title'] == TITLE

    def test_the_answer_counts_the_sightings(
        self,
        record: Callable[..., Any]
    ) -> None:
        # Which is what a reader of the log is scanning for, so the
        # screen that recorded one can show it without asking again.
        record()

        assert record().json()['timesSeen'] == 2

    def test_the_same_title_twice_stays_one_entry(
        self,
        listed: Callable[[], List[Dict[str, Any]]],
        record: Callable[..., Any]
    ) -> None:
        record()
        record()

        assert len(listed()) == 1

    def test_a_run_may_be_named_as_where_it_was_noticed(
        self,
        collected: str,
        record: Callable[..., Any]
    ) -> None:
        assert record(runId=collected).status_code == 201


class TestWhatIsRefused:
    def test_a_calendar_the_service_does_not_read(
        self,
        record: Callable[..., Any]
    ) -> None:
        # Allowlisted from the configuration rather than taken as free
        # text, and the refusal names the ones that are configured.
        answer = record(calendar='not-a-calendar')

        assert answer.status_code == 422
        assert answer.headers['content-type'] == PROBLEM_MEDIA_TYPE
        assert CALENDAR in answer.json()['detail']

    def test_an_empty_title(
        self,
        record: Callable[..., Any]
    ) -> None:
        assert record(title='').status_code == 422

    def test_a_refused_sighting_is_not_recorded(
        self,
        listed: Callable[[], List[Dict[str, Any]]],
        record: Callable[..., Any]
    ) -> None:
        record(calendar='not-a-calendar')

        assert listed() == []


class TestReadingTheLog:
    def test_an_empty_log_reads_as_nothing(
        self,
        listed: Callable[[], List[Dict[str, Any]]]
    ) -> None:
        # A database with no runs in it answers, because the log
        # belongs to no run.
        assert listed() == []

    def test_every_title_is_listed_with_where_it_was_seen(
        self,
        listed: Callable[[], List[Dict[str, Any]]],
        record: Callable[..., Any]
    ) -> None:
        record()

        entry = listed()[0]

        assert entry['calendar'] == CALENDAR
        assert entry['timesSeen'] == 1
        assert entry['firstSeen'] == entry['lastSeen']


class TestWhoMayAsk:
    def test_a_caller_without_a_credential_may_not_read(
        self,
        anonymous_client: TestClient
    ) -> None:
        assert anonymous_client.get(UNMATCHED_PATH).status_code == 401

    def test_a_caller_without_a_credential_may_not_record(
        self,
        anonymous_client: TestClient
    ) -> None:
        response = anonymous_client.post(
            UNMATCHED_PATH,
            json={'calendar': CALENDAR, 'title': TITLE}
        )

        assert response.status_code == 401

    def test_reading_takes_the_scope_settings_are_read_under(
        self,
        client: TestClient
    ) -> None:
        published = client.get(
            _defaults.API_OPENAPI_PATH
        ).json()['paths'][UNMATCHED_PATH]['get']

        assert published['security'] == [{'Bearer token': ['config:read']}]

    def test_recording_takes_a_write_scope(
        self,
        client: TestClient
    ) -> None:
        # It writes something durable, even though it writes nothing
        # about a run.
        published = client.get(
            _defaults.API_OPENAPI_PATH
        ).json()['paths'][UNMATCHED_PATH]['post']

        assert published['security'] == [{'Bearer token': ['runs:write']}]
