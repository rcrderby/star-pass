#!/usr/bin/env python3
""" star_pass exception types.

    The core raises these instead of exiting, so that the process that
    exits is the one that owns a process: the CLI turns them into a
    status code, and the API service will turn them into a response.

    The three subclasses are the distinctions a caller acts on
    differently -- fix the deployment, fix the data, or try again later
    -- rather than one class per failure.  A caller that wants every
    failure catches 'StarPassError'.
"""


class StarPassError(Exception):
    """ Base class for every error the core raises deliberately.

        An error of this type carries a message written for the person
        running the command: it names what failed and what to do about
        it.  Anything else reaching a caller is a defect.
    """


class ConfigurationError(StarPassError):
    """ The deployment is missing a value or holds an unusable one.

        Raised for a missing environment variable, a calendar that is
        not in the configuration, or configuration that is present but
        cannot be used.  Nothing the caller passes at run time fixes
        one; the environment or the data model has to change.
    """


class ValidationError(StarPassError):
    """ Supplied data cannot become a correct shift.

        Raised for a missing or empty input file, absent columns, a row
        with no need ID, and times or offsets that produce a shift
        ending at or before its start.  The run stops and names the
        rows rather than skipping them, because a missing shift is
        invisible until volunteers cannot sign up for it.
    """


class UpstreamError(StarPassError):
    """ A service the core depends on failed or answered unusably.

        Raised for a transport failure, a bad status code, or a body
        that is not the JSON it claims to be.  The message is the
        redacted summary; the detail belongs in the log, because an
        upstream body can carry a credential or a volunteer's data.
    """
