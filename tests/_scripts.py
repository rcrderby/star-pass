#!/usr/bin/env python3
""" Loading the commands in 'scripts' from their paths.

    Beside 'tests/_upstream.py' rather than in 'conftest.py':
    nothing here is a fixture, and the two files that call it want
    a function rather than something pytest hands them.
"""

# Imports - Python Standard Library
import sys
from importlib import util
from pathlib import Path
from types import ModuleType


def loaded_script(name: str, path: Path) -> ModuleType:
    """ Load one of the modules in 'scripts' from its path.

        They live there rather than in a package because the directory
        holds commands to run, and nothing else imports them.  Each is
        registered under its own name as it is loaded, which is what
        lets a script's own 'import _drawing' find the module this
        already has rather than a second copy of it - and is why a
        module a script imports has to be loaded first.

        Here rather than in either file that calls it: two copies of
        four lines is what R0801 and JSCPD both report, and the answer
        to a thing two callers must do identically is to move it below
        them.

        Args:
            name (str):
                What to register the module as.

            path (Path):
                The file to load it from.

        Returns:
            module (ModuleType):
                The module, imported.
    """

    specification = util.spec_from_file_location(name, path)
    module = util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)

    return module
