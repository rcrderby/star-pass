#!/usr/bin/env python3
""" What the front-end service was configured with.

    Its own settings, separate from the API service's, because the two
    are separate containers with separate environments and the
    one thing the front-end must **not** have is the credential mount:
    the internet-facing process never holds the Amplify secret on its
    filesystem, and in one container that separation would be a coding
    convention rather than a boundary.
"""
# '_number' below reads what the core's own reader reads, and says the
# same thing about it.  Sharing one would mean importing the core, and
# 'tests/test_bff_configuration.py' asserts the core never appears in
# this package's import graph.  The repetition is what that boundary
# costs.
# pylint: disable=duplicate-code

# Imports - Python Standard Library
from os import getenv
from pathlib import Path
from typing import Callable, TypeVar, Union

# Imports - Local
from ._exceptions import ConfigurationError

# What a setting below is read as.
Number = TypeVar('Number', int, float)


def _number(
        var_name: str,
        default: str,
        kind: Callable[[str], Number],
        description: str
) -> Number:
    """ Return a numeric setting, or say which one is unusable.

        Configuration arrives from the environment, so it is untrusted
        input.  'STAR_PASS_BFF_TIMEOUT_SECONDS=12O' with a letter O is
        a typo somebody makes once; left to 'float' it ends the import
        with a message naming neither the variable nor where to fix it.

        Args:
            var_name (str):
                Name of the environment variable to read.

            default (str):
                What to read when it is unset.

            kind (Callable[[str], Number]):
                What to read it as.

            description (str):
                How to describe an acceptable value.

        Raises:
            ConfigurationError:
                When the value cannot be read as that kind.

        Returns:
            value (Number):
                The number.
    """

    raw: Union[str, None] = getenv(var_name, default)

    try:
        return kind(raw)

    except (TypeError, ValueError) as error:
        raise ConfigurationError(
            f'{var_name} must be {description}, and is {raw!r}. It is '
            'read from the environment or the .env file at the '
            'repository root (see .env.example).'
        ) from error


# Where the API service is.  A configuration value rather than a
# constant, because encryption between the two is a deployment
# decision and never a code change: plain HTTP on a private
# network today, something else the day they are on separate hosts.
API_URL = getenv('STAR_PASS_API_URL', 'http://api:8000')

# What this service presents to the API.  Held here and never sent to
# a browser, which is the whole point of the pattern: cross-site
# scripting cannot exfiltrate a credential that is not there.
API_TOKEN = getenv('STAR_PASS_API_TOKEN')

# What the session cookie and the token derived from it are signed
# with.  Required, and checked at startup: a service that fell back to
# a generated key would log everybody out on restart and, worse, would
# not say that it had.
SESSION_SECRET = getenv('STAR_PASS_SESSION_SECRET')

# Shortest secret the service will start with, for the reason the API
# token has one: it is generated rather than typed.
SESSION_SECRET_MINIMUM_LENGTH = 32

# What the browser holds.  The session itself is HttpOnly, so script
# cannot read it; the token beside it is deliberately readable,
# because the page has to send it back in a header and a header is
# what an off-site form cannot set.
SESSION_COOKIE = 'star_pass_session'
CSRF_COOKIE = 'star_pass_csrf'
CSRF_HEADER = 'X-Star-Pass-CSRF'

# How long a session lasts without being used.  Short, and no
# remember-me: this is a tool somebody opens to do one operation a
# month, and a cookie that outlives the browser being closed is a
# cookie that outlives the person leaving the machine.
SESSION_MAX_AGE_SECONDS = _number(
    var_name='STAR_PASS_SESSION_MAX_AGE_SECONDS',
    default='43200',
    kind=int,
    description='a whole number of seconds'
)

# Whether the cookies say 'Secure'.  On by default and turned off only
# for local development over plain HTTP, because a browser will not
# store a Secure cookie from an insecure origin and the failure looks
# like the session silently not working.
COOKIES_ARE_SECURE = getenv(
    'STAR_PASS_COOKIES_SECURE',
    'true'
).strip().lower() not in ('false', 'no', '0')

# How much the service says about what it is doing.  The same
# variable the core reads, because a deployment sets one level and
# both containers answer to it.  Resolved in '_logging', which refuses
# a name that is not a level.
LOG_LEVEL = getenv(
    'LOG_LEVEL',
    'INFO'
)

# Where the API is reached through this service.  One prefix, so what
# is proxied is a statement rather than whatever a path happens to
# match.
API_PREFIX = '/api'

# How long to wait for the API on a request that is not a stream.
# Generous: the slow ones read Amplify.
REQUEST_TIMEOUT_SECONDS = _number(
    var_name='STAR_PASS_BFF_TIMEOUT_SECONDS',
    default='120',
    kind=float,
    description='a number of seconds'
)

# Where the page this service holds the session for is read from.
# The page is served here because it cannot work from anywhere else:
# the token a write carries is a cookie the page has to read, the
# session cookie is 'SameSite=Strict', and a write whose origin is not
# this host is refused.
#
# A configuration value rather than a constant, so a deployment can
# serve a built interface from a mounted directory without rebuilding
# the image.
WEB_ROOT = Path(
    getenv(
        'STAR_PASS_WEB_ROOT',
        str(
            Path(__file__).parent.parent.parent / 'web'
        )
    )
)

# What a request for the root is answered with.  Named, because the
# check that refuses to start without a page looks for this file and
# the mount serves it.
WEB_INDEX = 'index.html'

# The paths the page routes itself, each answered with the page.
#
# Enumerated, never a catch-all.  The mount answers a path that is not
# a file with 404, and that refusal is what says a module the page
# imports is missing; a blanket fallback would hand the browser HTML
# where it asked for JavaScript.  'tests/test_web_routes.py' holds
# this tuple to the table the page routes with.
#
# The root is here rather than left to the mount, so the list is the
# whole answer to "which paths are the page".
SCREEN_PATHS = (
    '/',
    '/runs',
    '/runs/{run_id}',
    '/runs/{run_id}/uncollected',
    '/runs/{run_id}/preview',
    '/settings'
)
