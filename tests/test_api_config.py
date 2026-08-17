#!/usr/bin/env python3
""" What the service says it was configured with.

    The endpoint reads settings rather than records, so what is worth
    pinning is that each value reaches a caller from the setting it
    belongs to -- a document assembled from constants would answer
    every deployment with the same thing and nothing would say so.
    Each test below therefore changes one setting and reads it back.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
from typing import Any, Callable, Dict

# Imports - Third-Party
import pytest
from fastapi.testclient import TestClient

# Imports - Local
from star_pass_api import _defaults

# Constants
CONFIG_PATH = f'{_defaults.API_VERSION_PREFIX}/config'

# Where the settings are read.  One module reads them for both halves,
# so a test changing what a deployment configured changes them there.
SETTINGS = 'star_pass_contract._views'


@pytest.fixture(name='configured')
def fixture_configured(
    monkeypatch: pytest.MonkeyPatch,
    authenticated_client: TestClient
) -> Callable[..., Dict[str, Any]]:
    """ Return a way to read the configuration with a setting changed. """

    def read(**settings: Any) -> Dict[str, Any]:
        """ Return what the service reports once 'settings' apply. """
        for name, value in settings.items():
            monkeypatch.setattr(f'{SETTINGS}.{name}', value)

        response = authenticated_client.get(CONFIG_PATH)

        assert response.status_code == 200

        return response.json()

    return read


class TestWhatTheServiceReports:
    def test_the_timezone_is_the_one_windows_are_read_in(
        self,
        configured: Callable[..., Dict[str, Any]]
    ) -> None:
        assert configured(
            GCAL_TIMEZONE='America/New_York'
        )['timezone'] == 'America/New_York'

    def test_the_threshold_is_the_configured_one(
        self,
        configured: Callable[..., Dict[str, Any]]
    ) -> None:
        assert configured(
            FUZZY_MATCH_THRESHOLD=55
        )['matchThreshold'] == 55

    def test_the_never_collected_terms_are_the_configured_ones(
        self,
        configured: Callable[..., Dict[str, Any]]
    ) -> None:
        # A tuple in the settings and a list on the wire, because JSON
        # has one of the two.
        assert configured(
            GCAL_PREFIX_FILTERS=('derby daze', 'summer camp')
        )['excludedTitleTerms'] == ['derby daze', 'summer camp']

    def test_a_calendar_reports_what_it_is_searched_for(
        self,
        configured: Callable[..., Dict[str, Any]]
    ) -> None:
        assert configured(
            GCAL_CALENDARS={
                'practices': {
                    'gcal_id': 'a-calendar-identifier',
                    'query_strings': ['officials', 'scrimmage']
                }
            }
        )['calendars'] == [
            {
                'key': 'practices',
                'searchTerms': ['officials', 'scrimmage']
            }
        ]

    def test_an_empty_query_string_is_published_as_it_is_configured(
        self,
        configured: Callable[..., Dict[str, Any]]
    ) -> None:
        # A calendar searched for nothing in particular returns its
        # whole window, so nothing in it can be left out for want of a
        # term.  That is a value the deployment set, and turning it
        # into an absence here would leave a reader unable to tell it
        # from a calendar with no configuration at all.
        answer = configured(
            GCAL_CALENDARS={
                'events': {
                    'gcal_id': 'a-calendar-identifier',
                    'query_strings': ['']
                }
            }
        )

        assert answer['calendars'][0]['searchTerms'] == ['']

    def test_the_calendars_are_reported_in_key_order(
        self,
        configured: Callable[..., Dict[str, Any]]
    ) -> None:
        # What is published is a property of the configuration rather
        # than of the order somebody wrote it down in.
        answer = configured(
            GCAL_CALENDARS={
                'practices': {'gcal_id': 'one', 'query_strings': []},
                'events': {'gcal_id': 'two', 'query_strings': []}
            }
        )

        assert [
            calendar['key'] for calendar in answer['calendars']
        ] == ['events', 'practices']

    def test_no_calendar_identifier_is_published(
        self,
        configured: Callable[..., Dict[str, Any]]
    ) -> None:
        # A client names a calendar by its key.  The identifier is a
        # deployment detail nothing a caller does needs, and it is the
        # only value in these settings that reaches Google.
        identifier = 'a-calendar-identifier-not-to-be-published'
        answer = configured(
            GCAL_CALENDARS={
                'events': {
                    'gcal_id': identifier,
                    'query_strings': ['']
                }
            }
        )

        assert identifier not in str(answer)


class TestWhoMayRead:
    def test_a_caller_without_a_credential_is_refused(
        self,
        client: TestClient
    ) -> None:
        # Nothing here is secret, but the configuration says which
        # calendars exist and how a title is matched, and every
        # endpoint but health requires a credential.
        assert client.get(CONFIG_PATH).status_code == 401

    def test_the_endpoint_declares_the_scope_it_needs(
        self,
        client: TestClient
    ) -> None:
        published = client.get(
            _defaults.API_OPENAPI_PATH
        ).json()['paths'][CONFIG_PATH]['get']

        assert published['security'] == [{'Bearer token': ['config:read']}]


class TestWhatTheEndpointDoesNotDo:
    def test_there_is_no_way_to_write_a_setting(
        self,
        authenticated_client: TestClient
    ) -> None:
        # Read only by decision (D8): a value is changed by changing
        # the environment and restarting, so the service cannot
        # rewrite what it is running on.
        for method in ('post', 'put', 'patch', 'delete'):
            response = getattr(authenticated_client, method)(CONFIG_PATH)

            assert response.status_code == 405, method
