#!/usr/bin/env python3
""" Reading an Amplify opportunity, and where it is published.

    Below both callers.  Collection resolves an opportunity's title
    once and stores it on the run, because every review row is
    labelled with one and a lookup deferred to preview time would
    leave the screen unable to name anything; the shift preview reads
    the same title while reporting what it would create.  Asked in two
    places, the two could disagree about what a missing title reads as.

    The address is built rather than read.  It is the public page a
    volunteer signs up on, which the API's own response does not
    carry, and it is one configured base plus the need ID.
"""

# Imports - Local
from . import _defaults
from ._helpers import amplify_headers, Helpers

# Constants
AMPLIFY_NEED_DETAIL_URL = _defaults.AMPLIFY_NEED_DETAIL_URL
BASE_AMPLIFY_URL = _defaults.BASE_AMPLIFY_URL
HTTP_TIMEOUT = _defaults.HTTP_TIMEOUT

# What an opportunity is called when Amplify answers without a title.
# Named rather than left empty: a row labelled with nothing reads as a
# rendering fault, and this reads as what it is.
UNKNOWN_TITLE = 'Unknown'


def read_title(
        helpers: Helpers,
        need_id: str | int,
        timeout: int = HTTP_TIMEOUT
) -> str:
    """ Return an opportunity's title, as Amplify has it.

        Args:
            helpers (Helpers):
                What the request is sent through.

            need_id (str | int):
                Amplify need ID to look up.

            timeout (int, optional):
                HTTP timeout.  Defaults to the configured value.

        Raises:
            UpstreamError:
                If Amplify cannot be reached or refuses the request.

        Returns:
            title (str):
                The opportunity's title, or 'UNKNOWN_TITLE' when the
                answer carries none.
    """

    response = helpers.send_api_request(
        api_request_data={
            'method': 'GET',
            'url': f'{BASE_AMPLIFY_URL}/needs/{need_id}',
            'headers': amplify_headers(),
            'json': None,
            'timeout': timeout
        },
        display_request_status=False
    )

    # Guarding a body that is not JSON and an answer with no 'data'.
    return helpers.response_json(response).get('data', {}).get(
        'need_title',
        UNKNOWN_TITLE
    )


def public_url(
        need_id: str | int
) -> str:
    """ Return where an opportunity is published.

        Args:
            need_id (str | int):
                Amplify need ID.

        Returns:
            url (str):
                The page a volunteer signs up on.
    """

    return f'{AMPLIFY_NEED_DETAIL_URL}{need_id}'
