#!/usr/bin/env python3
""" The contract shapes cost a client nothing but the shapes.

    The command line client calls the core in-process by default and
    must not acquire a server as a dependency to do it (D2).  It also
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

# Imports - Python Standard Library
import subprocess  # nosec B404
import sys
from pathlib import Path
from typing import List

# Constants
REPOSITORY_ROOT = Path(__file__).parent.parent
IMPORT_ROOT = REPOSITORY_ROOT / 'app'

# What a client must not acquire by asking for the contract's shapes.
SERVER_MODULES = ('fastapi', 'starlette', 'uvicorn')


def imported_modules(
        statement: str
) -> List[str]:
    """ Return the modules a statement leaves loaded, in its own process.

        Args:
            statement (str):
                Python to run with the import root on the path.

        Returns:
            loaded (List[str]):
                Top-level names of every module then in memory.
    """

    program = (
        'import sys\n'
        f'sys.path.insert(0, {str(IMPORT_ROOT)!r})\n'
        f'{statement}\n'
        "print('\\n'.join(sorted({name.split('.')[0] "
        'for name in sys.modules})))'
    )
    finished = subprocess.run(  # nosec B603
        [sys.executable, '-c', program],
        capture_output=True,
        text=True,
        check=True
    )

    return finished.stdout.split()


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
