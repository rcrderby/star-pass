#!/usr/bin/env python3
""" The browser's session, and the token that proves a request is ours.

    **The one module that decides what a session is.**  Everything
    else asks it two questions -- which session is this, and is this
    request carrying the right token -- and that is what keeps the
    answer replaceable.  It is the arrangement the API service uses
    for the same reason: reading the credential in exactly one place
    is what makes swapping a static token for an identity provider a
    change to one module rather than to every route (D3).

    **A session carries nothing today.**  There is no login: a single
    person reaches this over a network that controls access (D14), and
    an authentication boundary in front of the whole system is
    deferred by decision.  So the session is an opaque identifier and
    nothing else -- not a name, not a scope, not a token.  Adding a
    signed payload, or a store to look one up in, is what happens the
    day OIDC lands and the session starts carrying an identity, and
    that day the change is here.

    **The token is derived rather than stored.**  It is an HMAC of the
    session identifier, so the pair can be checked without a store,
    and knowing one does not give you the other.  Signing rather than
    storing is what lets this service be restarted, or eventually run
    twice, without logging anybody out.

    What makes a write safe is three things and not one: the cookie is
    'SameSite=Strict', so a browser sends it on nothing an off-site
    page initiated; the token has to arrive in a **header**, which an
    off-site form cannot set; and the origin of a write is checked.
    Any one of them can be argued around, which is why there are
    three.
"""

# Imports - Python Standard Library
import hmac
from hashlib import sha256
from secrets import compare_digest, token_urlsafe
from typing import Optional

# Imports - Third-Party
from fastapi import Request, Response

# Imports - Local
from . import _defaults

# How much randomness a session identifier carries.  Bytes before
# encoding, so the value a browser holds is longer than this.
SESSION_BYTES = 32


def csrf_token(
        session: str
) -> str:
    """ Return the token that goes with one session.

        Args:
            session (str):
                The session identifier.

        Returns:
            token (str):
                What a write has to carry to be this session's.
    """

    return hmac.new(
        key=_defaults.SESSION_SECRET.encode('utf-8'),
        msg=session.encode('utf-8'),
        digestmod=sha256
    ).hexdigest()


def session_of(
        request: Request
) -> Optional[str]:
    """ Return the session a request arrived with, if it has one.

        Args:
            request (Request):
                The request.

        Returns:
            session (str | None):
                The identifier, or None when the browser has no
                session yet.
    """

    return request.cookies.get(_defaults.SESSION_COOKIE)


def started(
        response: Response
) -> str:
    """ Give a response a new session, and return it.

        Both cookies are set together, because a browser holding one
        of them is a browser that cannot make a write and cannot be
        told why.

        Args:
            response (Response):
                The response to set them on.

        Returns:
            session (str):
                The identifier the browser will now carry.
    """

    session = token_urlsafe(SESSION_BYTES)

    # HttpOnly: script never needs to read this, and what script
    # cannot read, injected script cannot send anywhere.
    _set_cookie(
        response=response,
        name=_defaults.SESSION_COOKIE,
        value=session,
        readable_by_script=False
    )
    # Readable, deliberately: the page has to put this in a header on
    # every write, which is the half an off-site page cannot do.
    _set_cookie(
        response=response,
        name=_defaults.CSRF_COOKIE,
        value=csrf_token(session=session),
        readable_by_script=True
    )

    return session


def carries_our_token(
        request: Request,
        session: str
) -> bool:
    """ Return whether a request carries this session's token.

        Compared in constant time, for the reason a credential is: a
        comparison that stops at the first wrong character reports, in
        how long it took, how much of the value was right.  As bytes,
        because the str form refuses operands holding non-ASCII
        characters, and Starlette decodes a header latin-1, so any byte
        above 0x7F reaches here as one.

        Args:
            request (Request):
                The request to check.

            session (str):
                The session it arrived with.

        Returns:
            carried (bool):
                Whether the header holds the right token.
    """

    presented = request.headers.get(_defaults.CSRF_HEADER)

    if not presented:
        return False

    return compare_digest(
        presented.encode('utf-8'),
        csrf_token(session=session).encode('utf-8')
    )


def _set_cookie(
        response: Response,
        name: str,
        value: str,
        readable_by_script: bool
) -> None:
    """ Set one of the pair, with the flags both of them share.

        Args:
            response (Response):
                The response to set it on.

            name (str):
                Cookie name.

            value (str):
                Cookie value.

            readable_by_script (bool):
                Whether script may read it.  The session may not; the
                token has to be.

        Returns:
            None.
    """

    response.set_cookie(
        key=name,
        value=value,
        max_age=_defaults.SESSION_MAX_AGE_SECONDS,
        httponly=not readable_by_script,
        secure=_defaults.COOKIES_ARE_SECURE,
        samesite='strict',
        path='/'
    )

    return None
