#!/usr/bin/env python3
""" What a package drags in with it, asked in a process of its own.

    Below both callers, because more than one package here promises
    not to import something: the contract's shapes must not acquire
    the web framework, and the front end must not acquire the domain.
    Both are answered the same way and the answer has to be gathered
    in a fresh process -- this suite has already imported nearly
    everything, so 'sys.modules' in here says nothing about what one
    import costs.
"""

# Imports - Python Standard Library
import subprocess  # nosec B404
import sys
from pathlib import Path
from typing import List

# Constants
REPOSITORY_ROOT = Path(__file__).parent.parent
IMPORT_ROOT = REPOSITORY_ROOT / 'app'


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
