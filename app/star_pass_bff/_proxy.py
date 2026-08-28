#!/usr/bin/env python3
""" Passing a browser's request to the API, with the credential added.

    A thin proxy and nothing else: it attaches the credential, checks
    that the browser has a session and that a write came from this
    page, and gets out of the way.  **No
    domain logic** -- what an answer means is the API's to say and the
    contract's to shape, and a front-end that started interpreting
    answers would be a second implementation of the thing the API
    exists to be (D1, D4).

    The browser holds no credential, so every request arrives without
    one and leaves with the service's.  Anything the browser sent that
    could be mistaken for one is dropped rather than forwarded: what
    reaches the API is an allowed set of headers, and the credential
    this service was configured with.

    **Answers that arrive over time are passed on over time.**  The
    job event stream is one of the contract's operations, and a proxy
    that buffered it would turn a job somebody is watching into
    silence followed by a dump at the end.

    **Every method is checked, not only the writes.**  A read needs a
    session.  A write needs that session, the token derived from it in
    a header, and nothing saying it came from another site.

    Same origin, so there is **no CORS configuration at all**.  If
    that changes, the boundary has leaked rather than moved.
"""

# Imports - Python Standard Library
from typing import Optional
from urllib.parse import urlsplit

# Imports - Third-Party
import httpx2
from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse

# Imports - Local
from . import _defaults
from ._sessions import carries_our_token, session_of

router = APIRouter()

# The methods a browser may send through.  An allowlist, so a method
# nobody designed for is refused here rather than reaching the API.
READ_METHODS = ('GET', 'HEAD')
WRITE_METHODS = ('POST', 'PATCH', 'PUT', 'DELETE')

# What is passed on from the browser's request.  An allowlist for the
# reason the credential is added rather than forwarded: what the API
# receives should be what this service decided to send, not whatever
# arrived.  'Idempotency-Key' is on it because the contract requires
# one on the keyed writes.
FORWARDED_REQUEST_HEADERS = (
    'accept',
    'content-type',
    'idempotency-key'
)

# What is passed back.  'Retry-After' is here because a rate-limited
# answer that did not say when to come back would leave a client
# guessing, and the stream headers because an event stream that
# arrived without them would be read as a document.
FORWARDED_RESPONSE_HEADERS = (
    'content-type',
    'retry-after',
    'cache-control'
)

# What says an answer arrives over time rather than at once.
STREAM_MEDIA_TYPE = 'text/event-stream'

# What a browser is told when a write did not carry this page's token,
# or came from somewhere else.  It says what to do rather than what
# was wrong, because the fix is the same either way and the detail
# would only help whoever was trying it.
NOT_OURS = (
    'This request did not come from the star-pass page in this '
    'browser session. Reload the page and try again.'
)

# What it is told when the session is missing entirely, which is a
# different thing: nothing was refused, there is simply nothing to
# check a write against yet.
NO_SESSION = (
    'This browser has no star-pass session. Load the page first, '
    'then try again.'
)


@router.api_route(
    f'{_defaults.API_PREFIX}/{{path:path}}',
    methods=list(READ_METHODS + WRITE_METHODS),
    include_in_schema=False
)
async def proxied(
        request: Request,
        path: str
) -> Response:
    """ Pass one request to the API and its answer back.

        Args:
            request (Request):
                What the browser sent.

            path (str):
                What it asked for, below the prefix.

        Raises:
            HTTPException:
                403 when the browser has no session or a write did not
                come from this page, and 502 when the API cannot be
                reached.

        Returns:
            answer (Response):
                What the API said, streamed when the API streams.
    """

    session = _session_or_refuse(request=request)

    if request.method in WRITE_METHODS:
        _check_the_write_is_ours(request=request, session=session)

    client: httpx2.AsyncClient = request.app.state.api

    upstream = client.build_request(
        method=request.method,
        url=f'/{path}',
        params=dict(request.query_params),
        headers=_headers_for(request=request),
        content=await request.body()
    )

    try:
        answer = await client.send(upstream, stream=True)

    except httpx2.HTTPError as error:
        # The reason is this deployment's business, not the browser's:
        # it names the address of a service the browser cannot reach
        # and has nothing to do about.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail='The star-pass API could not be reached.'
        ) from error

    return await _answered(answer=answer)


async def _answered(
        answer: httpx2.Response
) -> Response:
    """ Return what the API said, in the shape it said it.

        Args:
            answer (httpx2.Response):
                The upstream response, not yet read.

        Returns:
            response (Response):
                The same status, body and allowed headers.
    """

    headers = {
        name: value
        for name, value in answer.headers.items()
        if name.lower() in FORWARDED_RESPONSE_HEADERS
    }

    if answer.headers.get('content-type', '').startswith(
        STREAM_MEDIA_TYPE
    ):
        return StreamingResponse(
            _streamed(answer=answer),
            status_code=answer.status_code,
            headers=headers
        )

    body = await answer.aread()
    await answer.aclose()

    return Response(
        content=body,
        status_code=answer.status_code,
        headers=headers
    )


async def _streamed(
        answer: httpx2.Response
) -> object:
    """ Yield an answer as it arrives, and close it at the end.

        Args:
            answer (httpx2.Response):
                The upstream response, not yet read.

        Yields:
            chunk (bytes):
                Whatever has arrived, unbuffered.
    """

    try:
        async for chunk in answer.aiter_raw():
            yield chunk

    finally:
        await answer.aclose()


def _headers_for(
        request: Request
) -> dict:
    """ Return what to send the API, with the credential added.

        Args:
            request (Request):
                What the browser sent.

        Returns:
            headers (dict):
                The allowed headers, plus the credential.
    """

    headers = {
        name: value
        for name, value in request.headers.items()
        if name.lower() in FORWARDED_REQUEST_HEADERS
    }
    headers['Authorization'] = f'Bearer {_defaults.API_TOKEN}'

    return headers


def _session_or_refuse(
        request: Request
) -> str:
    """ Return the session this request arrived with, or refuse it.

        Asked of every method.  A request without one is forwarded
        carrying the service's credential and no check, so the session
        is what stands between network reach and the database (D14).

        The middleware mints one on the way out of the page, so a
        browser has a session before its own code asks for anything.

        Args:
            request (Request):
                The request to check.

        Raises:
            HTTPException:
                403, saying what to do about it.

        Returns:
            session (str):
                The session it arrived with.
    """

    session = session_of(request=request)

    if session is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=NO_SESSION
        )

    return session


def _check_the_write_is_ours(
        request: Request,
        session: str
) -> None:
    """ Refuse a write that did not come from this page.

        Three things have to hold: the browser has a session, the
        token derived from it arrived in a header, and nothing says
        the request came from another site.  The session is checked
        for every method and arrives here as an argument; a header is
        what an off-site form cannot set, so the token is a write
        concern.

        Args:
            request (Request):
                The write to check.

            session (str):
                The session it arrived with.

        Raises:
            HTTPException:
                403, saying what to do about it.

        Returns:
            None.
    """

    if not carries_our_token(request=request, session=session):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=NOT_OURS
        )

    if _from_elsewhere(request=request):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=NOT_OURS
        )

    return None


def _from_elsewhere(
        request: Request
) -> bool:
    """ Return whether a write says it came from another site.

        The host is compared rather than the whole origin: a proxy
        terminates TLS in front of this service (D6), so the scheme
        the browser used and the scheme this process sees are
        different by design, and comparing them would refuse every
        write in a real deployment.

        Args:
            request (Request):
                The write to check.

        Returns:
            elsewhere (bool):
                Whether anything about it names another site.
    """

    if request.headers.get('sec-fetch-site') not in (None, 'same-origin'):
        return True

    origin: Optional[str] = request.headers.get('origin')

    if origin is None:
        return False

    return urlsplit(origin).netloc != request.headers.get('host')
