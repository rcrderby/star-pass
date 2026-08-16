#!/usr/bin/env python3
""" A client for the star-pass API, generated from its contract.

    The operations are generated from 'docs/api/openapi.json', so the
    command line client can reach everything the web interface can and
    a missing endpoint is a failing test rather than something nobody
    notices (D15).
"""

# Imports - Local
from ._client import ApiProblem, Client
from ._local import LocalClient, LocalOperationUnavailable
from ._stream import StreamEvent, StreamProtocolError

__all__ = [
    'ApiProblem',
    'Client',
    'LocalClient',
    'LocalOperationUnavailable',
    'StreamEvent',
    'StreamProtocolError'
]
