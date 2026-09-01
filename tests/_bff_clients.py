#!/usr/bin/env python3
""" A browser opened onto the front end, with the API stood in for.

    Below both callers, because opening one is fiddly in the same way
    twice: the connection to the API is replaced *after* the
    application has started, since starting it is what opens the real
    one, and the test client has to be entered by hand to get a
    lifespan at all.

    What the stand-in answers is deliberately uninteresting.  These
    tests are about what this service does to a request and an answer
    -- the session it requires, the headers it sets, the line it
    writes -- and never about what the API said.
"""

# Imports - Python Standard Library
from typing import Tuple

# Imports - Third-Party
import httpx2
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Imports - Local
from star_pass_bff import _defaults, create_app


def _answer(
        _request: httpx2.Request
) -> httpx2.Response:
    """ Answer anything the proxy forwards.

        Args:
            _request (httpx2.Request):
                What was forwarded, which does not change the answer.

        Returns:
            answer (httpx2.Response):
                The same empty list of runs, every time.
    """

    return httpx2.Response(
        status_code=200,
        json={'runs': []}
    )


def opened() -> Tuple[TestClient, FastAPI]:
    """ Return a browser onto the front end, and the service behind it.

        Returns:
            opened (Tuple[TestClient, FastAPI]):
                A client with a lifespan running, and the application
                it is talking to.
    """

    api = create_app()
    client = TestClient(api)
    client.__enter__()  # pylint: disable=unnecessary-dunder-call
    api.state.api = httpx2.AsyncClient(
        transport=httpx2.MockTransport(_answer),
        base_url=_defaults.API_URL
    )

    return client, api
