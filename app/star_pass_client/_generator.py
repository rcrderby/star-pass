#!/usr/bin/env python3
""" Writing the client's operations from the committed specification.

    The command line client can do anything the web interface can, and
    D15 makes that structural rather than a discipline: every operation
    the contract publishes becomes a method here, because a generator
    reads the contract rather than a person reading it and remembering.

    Only the operations are generated.  The session, the credential and
    the failure mapping are written by hand in '_client.py', so what a
    reviewer reads is ordinary code and what is generated is nothing
    but the shape of the API.

    Rendering is fixed here for the same reason it is fixed for the
    specification: comparing two generated files is comparing two
    renderings, so the order and the spacing have to come from one
    place or a diff shows churn instead of a change to the contract.
"""

# Imports - Python Standard Library
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Constants
# Where the contract is read from and the operations are written to.
# The specification is read from the committed file rather than from a
# running service: the file is the artifact, and a generator that
# needed the service started first would be a generator nobody runs.
PACKAGE_DIRECTORY = Path(__file__).parent
REPOSITORY_ROOT = PACKAGE_DIRECTORY.parent.parent
SPECIFICATION_FILE = REPOSITORY_ROOT / 'docs' / 'api' / 'openapi.json'
OPERATIONS_FILE = PACKAGE_DIRECTORY / '_operations.py'

FILE_ENCODING = 'utf-8'

# The media type that means an operation is answered over time rather
# than at once, so the method yields lines instead of returning a body.
STREAM_MEDIA_TYPE = 'text/event-stream'

# What a path parameter's published type is called in Python.  A
# generated method that took every path value as a string would
# describe a revision number as text, which is not what the contract
# says one is.
PATH_TYPES = {
    'boolean': 'bool',
    'integer': 'int',
    'number': 'float',
    'string': 'str'
}

# The command that rewrites the committed file, quoted in the failure
# when it no longer matches.
REGENERATE_COMMAND = 'python scripts/generate_contract.py'

# What every generated file starts with.  It says what wrote it,
# because the first thing anyone does with a file like this is try to
# edit it.
HEADER = '''#!/usr/bin/env python3
""" The operations the star-pass API publishes.

    Generated from 'docs/api/openapi.json' by
    'app/star_pass_client/_generator.py'. Do not edit: run
    "{command}" and commit the result.

    One method per operation in the contract, which is what makes
    "the command line client can do anything the web interface can"
    a property of the build rather than a promise (D15). What each
    method sends, and what it does with the answer, is in
    '_client.py'.
"""

# Imports - Python Standard Library
from typing import Any, Callable, Dict, Iterator

# Imports - Local
from ._stream import StreamEvent


class Operations:
    """ One method per operation the contract publishes.

        Mixed into 'Client', which supplies the '_call' and '_stream'
        these methods use.
    """

    # What the other half has to provide.  Declared rather than
    # assumed, so the contract between the generated methods and the
    # written ones is on the page and a checker reading this file
    # alone can see it.
    _call: Callable[..., Any]
    _stream: Callable[..., Iterator[StreamEvent]]
'''


def _summary(
        operation: Dict[str, Any]
) -> str:
    """ Return the one-line description of an operation.

        Args:
            operation (Dict[str, Any]):
                The operation from the specification.

        Returns:
            summary (str):
                What the operation does.
    """

    return operation.get('summary', 'Call the operation.').rstrip('.')


def _path_parameters(
        operation: Dict[str, Any]
) -> List[Tuple[str, str]]:
    """ Return the path parameters an operation takes, in order.

        Each with the Python type its published schema names, because
        a path value is not always text: a revision is a number, and a
        method saying otherwise would be the contract described wrong
        by the thing generated from it.

        Args:
            operation (Dict[str, Any]):
                The operation from the specification.

        Returns:
            parameters (List[Tuple[str, str]]):
                The name and Python type of each path parameter.
    """

    return [
        (
            parameter['name'],
            PATH_TYPES.get(
                parameter.get('schema', {}).get('type'),
                'str'
            )
        )
        for parameter in operation.get('parameters', [])
        if parameter.get('in') == 'path'
    ]


def header_argument(
        name: str
) -> str:
    """ Return the argument name a header parameter is taken as.

        A header is named for the wire, with capitals and hyphens; an
        argument is named for Python.  Converted here rather than by
        each caller, so that renaming a header in the contract renames
        the argument with it.

        Args:
            name (str):
                The header, as the contract publishes it.

        Returns:
            argument (str):
                The same name, as an identifier.
    """

    return name.lower().replace('-', '_')


def _header_parameters(
        operation: Dict[str, Any]
) -> List[str]:
    """ Return the headers an operation requires, in order.

        Only the required ones.  An optional header is something a
        caller may choose to send, and a generated method that took one
        would make the choice look mandatory.

        Args:
            operation (Dict[str, Any]):
                The operation from the specification.

        Returns:
            names (List[str]):
                The header names, as the contract publishes them.
    """

    return [
        parameter['name']
        for parameter in operation.get('parameters', [])
        if parameter.get('in') == 'header' and parameter.get('required')
    ]


def _takes_body(
        operation: Dict[str, Any]
) -> bool:
    """ Return whether an operation is sent something.

        Args:
            operation (Dict[str, Any]):
                The operation from the specification.

        Returns:
            sends (bool):
                Whether it carries a request body.
    """

    return bool(operation.get('requestBody'))


def _is_stream(
        operation: Dict[str, Any]
) -> bool:
    """ Return whether an operation answers over time.

        Args:
            operation (Dict[str, Any]):
                The operation from the specification.

        Returns:
            streaming (bool):
                Whether its successful response is a stream.
    """

    responses = operation.get('responses', {})
    content = responses.get('200', {}).get('content', {})

    return STREAM_MEDIA_TYPE in content


def _method(
        path: str,
        verb: str,
        operation: Dict[str, Any]
) -> str:
    """ Return one operation as a method.

        Args:
            path (str):
                The templated path the operation is served at.

            verb (str):
                The HTTP method.

            operation (Dict[str, Any]):
                The operation from the specification.

        Returns:
            source (str):
                The method, indented to sit in a class body.
    """

    name = operation['operationId']
    parameters = _path_parameters(operation=operation)
    headers = _header_parameters(operation=operation)
    streaming = _is_stream(operation=operation)
    sends = _takes_body(operation=operation)

    # The body comes first and the headers last, so that adding a path
    # parameter to an operation cannot change what an existing
    # positional argument means.
    signature = (
        ',\n            body: Dict[str, Any]' if sends else ''
    ) + ''.join(
        f',\n            {parameter}: {kind}'
        for parameter, kind in parameters
    ) + ''.join(
        f',\n            {header_argument(name=header)}: str'
        for header in headers
    )
    sent = ', '.join(
        f"'{header}': {header_argument(name=header)}"
        for header in headers
    )
    arguments = (
        ',\n            body=body' if sends else ''
    ) + (
        f',\n            headers={{{sent}}}' if headers else ''
    ) + ''.join(
        f',\n            {parameter}={parameter}'
        for parameter, _ in parameters
    )
    documented = (
        '\n                body (Dict[str, Any]):'
        '\n                    What the operation is sent, shaped as '
        'the\n                    contract publishes it.\n'
        if sends
        else ''
    ) + ''.join(
        f'\n                {parameter} ({kind}):'
        f'\n                    Value for the path.\n'
        for parameter, kind in parameters
    ) + ''.join(
        f'\n                {header_argument(name=header)} (str):'
        f'\n                    Value for the {header} header.\n'
        for header in headers
    )
    answer = (
        """            event (StreamEvent):
                    One event, in the order they arrive."""
        if streaming
        else """            answer (Any):
                    What the service answered."""
    )

    return f'''
    def {name}(
            self{signature}
    ) -> {'Iterator[StreamEvent]' if streaming else 'Any'}:
        """ {_summary(operation=operation)}.

            Args:{documented or '\n                None.\n'}
            Raises:
                ApiProblem:
                    If the service reported a failure.

            {'Yields' if streaming else 'Returns'}:
    {answer}
        """

        return self.{'_stream' if streaming else '_call'}(
            method='{verb.upper()}',
            path='{path}'{arguments}
        )
'''


def _operations(
        document: Dict[str, Any]
) -> List[Tuple[str, str, Dict[str, Any]]]:
    """ Return every operation the contract publishes, in a fixed order.

        Sorted by the name the method takes, so that adding an
        endpoint moves one method into place rather than reordering
        the file.

        Args:
            document (Dict[str, Any]):
                The specification.

        Returns:
            operations (List[Tuple[str, str, Dict[str, Any]]]):
                The path, the verb and the operation, by method name.
    """

    found = [
        (path, verb, operation)
        for path, verbs in document.get('paths', {}).items()
        for verb, operation in verbs.items()
    ]

    return sorted(found, key=lambda item: item[2]['operationId'])


def specification() -> Dict[str, Any]:
    """ Return the committed contract.

        Args:
            None.

        Returns:
            document (Dict[str, Any]):
                The OpenAPI document as committed.
    """

    return json.loads(
        SPECIFICATION_FILE.read_text(encoding=FILE_ENCODING)
    )


def render(
        document: Dict[str, Any]
) -> str:
    """ Return the operations as they are written to the file.

        Args:
            document (Dict[str, Any]):
                The specification to generate from.

        Returns:
            rendered (str):
                The module's source.
    """

    return HEADER.format(command=REGENERATE_COMMAND) + ''.join(
        _method(path=path, verb=verb, operation=operation)
        for path, verb, operation in _operations(document=document)
    )


def committed() -> str:
    """ Return the generated file as it is on disk.

        Args:
            None.

        Returns:
            source (str):
                The file's content, or an empty string when it is not
                there yet.
    """

    if not OPERATIONS_FILE.is_file():
        return ''

    return OPERATIONS_FILE.read_text(encoding=FILE_ENCODING)


def write() -> Path:
    """ Write the generated operations over the committed copy.

        Args:
            None.

        Returns:
            path (Path):
                Where it was written.
    """

    OPERATIONS_FILE.write_text(
        data=render(document=specification()),
        encoding=FILE_ENCODING
    )

    return OPERATIONS_FILE
