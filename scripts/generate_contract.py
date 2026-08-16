#!/usr/bin/env python3
""" Rewrite the committed contract and the client generated from it.

    Run after changing anything the contract describes -- a route, a
    model, a scope, or the version -- and commit what it writes:

        python scripts/generate_contract.py

    Both artifacts are written by one command because the second is
    generated from the first: the client's operations come from the
    specification, so writing the specification alone would leave a
    client describing the service as it used to be. Two commands would
    make that a thing to remember; one makes it impossible.

    The order matters for the same reason. The specification is
    written from the running application, and the client is then
    generated from the file that was just written.

    'tests/test_api_spec.py' and 'tests/test_api_client.py' fail while
    either committed copy disagrees with what it came from, so a
    forgotten run is caught rather than shipped.
"""

# Imports - Python Standard Library
import sys
from pathlib import Path

# The import root, the same directory pytest and the container image
# put on the path.  Added before the imports below, which is why they
# are not at the top of the file.
sys.path.insert(
    0,
    str(Path(__file__).parent.parent / 'app')
)

# Imports below intentionally follow the path setup above.
# pylint: disable=wrong-import-position

# Imports - Local
from star_pass_api._spec import write as write_specification  # noqa: E402
from star_pass_client._generator import write as write_client  # noqa: E402


def main() -> int:
    """ Write both artifacts and report where they went.

        Args:
            None.

        Returns:
            status (int):
                Zero, for a process that succeeded.
    """

    for write in (write_specification, write_client):
        print(f'Wrote {write()}')

    return 0


if __name__ == '__main__':
    sys.exit(main())
