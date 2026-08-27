#!/usr/bin/env python3
""" Who is calling, and what they are allowed to ask for.

    One dependency reads the credential and returns a 'Principal'.  No
    other module reads the token or the Authorization header, and no
    route decides for itself whether a caller is allowed in.  That is
    what makes the move to OpenID Connect a change here rather than a
    change everywhere (D3): the token comparison becomes a token
    validation, the same 'Principal' comes out, and the routes are
    untouched.

    Every route declares the scopes it needs even though there is one
    principal today and it holds all of them.  A scope added to a route
    later is a change to that route; a scope system added later is a
    change to every route.

    The two failures are different and are answered differently.  A
    caller the service cannot identify gets 401 and a challenge saying
    how to authenticate.  A caller it can identify, asking for
    something their scopes do not cover, gets 403: repeating the
    challenge would invite them to try another credential for a
    decision that was not about their credential.
"""

# Imports - Python Standard Library
from dataclasses import dataclass
from secrets import compare_digest
from typing import FrozenSet, Optional

# Imports - Third-Party
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
    SecurityScopes
)

# Imports - Local
from star_pass._exceptions import ConfigurationError
from star_pass._logging import get_logger
from . import _defaults

# Constants
# What a caller can ask to do.  Named for the resource and the verb, so
# that a token issued to something other than this service's own client
# can be given a subset that reads as a sentence.
SCOPE_RUNS_READ = 'runs:read'
SCOPE_RUNS_WRITE = 'runs:write'
SCOPE_SEND_EXECUTE = 'send:execute'
SCOPE_CONFIG_READ = 'config:read'
SCOPES = {
    SCOPE_RUNS_READ: 'Read runs, revisions, events and the change log.',
    SCOPE_RUNS_WRITE: 'Collect a run and edit what it collected.',
    SCOPE_SEND_EXECUTE: 'Create shifts in Amplify.',
    SCOPE_CONFIG_READ: 'Read the service configuration and version.'
}

# The challenge returned with a 401, naming the scheme the service
# accepts.  Required by RFC 9110 on a 401 and it is what tells a client
# what to send.
AUTHENTICATE_HEADER = 'WWW-Authenticate'
AUTHENTICATE_CHALLENGE = 'Bearer'

# The scheme, declared so that it reaches the generated specification
# and the documentation offers somewhere to paste a token.  It does not
# raise on a missing credential: this module answers that itself, so
# that the response is a problem document like every other failure.
bearer_scheme = HTTPBearer(
    scheme_name='Bearer token',
    description='The value of STAR_PASS_API_TOKEN.',
    auto_error=False
)

# Module logger
logger = get_logger(__name__)


@dataclass(frozen=True)
class Principal:
    """ Who is making a request, and what they may ask for.

        Attributes:
            id (str):
                Identifier recorded against everything the caller
                changes.  A single value while the credential is a
                static token, and a real subject once an identity
                provider issues one, with no change to what records it.

            scopes (FrozenSet[str]):
                What this caller is allowed to do.
    """

    id: str
    scopes: FrozenSet[str]


def api_token() -> str:
    """ Return the configured API token.

        Read through a function rather than bound at import, so that
        the value a request is checked against is the one configured
        now.

        Args:
            None.

        Raises:
            ConfigurationError:
                If no token is configured, or it is too short to be
                one.

        Returns:
            token (str):
                The token a caller has to present.
    """

    token = _defaults.API_TOKEN

    if not token:
        message = (
            'STAR_PASS_API_TOKEN is not set. The service authenticates '
            'every request against it and will not start without one.'
        )
        logger.error(message)
        raise ConfigurationError(message)

    if len(token) < _defaults.API_TOKEN_MINIMUM_LENGTH:
        message = (
            'STAR_PASS_API_TOKEN is shorter than '
            f'{_defaults.API_TOKEN_MINIMUM_LENGTH} characters. It is '
            'the only thing standing in front of the service, so a '
            'guessable one is the same as none.'
        )
        logger.error(message)
        raise ConfigurationError(message)

    return token


def check_configuration() -> None:
    """ Fail now if the service cannot authenticate anyone.

        Called while the application is built, so that a deployment
        missing its token stops at startup rather than at the first
        request -- or, worse, at the first request that mattered.

        Args:
            None.

        Raises:
            ConfigurationError:
                If the token is missing or unusable.

        Returns:
            None.
    """

    api_token()

    return None


def _unauthenticated(
        reason: str
) -> HTTPException:
    """ Return the failure for a caller the service cannot identify.

        Args:
            reason (str):
                What was wrong with the credential.

        Returns:
            error (HTTPException):
                A 401 carrying the challenge.
    """

    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=reason,
        headers={AUTHENTICATE_HEADER: AUTHENTICATE_CHALLENGE}
    )


async def get_principal(
        security_scopes: SecurityScopes,
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(
            bearer_scheme
        )
) -> Principal:
    """ Identify the caller and check what they asked for.

        The only place the credential is read.  A route names the
        scopes it needs and receives a principal or nothing at all.

        Args:
            security_scopes (SecurityScopes):
                Scopes the route declared.

            credentials (HTTPAuthorizationCredentials, optional):
                The parsed Authorization header, or None when there was
                no usable one.

        Raises:
            HTTPException:
                401 when the caller cannot be identified, 403 when they
                can be and their scopes do not cover the request.

            ConfigurationError:
                If the service has no token to check against.

        Returns:
            principal (Principal):
                Who is calling.
    """

    if credentials is None:
        raise _unauthenticated(
            reason='This endpoint requires a bearer token.'
        )

    # 'compare_digest' rather than '==': a comparison that stops at the
    # first wrong character reports, in how long it took, how much of
    # the token was right.  Encoded first because the str form refuses
    # operands holding non-ASCII characters, and Starlette decodes a
    # header latin-1, so any byte above 0x7F reaches here as one.
    presented = credentials.credentials.encode('utf-8')
    expected = api_token().encode('utf-8')

    if not compare_digest(presented, expected):
        raise _unauthenticated(
            reason='The bearer token is not valid.'
        )

    principal = Principal(
        id=_defaults.API_PRINCIPAL_ID,
        scopes=frozenset(SCOPES)
    )

    missing = set(security_scopes.scopes) - principal.scopes
    if missing:
        message = (
            'This endpoint requires the '
            f'{", ".join(sorted(missing))} scope.'
        )
        logger.warning(message)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=message
        )

    return principal


def requires(
        *scopes: str
) -> Security:
    """ Declare the scopes a route needs.

        Args:
            *scopes (str):
                Scopes required to reach the route.

        Returns:
            dependency (Security):
                The principal dependency, carrying those scopes.
    """

    return Security(
        get_principal,
        scopes=list(scopes)
    )
