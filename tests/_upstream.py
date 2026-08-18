#!/usr/bin/env python3
""" Everything that stands in for a service outside this process.

    A module of its own rather than more of 'conftest.py', which
    crossed the line limit and had a seam to be split on: these
    fixtures replace the boundary, and the ones left behind build
    stored state.  Registered as a plugin from 'conftest.py', so a
    test asks for one by name without knowing which file it is in.

    Nothing here reaches a network.  A test that made a live request
    would be a test whose result depended on somebody else's service
    being up, and on a real credential being present to reach it.
"""

# Imports - Python Standard Library
import json
from typing import Any, Callable, Dict, List

# Imports - Third-Party
import pytest
from requests import Response

# Constants
# What the address of a shift create ends with, so the scripted
# answers can tell one from a read of the opportunity itself.
SHIFT_CREATE_SUFFIX = '/shifts'


@pytest.fixture(name='make_amplify_shift')
def fixture_make_amplify_shift() -> Callable[..., dict]:
    """ Return a factory building a shift as Amplify describes one.

        The default is the row the default event would create, so a
        test arranging "Amplify already has this shift" says only that.
    """

    def build(**overrides: Any) -> dict:
        """ Return a shift, replacing any field named in 'overrides'. """
        shift: dict = {
            'id': 1,
            'start': '2026-09-03 19:15:00',
            'end': '2026-09-03 21:30:00',
            'duration': 135
        }
        shift.update(overrides)

        return shift

    return build


@pytest.fixture(name='answer_requests')
def fixture_answer_requests(
    monkeypatch: pytest.MonkeyPatch
) -> Callable[[Callable[[dict], dict]], list]:
    """ Return a way to answer every request the core sends.

        Everything reaching the calendar or Amplify goes through
        'Helpers.send_api_request', which this replaces, so a test
        using it makes no live request.  Here rather than beside any
        one caller: how a scripted answer is built is the same
        wherever one is scripted, and a second copy would be a second
        thing to keep in step with what the code reads.

        The script is handed the whole request rather than its address,
        because two reads of one calendar window differ only in the
        query string they carry.

        The list it returns is what was asked for, in order, so a test
        about what a send does to Amplify reads the requests rather
        than inferring them from what was stored afterwards.
    """

    def script(body_for: Callable[[dict], dict]) -> list:
        """ Answer each request with the body chosen for it. """
        sent: list = []

        def send(
            _self: Any,
            api_request_data: dict,
            **_ignored: Any
        ) -> Response:
            """ Answer one request. """
            sent.append(api_request_data)
            response = Response()
            response.status_code = 200
            response.headers['Content-Type'] = 'application/json'
            # pylint: disable-next=protected-access
            response._content = json.dumps(
                body_for(api_request_data)
            ).encode('utf-8')

            return response

        monkeypatch.setattr(
            'star_pass._helpers.Helpers.send_api_request',
            send
        )

        return sent

    return script


@pytest.fixture(name='amplify_holds')
def fixture_amplify_holds(
    answer_requests: Callable[[Callable[[dict], dict]], None]
) -> Callable[..., None]:
    """ Return a way to say what Amplify's opportunities already hold.

        Every read of an opportunity is answered from here, so a test
        that asks what a send would create makes no live request.  The
        title is answered by the same call, because one request carries
        both.

        An opportunity the mapping does not name answers without a
        'shifts' key at all, which is Amplify's own way of saying it
        holds none.

        Returns the list of requests made, so a test about a send can
        read what it asked Amplify for.
    """

    def script(
        shifts: dict | None = None,
        titled: bool = True
    ) -> list:
        """ Answer each opportunity with the shifts named against it. """
        held = shifts if shifts is not None else {}

        def need_body(request: dict) -> dict:
            """ Return what Amplify says about one opportunity. """
            url = request['url']

            if url.endswith(SHIFT_CREATE_SUFFIX):
                # A create, which the send does not read an answer
                # from; only the reads before it are scripted here.
                return {}

            need_id = url.rsplit('/', 1)[-1]
            data: dict = {}

            if titled:
                data['need_title'] = f'Need {need_id}'

            if need_id in held:
                data['shifts'] = held[need_id]

            return {'data': data}

        return answer_requests(need_body)

    return script


@pytest.fixture(name='credential_accepted')
def fixture_credential_accepted(
    answer_requests: Callable[[Callable[[dict], dict]], list]
) -> List[Dict[str, Any]]:
    """ Have Amplify take the credential, and return what was asked.

        The read the check is made with returns rows, and what is in
        them is never looked at: the question is whether the request
        was allowed.  Here rather than in either credential module,
        because the core's check and the endpoint over it need the
        same arrangement.
    """
    return answer_requests(lambda _request: {'data': []})
