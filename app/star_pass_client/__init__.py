#!/usr/bin/env python3
""" A client for the star-pass API, generated from its contract.

    The operations are generated from 'docs/api/openapi.json', so the
    command line client can reach everything the web interface can and
    a missing endpoint is a failing test rather than something nobody
    notices (D15).
"""

# Imports - Local
from ._client import ApiProblem, Client

__all__ = [
    'ApiProblem',
    'Client'
]
