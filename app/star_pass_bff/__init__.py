#!/usr/bin/env python3
""" The front end's own service: session, CSRF, and a proxy (D4, D17).

    The browser reaches the star-pass API only through here, and holds
    **no** credential: this process keeps it server-side and attaches
    it to what it forwards, so cross-site scripting cannot exfiltrate
    a token that is not in the page.  Same origin, so there is no CORS
    configuration at all.

    A separate container from the API, with no credential mount on it:
    the internet-facing process never has the Amplify secret on its
    filesystem, and in one container that separation would be a coding
    convention rather than a boundary (D17).

    It holds **no domain logic** and imports nothing of the core.  What
    an answer means is the API's to say; this shapes requests, checks
    that writes came from its own page, and gets out of the way.

    Run it with:

        uvicorn --factory star_pass_bff:create_app
"""

# Imports - Local
from ._app import create_app

__all__ = ['create_app']
