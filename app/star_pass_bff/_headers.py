#!/usr/bin/env python3
""" The policy the page is served under, set by the service itself.

    The Caddyfile sets the same three headers, and two copies is the
    arrangement rather than an oversight: a policy that arrives only
    from the proxy is one the deployment happens to have rather than
    one the application holds.  'docs/deployment.md' documents running
    both services under bare uvicorn, and in that mode there is no
    Caddy and there would be no policy at all.

    The policy is load-bearing rather than decorative.  It makes
    'href: opportunity.url' in 'web/js/review/table.js' safe against a
    'javascript:' value arriving from upstream, and it is what leaves
    the page no route out.

    Two copies that can drift will, so a test holds this module and
    the Caddyfile to each other, for the reason 'test_web_routes.py'
    holds the page's route table and the service's to each other.
"""

# Imports - Python Standard Library
from typing import Awaitable, Callable, Dict

# Imports - Third-Party
from fastapi import FastAPI, Request, Response

# What the page is allowed to load, and from where.  It loads no
# third-party script, style, font or image, and talks to no origin but
# its own.  No 'unsafe-inline': the script and the stylesheet are
# files, which is what lets this be strict rather than decorative.
#
# 'form-action' is here rather than left to 'default-src', which it
# does not fall back to: without it named, a form on this page may
# submit anywhere.  Nothing here posts a form, so the answer is none.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "connect-src 'self'; "
    "img-src 'self' data:; "
    "base-uri 'none'; "
    "form-action 'none'; "
    "frame-ancestors 'none'"
)

# The whole policy, by header name.  Read by the middleware below and
# by the test that holds this file and the Caddyfile to each other.
SECURITY_HEADERS: Dict[str, str] = {
    'Content-Security-Policy': CONTENT_SECURITY_POLICY,
    # A response typed 'application/json' is never run as script,
    # whatever the browser would otherwise guess it was.
    'X-Content-Type-Options': 'nosniff',
    # A path here names a run, an event or a person; there is nowhere
    # off-site to send it to, and no reason to offer.
    'Referrer-Policy': 'same-origin'
}


def add_security_headers(
        api: FastAPI
) -> None:
    """ Set the policy on every response the service makes.

        On every response rather than on the page alone: a module, a
        stylesheet and a proxied answer are all things a browser is
        given, and a header set in one place is one rule rather than
        a list of exceptions.

        Args:
            api (FastAPI):
                The application to set them on.

        Returns:
            None.
    """

    @api.middleware('http')
    async def _set_security_headers(
            _request: Request,
            call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """ Answer, then say what the answer may do. """
        response = await call_next(_request)

        for name, value in SECURITY_HEADERS.items():
            response.headers[name] = value

        return response

    return None
