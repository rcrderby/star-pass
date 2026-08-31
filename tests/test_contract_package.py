#!/usr/bin/env python3
""" The contract shapes cost a client nothing but the shapes.

    The command line client calls the core in-process by default and
    must not acquire a server as a dependency to do it.  It also
    has to answer with exactly what the service answers, which means
    using the service's shapes -- so those shapes cannot live in the
    package that builds the service, because importing anything from
    there runs its '__init__' and pulls in the web framework.

    The test below is what keeps that true.  It is import hygiene, so
    it is checked by importing rather than by reading, and it runs in
    a subprocess: this suite has already imported the service by the
    time it gets here, and a check inside the process would pass on
    somebody else's import.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Local
from _importing import imported_modules

# Constants
# What a client must not acquire by asking for the contract's shapes.
SERVER_MODULES = ('fastapi', 'starlette', 'uvicorn')


class TestWhatTheContractDragsIn:
    def test_the_shapes_do_not_import_the_web_framework(self) -> None:
        loaded = imported_modules(statement='import star_pass_contract')

        assert not set(loaded) & set(SERVER_MODULES)

    def test_the_shapes_are_usable_on_their_own(self) -> None:
        # A negative test alone would pass on a name that no longer
        # imports because it no longer exists.
        loaded = imported_modules(
            statement=(
                'from star_pass_contract import to_run_view, RunView\n'
                'assert to_run_view is not None and RunView is not None'
            )
        )

        assert 'star_pass_contract' in loaded
        assert 'pydantic' in loaded

    def test_the_service_package_does_import_it(self) -> None:
        # The comparison that gives the first test its meaning: the
        # framework is absent from the contract because the contract
        # does not need it, not because nothing here imports it.
        loaded = imported_modules(statement='import star_pass_api')

        assert 'fastapi' in loaded
