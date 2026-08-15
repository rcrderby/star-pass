#!/usr/bin/env python3
""" star_pass_api default values.

    Separate from the core's '_defaults' because these describe the
    service rather than the domain: a path prefix and the addresses the
    documentation is served at mean nothing to the CLI, and the core
    must not acquire settings that only a server has.
"""

# Imports - Local
from __version__ import __version__

# The path every endpoint lives under.  Versioned in the path so a
# breaking change can be served alongside what it breaks, rather than
# replacing it (D15).  Changes within a version are additive only.
API_VERSION_PREFIX = '/v1'

# Service metadata, which becomes the 'info' section of the generated
# specification.
API_TITLE = 'star-pass'
API_VERSION = __version__
API_SUMMARY = 'Bulk volunteer shift operations for the Rose City Rollers.'
API_DESCRIPTION = (
    'The remote surface over the star-pass core. Everything the web '
    'interface can do is reachable here, and the command line client '
    'can do anything the web interface can.'
)

# Documentation addresses.  The documentation user interfaces are open
# while every endpoint requires authentication: the shape of an API is
# not a secret, and a reader who cannot try a call learns less for no
# gain in safety (D15).
API_DOCS_PATH = '/docs'
API_REDOC_PATH = '/redoc'
API_OPENAPI_PATH = f'{API_VERSION_PREFIX}/openapi.json'

# Tags, so the generated documentation groups endpoints by what they
# are for rather than listing them in definition order.
API_TAG_SERVICE = 'service'
