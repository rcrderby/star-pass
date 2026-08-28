#!/usr/bin/env python3
""" The browser's session, and the token that proves a request is ours.

    The one module that decides what a session is.  Everything else
    asks it which session a request carries and whether the token
    beside it is right.

    A session is an opaque identifier and nothing else: there is no
    login, so it carries no name, scope or token.  The CSRF token is
    an HMAC of that identifier rather than a stored value, so the pair
    is checked without a store and knowing one does not give you the
    other, and restarting the service logs nobody out.

    Three things make a write ours: the cookie is 'SameSite=Strict',
    so a browser sends it on nothing an off-site page started; the
    token arrives in a header, which an off-site form cannot set; and
    the origin is checked.
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
