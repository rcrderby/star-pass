#!/usr/bin/env python3
""" star_pass_api default values.

    Separate from the core's '_defaults' because these describe the
    service rather than the domain: a path prefix and the addresses the
    documentation is served at mean nothing to the CLI, and the core
    must not acquire settings that only a server has.
"""

# Imports - Python Standard Library
from os import getenv

# Imports - Local
from __version__ import __version__

# The token every request is authenticated against.  From the
# environment and never a file or a command line flag: a flag is
# visible in the process table to every user on the host, and a path
# would need its own handling for a value that is one string (D3).
#
# The Amplify credential is a different thing and arrives differently
# (D9); this one is what a client presents to reach the service.
API_TOKEN = getenv('STAR_PASS_API_TOKEN')

# Shortest token the service will start with.  A static bearer token is
# the whole authentication boundary until an identity provider replaces
# it, and it is generated rather than typed, so there is no reason for
# a short one.
API_TOKEN_MINIMUM_LENGTH = 32

# Recorded against everything a caller changes (D13).  One value while
# the credential is a static token; the column it fills starts carrying
# real subjects when tokens are issued per identity, with no change to
# what writes it.
API_PRINCIPAL_ID = 'static-token'

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
