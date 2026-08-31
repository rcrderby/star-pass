#!/usr/bin/env python3
""" The remote surface over the star-pass core.

    A separate package from 'star_pass', not a module inside it.  The
    core holds the domain logic and knows nothing about HTTP; this
    package knows about HTTP and holds no domain logic.  Putting the
    two together is the thing the design is arranged to prevent, and
    the boundary is only real while they are separate imports.

    The command line client calls the core directly and needs no server
    running, so nothing here may become the only way to reach
    something the core can do.

    Run it with:

        uvicorn --factory star_pass_api:create_app
"""

# Imports - Local
from ._app import create_app

__all__ = ['create_app']
