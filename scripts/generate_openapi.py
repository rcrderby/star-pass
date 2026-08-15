#!/usr/bin/env python3
""" Rewrite the committed OpenAPI specification.

    Run after changing anything the contract describes -- a route, a
    model, a scope, or the version -- and commit what it writes:

        python scripts/generate_openapi.py

    'tests/test_api_spec.py' fails while the committed copy and the
    service disagree, so a forgotten run is caught rather than shipped.
"""

# Imports - Python Standard Library
import sys
from pathlib import Path

# The import root, the same directory pytest and the container image
# put on the path.  Added before the import below, which is why that
# import is not at the top of the file.
sys.path.insert(
    0,
    str(Path(__file__).parent.parent / 'app')
)

# Imports below intentionally follow the path setup above.
# pylint: disable=wrong-import-position

# Imports - Local
from star_pass_api._spec import write  # noqa: E402


def main() -> int:
    """ Write the specification and report where it went.

        Args:
            None.

        Returns:
            status (int):
                Zero, for a process that succeeded.
    """

    print(f'Wrote {write()}')

    return 0


if __name__ == '__main__':
    sys.exit(main())
