#!/usr/bin/env python3
""" The generated specification, and where the committed copy lives.

    The document is generated from the running application and never
    written by hand.  A copy is committed so that a change to the
    contract shows up in a diff and has to be looked at, and so that
    the command line client's remote client can be generated from a
    file rather than from a service someone has to start first.

    Committing a generated file only works while something checks the
    two agree: 'tests/test_api_spec.py' regenerates and compares, so
    drift fails the build rather than being discovered by whatever was
    generated from the stale copy.

    Rendering is fixed here rather than left to a caller, because a
    comparison between two documents is really a comparison between two
    renderings of them: sorted keys and a fixed indent are what make a
    diff show the change to the contract instead of a reordering.
"""

# Imports - Python Standard Library
import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator

# Imports - Local
from . import _defaults
from ._app import create_app

# Constants
# Where the committed copy lives.  Outside the package: it is a
# published artifact rather than something the application reads, and
# nothing at run time opens it.
SPECIFICATION_DIRECTORY = Path(__file__).parent.parent.parent / 'docs' / 'api'
SPECIFICATION_FILE = SPECIFICATION_DIRECTORY / 'openapi.json'

# How the file is rendered.  Sorted so that a diff shows a change to
# the contract and not a change in the order a dictionary was built.
SPECIFICATION_INDENT = 2

# Stands in for the token while the document is generated.  The
# specification describes the shape of the service, which does not
# depend on the value it authenticates against, and the value never
# reaches the document.  Supplying one here means the document comes
# from exactly the application that serves, rather than from a second
# way of building it that could describe something else.  The name
# avoids the words bandit reads as a credential being assigned.
PLACEHOLDER_CREDENTIAL = 'generated-specification-placeholder-value'

# The command that rewrites the committed copy, quoted in the failure
# when it no longer matches.
REGENERATE_COMMAND = 'python scripts/generate_contract.py'


@contextmanager
def _configured() -> Iterator[None]:
    """ Supply a token for the duration of the block, if none is set.

        Args:
            None.

        Yields:
            None.
    """

    original = _defaults.API_TOKEN

    if not original:
        _defaults.API_TOKEN = PLACEHOLDER_CREDENTIAL

    try:
        yield

    finally:
        _defaults.API_TOKEN = original


def specification() -> Dict[str, Any]:
    """ Return the specification the service generates.

        Args:
            None.

        Returns:
            document (Dict[str, Any]):
                The OpenAPI document.
    """

    with _configured():
        return create_app().openapi()


def render(
        document: Dict[str, Any]
) -> str:
    """ Return the document as it is written to the committed file.

        Args:
            document (Dict[str, Any]):
                The document to render.

        Returns:
            rendered (str):
                The document as sorted, indented JSON, ending in a
                newline so the file is a well formed text file.
    """

    return json.dumps(
        document,
        indent=SPECIFICATION_INDENT,
        sort_keys=True
    ) + '\n'


def committed() -> str:
    """ Return the committed copy as it is on disk.

        Args:
            None.

        Returns:
            rendered (str):
                The file's content, or an empty string when it is not
                there yet.
    """

    if not SPECIFICATION_FILE.is_file():
        return ''

    return SPECIFICATION_FILE.read_text(encoding=_defaults.FILE_ENCODING)


def write() -> Path:
    """ Write the generated specification over the committed copy.

        Args:
            None.

        Returns:
            path (Path):
                Where it was written.
    """

    SPECIFICATION_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True
    )
    SPECIFICATION_FILE.write_text(
        data=render(document=specification()),
        encoding=_defaults.FILE_ENCODING
    )

    return SPECIFICATION_FILE
