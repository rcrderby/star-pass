#!/usr/bin/env python3
""" The browser reaching the API only through the front end.

    Two claims, and the tests are mostly about the second.

    The first is that the proxy is faithful: what the API answered is
    what the browser gets, including an answer that arrives over time.

    The second is that the browser never holds a credential and cannot
    be made to spend one.  The credential is added here and never
    forwarded from the request, and a write has to prove it came from
    this page -- a session, a token derived from it in a header, and
    nothing saying it came from another site.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
from typing import Any, Callable, Dict, Iterator, List, Tuple

# Imports - Third-Party
import httpx2
import pytest
from fastapi.testclient import TestClient

# Imports - Local
from star_pass_bff import _defaults, create_app
from star_pass_bff._sessions import csrf_token

# Constants
RUNS_PATH = f'{_defaults.API_PREFIX}/v1/runs'

# What the stub answers with, so a test can tell the body it sent from
# anything the proxy might have invented.
ANSWER = {'runs': []}

# An event stream, as the job endpoint answers one.
STREAM_BODY = b'event: step\ndata: {"label": "Reading"}\n\n'


@pytest.fixture(name='asked')
def fixture_asked() -> List[httpx2.Request]:
    """ Return the list the stub records what it was asked into. """
    return []


@pytest.fixture(name='answering')
def fixture_answering(
    asked: List[httpx2.Request]
) -> Callable[..., Any]:
    """ Return a way to say what the API answers, and with what. """

    def script(
        status_code: int = 200,
        json: Any = None,
        headers: Dict[str, str] = None,
        content: bytes = None
    ) -> httpx2.MockTransport:
        """ Answer every request the same way, recording each. """

        def handle(request: httpx2.Request) -> httpx2.Response:
            """ Record one request and answer it. """
            asked.append(request)

            if content is not None:
                # An async iterator rather than bytes, so the answer
                # is a stream the way the job endpoint's is. Given
                # bytes, the proxy would be passing on something
                # already complete and the test would prove nothing.
                return httpx2.Response(
                    status_code,
                    content=_arriving(content=content),
                    headers=headers or {}
                )

            return httpx2.Response(
                status_code,
                json=ANSWER if json is None else json,
                headers=headers or {}
            )

        return httpx2.MockTransport(handle)

    return script


@pytest.fixture(name='browser')
def fixture_browser(
    answering: Callable[..., Any]
) -> Callable[..., Iterator[TestClient]]:
    """ Return a way to open a browser onto the front end.

        The connection to the API is replaced after the application
        has started, because starting it is what opens the real one --
        the client belongs to the running process rather than to the
        module.
    """

    def opened(**answers: Any) -> Tuple[TestClient, Any]:
        """ Return a client and the stub it will reach. """
        api = create_app()
        client = TestClient(api)
        client.__enter__()  # pylint: disable=unnecessary-dunder-call
        api.state.api = httpx2.AsyncClient(
            transport=answering(**answers),
            base_url=_defaults.API_URL
        )

        return client, api

    return opened


@pytest.fixture(name='loaded')
def fixture_loaded(
    browser: Callable[..., Any]
) -> Tuple[TestClient, Any]:
    """ Return a browser that has already been given a session. """
    client, api = browser()
    client.get(f'{RUNS_PATH}')

    return client, api


def writing(
    client: TestClient
) -> Dict[str, str]:
    """ Return the headers a write from this page carries. """
    return {
        _defaults.CSRF_HEADER: client.cookies[_defaults.CSRF_COOKIE]
    }


class TestWhatTheBrowserIsGiven:
    def test_a_first_visit_is_given_a_session(
        self,
        browser: Callable[..., Any]
    ) -> None:
        client, _api = browser()

        client.get(RUNS_PATH)

        assert client.cookies[_defaults.SESSION_COOKIE]

    def test_script_cannot_read_the_session(
        self,
        browser: Callable[..., Any]
    ) -> None:
        # What script cannot read, injected script cannot send
        # anywhere, which is the whole point of holding the credential
        # here instead (D4).
        client, _api = browser()

        answer = client.get(RUNS_PATH)

        assert 'httponly' in _cookie_header(
            answer=answer,
            name=_defaults.SESSION_COOKIE
        )

    def test_script_can_read_the_token(
        self,
        browser: Callable[..., Any]
    ) -> None:
        # Deliberately: the page has to send it back in a header, and
        # a header is the half an off-site form cannot set.
        client, _api = browser()

        answer = client.get(RUNS_PATH)

        assert 'httponly' not in _cookie_header(
            answer=answer,
            name=_defaults.CSRF_COOKIE
        )

    def test_neither_is_sent_on_another_site_s_request(
        self,
        browser: Callable[..., Any]
    ) -> None:
        client, _api = browser()

        answer = client.get(RUNS_PATH)

        for name in (_defaults.SESSION_COOKIE, _defaults.CSRF_COOKIE):
            assert 'samesite=strict' in _cookie_header(
                answer=answer,
                name=name
            )

    def test_a_browser_that_has_one_is_not_given_another(
        self,
        loaded: Tuple[TestClient, Any]
    ) -> None:
        client, _api = loaded
        first = client.cookies[_defaults.SESSION_COOKIE]

        client.get(RUNS_PATH)

        assert client.cookies[_defaults.SESSION_COOKIE] == first

    def test_the_token_is_this_session_s(
        self,
        loaded: Tuple[TestClient, Any]
    ) -> None:
        client, _api = loaded

        assert client.cookies[_defaults.CSRF_COOKIE] == csrf_token(
            session=client.cookies[_defaults.SESSION_COOKIE]
        )


class TestWhatReachesTheApi:
    def test_the_path_below_the_prefix(
        self,
        asked: List[httpx2.Request],
        loaded: Tuple[TestClient, Any]
    ) -> None:
        client, _api = loaded

        client.get(f'{RUNS_PATH}/r-1')

        assert asked[-1].url.path == '/v1/runs/r-1'

    def test_the_query_it_was_asked_with(
        self,
        asked: List[httpx2.Request],
        loaded: Tuple[TestClient, Any]
    ) -> None:
        client, _api = loaded

        client.get(f'{RUNS_PATH}?limit=5')

        assert asked[-1].url.params['limit'] == '5'

    def test_the_credential_this_service_holds(
        self,
        asked: List[httpx2.Request],
        loaded: Tuple[TestClient, Any]
    ) -> None:
        client, _api = loaded

        client.get(RUNS_PATH)

        assert asked[-1].headers['authorization'] == (
            f'Bearer {_defaults.API_TOKEN}'
        )

    def test_not_a_credential_the_browser_supplied(
        self,
        asked: List[httpx2.Request],
        loaded: Tuple[TestClient, Any]
    ) -> None:
        # A page that could choose what the API is asked with would be
        # a page worth attacking for it.
        client, _api = loaded

        client.get(RUNS_PATH, headers={'Authorization': 'Bearer made-up'})

        assert asked[-1].headers['authorization'] == (
            f'Bearer {_defaults.API_TOKEN}'
        )

    def test_not_the_browser_s_cookies(
        self,
        asked: List[httpx2.Request],
        loaded: Tuple[TestClient, Any]
    ) -> None:
        client, _api = loaded

        client.get(RUNS_PATH)

        assert 'cookie' not in asked[-1].headers

    def test_the_idempotency_key_a_write_carries(
        self,
        asked: List[httpx2.Request],
        loaded: Tuple[TestClient, Any]
    ) -> None:
        # The contract requires one on the keyed writes, so a proxy
        # that dropped it would make them unreachable.
        client, _api = loaded

        client.post(
            f'{RUNS_PATH}/r-1/revisions',
            headers={**writing(client=client), 'Idempotency-Key': 'once'}
        )

        assert asked[-1].headers['idempotency-key'] == 'once'


class TestWhatComesBack:
    def test_the_status_the_api_answered(
        self,
        browser: Callable[..., Any]
    ) -> None:
        client, _api = browser(status_code=404)

        assert client.get(RUNS_PATH).status_code == 404

    def test_the_body_the_api_answered(
        self,
        browser: Callable[..., Any]
    ) -> None:
        client, _api = browser()

        assert client.get(RUNS_PATH).json() == ANSWER

    def test_a_problem_document_keeps_its_media_type(
        self,
        browser: Callable[..., Any]
    ) -> None:
        # A client that handles failures by media type would stop
        # recognising them otherwise.
        client, _api = browser(
            status_code=409,
            headers={'content-type': 'application/problem+json'}
        )

        assert client.get(RUNS_PATH).headers['content-type'] == (
            'application/problem+json'
        )

    def test_a_rate_limited_answer_still_says_when_to_come_back(
        self,
        browser: Callable[..., Any]
    ) -> None:
        client, _api = browser(
            status_code=429,
            headers={'retry-after': '30'}
        )

        assert client.get(RUNS_PATH).headers['retry-after'] == '30'

    def test_an_event_stream_is_passed_on_as_one(
        self,
        browser: Callable[..., Any]
    ) -> None:
        # A job somebody is watching, rather than silence and then a
        # dump at the end.
        client, _api = browser(
            content=STREAM_BODY,
            headers={'content-type': 'text/event-stream'}
        )

        answer = client.get(f'{_defaults.API_PREFIX}/v1/jobs/j-1/events')

        assert answer.headers['content-type'] == 'text/event-stream'
        assert answer.content == STREAM_BODY
        # What says it was passed on rather than gathered up: an
        # answer read to the end before being sent would know its own
        # length.
        assert 'content-length' not in answer.headers

    def test_an_api_that_cannot_be_reached_is_a_bad_gateway(
        self,
        browser: Callable[..., Any]
    ) -> None:
        client, api = browser()
        api.state.api = httpx2.AsyncClient(
            transport=httpx2.MockTransport(_refuse),
            base_url=_defaults.API_URL
        )

        answer = client.get(RUNS_PATH)

        assert answer.status_code == 502
        # The reason names a service the browser cannot reach and has
        # nothing to do about, so it is not in the answer.
        assert _defaults.API_URL not in answer.text


class TestWhatMakesAWriteOurs:
    def test_a_write_from_the_page_goes_through(
        self,
        asked: List[httpx2.Request],
        loaded: Tuple[TestClient, Any]
    ) -> None:
        client, _api = loaded

        answer = client.post(RUNS_PATH, headers=writing(client=client))

        assert answer.status_code == 200
        assert asked[-1].method == 'POST'

    def test_a_write_without_the_token_is_refused(
        self,
        asked: List[httpx2.Request],
        loaded: Tuple[TestClient, Any]
    ) -> None:
        client, _api = loaded
        before = len(asked)

        answer = client.post(RUNS_PATH)

        assert answer.status_code == 403
        # Refused here, so nothing was spent on it upstream.
        assert len(asked) == before

    def test_a_write_carrying_the_wrong_token_is_refused(
        self,
        loaded: Tuple[TestClient, Any]
    ) -> None:
        client, _api = loaded

        answer = client.post(
            RUNS_PATH,
            headers={_defaults.CSRF_HEADER: csrf_token(session='another')}
        )

        assert answer.status_code == 403

    def test_a_write_from_a_browser_with_no_session_is_refused(
        self,
        browser: Callable[..., Any]
    ) -> None:
        client, _api = browser()

        answer = client.post(RUNS_PATH)

        assert answer.status_code == 403
        assert 'no star-pass session' in answer.json()['detail']

    def test_a_write_another_site_says_it_sent_is_refused(
        self,
        loaded: Tuple[TestClient, Any]
    ) -> None:
        client, _api = loaded

        answer = client.post(
            RUNS_PATH,
            headers={
                **writing(client=client),
                'Origin': 'https://not-star-pass.example'
            }
        )

        assert answer.status_code == 403

    def test_a_write_the_browser_says_is_cross_site_is_refused(
        self,
        loaded: Tuple[TestClient, Any]
    ) -> None:
        # The browser's own account of where a request came from,
        # which is the one an attacker cannot rewrite.
        client, _api = loaded

        answer = client.post(
            RUNS_PATH,
            headers={
                **writing(client=client),
                'Sec-Fetch-Site': 'cross-site'
            }
        )

        assert answer.status_code == 403

    def test_a_refusal_says_what_to_do_about_it(
        self,
        loaded: Tuple[TestClient, Any]
    ) -> None:
        client, _api = loaded

        answer = client.post(RUNS_PATH)

        assert answer.headers['content-type'].startswith(
            'application/problem+json'
        )
        assert 'Reload the page' in answer.json()['detail']

    def test_a_read_needs_none_of_it(
        self,
        loaded: Tuple[TestClient, Any]
    ) -> None:
        # Reading changes nothing, and a token on every read would be
        # a token in every link.
        client, _api = loaded

        assert client.get(RUNS_PATH).status_code == 200


async def _arriving(
    content: bytes
) -> Any:
    """ Yield an answer in pieces, as a service sending one does. """
    for piece in content.splitlines(keepends=True):
        yield piece


def _refuse(request: httpx2.Request) -> httpx2.Response:
    """ Fail the way an unreachable service does. """
    raise httpx2.ConnectError('nothing listening', request=request)


def _cookie_header(
    answer: Any,
    name: str
) -> str:
    """ Return the 'Set-Cookie' line for one cookie, lowercased. """
    return next(
        value.lower()
        for key, value in answer.headers.multi_items()
        if key.lower() == 'set-cookie' and value.startswith(f'{name}=')
    )
