#!/usr/local/bin/python3
""" Slack notification classes and methods.

    Builds Block Kit messages from a plain summary data structure and
    posts them to Slack with the Slack Web API (slack_sdk).  A dry-run
    ('check_mode') mirrors the CreateShifts pattern: the message is
    built and displayed but no request is sent.
"""

# Imports - Python Standard Library
from json import dumps
from os import getenv
from typing import Any, Dict, List, Optional

# Imports - Third-Party
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# Imports - Local
from . import _defaults
from ._helpers import Helpers, load_env_file
from ._logging import get_logger

# Load environment variables
load_env_file()

# Constants
# Authentication (secret; read from the environment, never hard-coded)
SLACK_BOT_TOKEN = getenv(
    key='SLACK_BOT_TOKEN'
)

# Deployment configuration
SLACK_CHANNEL = _defaults.SLACK_CHANNEL
SLACK_DEV_CHANNEL = _defaults.SLACK_DEV_CHANNEL
SLACK_CHECK_MODE_MESSAGE = _defaults.SLACK_CHECK_MODE_MESSAGE
SLACK_SIGN_UP_BUTTON_TEXT = _defaults.SLACK_SIGN_UP_BUTTON_TEXT

# Module logger
logger = get_logger(__name__)


def _format_shift_text(
        shift: Dict[str, Any]
) -> str:
    """ Format a single shift as a Block Kit 'mrkdwn' string.

        Args:
            shift (Dict[str, Any]):
                Shift summary data.  Recognized keys: 'name', 'start',
                'end', 'filled', and 'slots'.

        Returns:
            text (str):
                A 'mrkdwn' string with the shift name, time window, and
                filled/available count.
    """

    # Collect the shift fields, tolerating missing values
    name = shift.get('name', 'Shift')
    start = shift.get('start')
    end = shift.get('end')
    filled = shift.get('filled', 0)
    slots = shift.get('slots')

    # Build the time window portion when start/end are present
    if start and end:
        when = f'{start} - {end}'
    else:
        when = start or end or 'Time TBD'

    # Build the filled/available count portion
    if slots is not None:
        count = f'{filled}/{slots} filled'
    else:
        count = f'{filled} filled'

    return f'*{name}*\n{when}\n{count}'


def build_summary_blocks(
        summary: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """ Build Slack Block Kit blocks from a sign-up summary.

        Args:
            summary (Dict[str, Any]):
                Summary data with the keys:

                    title (str):
                        Message heading.

                    as_of (str, optional):
                        Timestamp displayed in a context block.

                    shifts (List[Dict], optional):
                        Per-shift data (see '_format_shift_text').  When
                        a shift includes a 'signup_url', a link button is
                        attached to that shift's section.

        Returns:
            blocks (List[Dict[str, Any]]):
                A list of Block Kit block dictionaries.
    """

    # Header block with the summary title
    blocks: List[Dict[str, Any]] = [
        {
            'type': 'header',
            'text': {
                'type': 'plain_text',
                'text': summary.get('title', 'star-pass update'),
                'emoji': True
            }
        }
    ]

    # Optional context block noting when the data was collected
    as_of = summary.get('as_of')
    if as_of:
        blocks.append(
            {
                'type': 'context',
                'elements': [
                    {
                        'type': 'mrkdwn',
                        'text': f'As of {as_of}'
                    }
                ]
            }
        )

    # Separate the heading from the shift list
    blocks.append({'type': 'divider'})

    # One section per shift, with an optional sign-up link button.  The
    # button 'action_id' includes the loop index to stay unique within
    # the message (Slack rejects duplicate action_ids).
    for index, shift in enumerate(summary.get('shifts', [])):
        section: Dict[str, Any] = {
            'type': 'section',
            'text': {
                'type': 'mrkdwn',
                'text': _format_shift_text(shift)
            }
        }

        signup_url = shift.get('signup_url')
        if signup_url:
            section['accessory'] = {
                'type': 'button',
                'text': {
                    'type': 'plain_text',
                    'text': SLACK_SIGN_UP_BUTTON_TEXT,
                    'emoji': True
                },
                'url': signup_url,
                'action_id': f'signup_{index}'
            }

        blocks.append(section)

    return blocks


def _summary_fallback_text(
        summary: Dict[str, Any]
) -> str:
    """ Build plain-text fallback for a summary message.

        Slack uses the top-level 'text' for notifications and
        accessibility when a message is composed of blocks.

        Args:
            summary (Dict[str, Any]):
                Summary data (see 'build_summary_blocks').

        Returns:
            text (str):
                A short plain-text description of the message.
    """

    title = summary.get('title', 'star-pass update')
    count = len(summary.get('shifts', []))

    return f'{title} - {count} shift(s)'


class SlackNotifier:
    """ Build and post Slack messages via the Slack Web API. """

    def __init__(
            self,
            channel: Optional[str] = None,
            check_mode: bool = True,
            token: Optional[str] = None,
            client: Optional[WebClient] = None
    ) -> None:
        """ Class initialization method.

            Args:
                channel (str, optional):
                    Destination channel ID.  Defaults to the
                    'SLACK_CHANNEL' environment value.

                check_mode (bool, optional):
                    When True (default), messages are built and
                    displayed but not sent -- a dry run.

                token (str, optional):
                    Slack bot token.  Defaults to the 'SLACK_BOT_TOKEN'
                    environment value.

                client (WebClient, optional):
                    Pre-built Slack Web API client.  Primarily an
                    injection point for tests; when omitted a client is
                    created from 'token'.

            Returns:
                None.
        """

        # Initialize helper methods
        self.helpers = Helpers()

        # Determine the value of 'check_mode' (dry run)
        if isinstance(check_mode, bool) is True:
            self.check_mode = check_mode
        else:
            self.check_mode = self.helpers.convert_to_bool(check_mode)

        # Resolve the token and destination channel
        self.token = token if token is not None else SLACK_BOT_TOKEN
        self.channel = channel if channel is not None else SLACK_CHANNEL

        # Slack Web API client (injectable for tests).  Constructing a
        # WebClient performs no network request, so this is safe even in
        # check mode or without a token.
        if client is not None:
            self.client = client
        else:
            self.client = WebClient(token=self.token)

        return None

    def post(
            self,
            blocks: List[Dict[str, Any]],
            channel: Optional[str] = None,
            text: Optional[str] = None
    ) -> Optional[Any]:
        """ Post Block Kit blocks to a Slack channel.

            Args:
                blocks (List[Dict[str, Any]]):
                    Block Kit blocks to post.

                channel (str, optional):
                    Destination channel ID.  Defaults to the instance
                    channel.

                text (str, optional):
                    Plain-text fallback used for notifications and
                    accessibility.

            Raises:
                ValueError:
                    If no destination channel is configured, or a live
                    post is attempted without a bot token.

                slack_sdk.errors.SlackApiError:
                    If the Slack Web API returns an error.

            Returns:
                response (Any | None):
                    The Slack API response, or None in check mode.
        """

        # Resolve the destination channel
        target = channel if channel is not None else self.channel

        # A destination channel is required in every mode
        if not target:
            message = (
                'No Slack channel configured; set SLACK_CHANNEL or '
                'pass a channel argument.'
            )
            logger.error(message)
            raise ValueError(message)

        # Dry run: display the payload and skip the API request
        if self.check_mode is True:
            self.helpers.printer(message=SLACK_CHECK_MODE_MESSAGE)
            self.helpers.printer(message=dumps(blocks, indent=2))
            message = f'Slack check mode: skipped posting to {target}'
            logger.info(message)
            return None

        # A bot token is required for a live post
        if not self.token:
            message = (
                'SLACK_BOT_TOKEN is not set; cannot post to Slack.'
            )
            logger.error(message)
            raise ValueError(message)

        # Send the message, surfacing Slack API errors to the caller
        try:
            response = self.client.chat_postMessage(
                channel=target,
                blocks=blocks,
                text=text or 'star-pass update'
            )
        except SlackApiError as error:
            message = f'Slack API error posting to {target}: {error}'
            logger.error(message)
            raise

        message = f'Posted Slack message to {target}'
        logger.info(message)

        return response

    def post_summary(
            self,
            summary: Dict[str, Any],
            channel: Optional[str] = None
    ) -> Optional[Any]:
        """ Build and post a sign-up summary message.

            Args:
                summary (Dict[str, Any]):
                    Summary data (see 'build_summary_blocks').

                channel (str, optional):
                    Destination channel ID.  Defaults to the instance
                    channel.

            Returns:
                response (Any | None):
                    The Slack API response, or None in check mode.
        """

        # Build the message payload from the summary data
        blocks = build_summary_blocks(summary=summary)
        text = _summary_fallback_text(summary=summary)

        return self.post(
            blocks=blocks,
            channel=channel,
            text=text
        )
