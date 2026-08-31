#!/usr/bin/env python3
""" What the front-end service raises when it cannot run.

    Its own, rather than the core's: the internet-facing process
    imports nothing of the domain, and a test holds the import graph
    to that.
"""


class ConfigurationError(Exception):
    """ The service cannot run on what it was given. """
