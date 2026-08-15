#!/usr/bin/env python3
""" The committed specification describes the service that is running.

    A committed generated file is only worth having while something
    checks it: the drift test below is what makes the file a contract
    rather than a snapshot of whatever the service looked like when
    someone last remembered to run the generator.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
import json

# Imports - Third-Party
from fastapi.testclient import TestClient

# Imports - Local
from star_pass_api import _defaults, _spec
from star_pass_api._security import SCOPES

# Constants
DRIFT_MESSAGE = (
    'The committed specification no longer matches the service. Run '
    f'"{_spec.REGENERATE_COMMAND}" and commit the result.'
)


class TestTheCommittedCopy:
    def test_the_committed_copy_matches_the_service(self) -> None:
        generated = _spec.render(document=_spec.specification())

        assert _spec.committed() == generated, DRIFT_MESSAGE

    def test_the_committed_copy_is_what_the_service_serves(
        self,
        client: TestClient
    ) -> None:
        # The file is the artifact a client is generated from, so it
        # has to be the same document the endpoint hands out.
        served = client.get(_defaults.API_OPENAPI_PATH).json()

        assert json.loads(_spec.committed()) == served

    def test_the_rendering_is_stable(self) -> None:
        # A drift check compares renderings, so the same document has
        # to render the same way twice.
        document = _spec.specification()

        assert _spec.render(document=document) == _spec.render(
            document=_spec.specification()
        )

    def test_the_committed_copy_ends_in_a_newline(self) -> None:
        assert _spec.committed().endswith('\n')


class TestWhatTheSpecificationSays:
    def test_it_is_openapi_3_1(self) -> None:
        assert _spec.specification()['openapi'].startswith('3.1')

    def test_it_carries_the_running_version(self) -> None:
        # Which means a version bump changes this file, deliberately:
        # the contract records which release it describes.
        information = _spec.specification()['info']

        assert information['version'] == _defaults.API_VERSION

    def test_every_scope_the_service_defines_is_reachable(self) -> None:
        # A scope no route declares is one nothing can be granted for,
        # which is a scope that exists only in the source.
        document = _spec.specification()
        declared = {
            scope
            for path in document['paths'].values()
            for operation in path.values()
            for requirement in operation.get('security', ())
            for scopes in requirement.values()
            for scope in scopes
        }

        assert declared <= set(SCOPES)

    def test_generation_needs_no_configured_token(
        self,
        monkeypatch
    ) -> None:
        # The contract describes the shape of the service, not the
        # value it authenticates against, so the generator works on a
        # machine that has no token set.
        monkeypatch.setattr(_defaults, 'API_TOKEN', None)

        assert _spec.specification()['openapi']

    def test_the_placeholder_token_never_reaches_the_document(
        self,
        monkeypatch
    ) -> None:
        monkeypatch.setattr(_defaults, 'API_TOKEN', None)

        assert _spec.PLACEHOLDER_CREDENTIAL not in json.dumps(
            _spec.specification()
        )

    def test_a_configured_token_is_left_as_it_was(
        self,
        api_credential: str
    ) -> None:
        # The generator borrows the setting when it is unset; it must
        # not disturb it when it is set.
        _spec.specification()

        assert _defaults.API_TOKEN == api_credential
