#!/usr/bin/env python3
""" What the front-end service was configured with.

    Its own settings, separate from the API service's, because the two
    are separate containers with separate environments (D17) and the
    one thing the front-end must **not** have is the credential mount:
    the internet-facing process never holds the Amplify secret on its
    filesystem, and in one container that separation would be a coding
    convention rather than a boundary.
"""

# Imports - Python Standard Library
from os import getenv
from pathlib import Path

# Where the API service is.  A configuration value rather than a
# constant, because encryption between the two is a deployment
# decision and never a code change (D6): plain HTTP on a private
# network today, something else the day they are on separate hosts.
API_URL = getenv('STAR_PASS_API_URL', 'http://api:8000')

# What this service presents to the API.  Held here and never sent to
# a browser, which is the whole point of the pattern: cross-site
# scripting cannot exfiltrate a credential that is not there (D4).
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
SESSION_MAX_AGE_SECONDS = int(
    getenv(
        'STAR_PASS_SESSION_MAX_AGE_SECONDS',
        '43200'
    )
)

# Whether the cookies say 'Secure'.  On by default and turned off only
# for local development over plain HTTP, because a browser will not
# store a Secure cookie from an insecure origin and the failure looks
# like the session silently not working.
COOKIES_ARE_SECURE = getenv(
    'STAR_PASS_COOKIES_SECURE',
    'true'
).strip().lower() not in ('false', 'no', '0')

# Where the API is reached through this service.  One prefix, so what
# is proxied is a statement rather than whatever a path happens to
# match.
API_PREFIX = '/api'

# How long to wait for the API on a request that is not a stream.
# Generous: the slow ones read Amplify.
REQUEST_TIMEOUT_SECONDS = float(
    getenv(
        'STAR_PASS_BFF_TIMEOUT_SECONDS',
        '120'
    )
)

# Where the page this service holds the session for is read from.
# The page is served here rather than from anywhere else because it
# cannot work from anywhere else: the token a write carries is a
# cookie the page has to read, the session cookie is 'SameSite=Strict'
# so a browser sends it on nothing another site initiated, and a write
# whose origin is not this host is refused (D4, D18).  A page on a
# second origin would fail all three, and answering that with CORS
# would be the boundary leaking rather than moving.
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

# The paths the page routes itself (D28), each answered with the page.
#
# **Enumerated, and never a catch-all.**  The page is mounted with
# 'html=True', which answers a path that is not a file with 404 -- and
# that refusal is what says a module the page imports is missing.  A
# blanket fallback would answer a mistyped module path with the page
# and a 200, so the browser would be handed HTML where it asked for
# JavaScript, and the screen would silently never draw.  Enumerating
# costs this tuple; 'tests/test_web_routes.py' holds it to the table
# the page routes with, because a path one of them knows and the other
# does not is a screen that works until somebody reloads it.
#
# The root is here rather than left to the mount so that the list is
# the whole answer to "which paths are the page".
SCREEN_PATHS = (
    '/',
    '/runs',
    '/runs/{run_id}',
    '/runs/{run_id}/uncollected',
    '/runs/{run_id}/preview',
    '/settings'
)
