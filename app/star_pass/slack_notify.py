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
from typing import Any, Dict, List, Optional, Tuple

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
SLACK_SIGN_UP_PROMPT = _defaults.SLACK_SIGN_UP_PROMPT
SLACK_SUMMARY_EMOJI = _defaults.SLACK_SUMMARY_EMOJI
TITLE_SEPARATOR = _defaults.SLACK_TITLE_SEPARATOR

# Slack rejects button text longer than 75 characters.
BUTTON_TEXT_LIMIT = 75

# Module logger
logger = get_logger(__name__)


def _split_title(
        title: str
) -> Tuple[str, str]:
    """ Split an opportunity title into its event and role parts.

        Opportunity titles repeat the event across the roles that staff
        it ('Adult Scrimmages - Skating Officials', 'Adult Scrimmages -
        Non-Skating Officials').  Splitting on the separator groups
        those together and shortens each line to the part that differs,
        with no mapping file to maintain.  A title without the separator
        is its own group and keeps its full text.

        Args:
            title (str):
                The opportunity title.

        Returns:
            parts (Tuple[str, str]):
                The event name and the role label.  Both are the full
                title when it carries no separator.
    """

    event, separator, role = title.partition(TITLE_SEPARATOR)

    if not separator or not role.strip():
        return (title, title)

    return (event.strip(), role.strip())


def _group_needs(
        needs: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """ Group a summary's needs by event, merging shared time slots.

        Needs staffing the same event are shown together, and the shifts
        they share are merged onto one line per time slot so a reader
        sees every role for that hour at once.

        Args:
            needs (List[Dict[str, Any]]):
                Summary needs, each with 'title' and 'shifts' (see
                'amplify_responses.build_summary').

        Returns:
            groups (List[Dict[str, Any]]):
                One entry per event, ordered by its earliest shift, each
                with 'name' and 'slots'.  Each slot has 'when' and
                'entries' (label and filled count, in need order).
    """

    groups: Dict[str, Dict[str, Any]] = {}

    for need in needs:
        event, role = _split_title(title=need.get('title', 'Shifts'))
        group = groups.setdefault(
            event,
            {'name': event, 'slots': {}, 'needs': []}
        )
        group['needs'].append(need)

        for shift in need.get('shifts', []):
            # The label already encodes both start and end, so it keys
            # the slot; 'sort_key' orders slots across needs.
            when = shift.get('when', 'Time TBD')
            slot = group['slots'].setdefault(
                when,
                {
                    'when': when,
                    'sort_key': shift.get('sort_key', ''),
                    'entries': []
                }
            )
            slot['entries'].append(
                {
                    'label': role,
                    'filled': shift.get('filled', 0)
                }
            )

    # Order slots within a group, then groups by their earliest slot
    ordered = []
    for group in groups.values():
        slots = sorted(
            group['slots'].values(),
            key=lambda slot: slot['sort_key']
        )
        ordered.append(
            {
                'name': group['name'],
                'slots': slots,
                'needs': group['needs']
            }
        )

    ordered.sort(
        key=lambda group: group['slots'][0]['sort_key']
        if group['slots'] else ''
    )

    return ordered


def _format_group_text(
        group: Dict[str, Any]
) -> str:
    """ Format one event group as a Block Kit 'mrkdwn' string.

        Args:
            group (Dict[str, Any]):
                A group with 'name' and 'slots' (see '_group_needs').

        Returns:
            text (str):
                The event name in bold, then one line per time slot.
    """

    lines = [f'*{group["name"]}*']

    for slot in group['slots']:
        counts = []
        for entry in slot['entries']:
            # A title with no separator makes the label the event name,
            # so repeating it on the line would just be noise.
            if entry['label'] == group['name']:
                counts.append(f'{entry["filled"]} signed up')
            else:
                counts.append(f'{entry["filled"]} x {entry["label"]}')

        lines.append(f'{slot["when"]} - {", ".join(counts)}')

    return '\n'.join(lines)


def _heading_text(
        title: str
) -> str:
    """ Build the header text, flanked by the configured emoji.

        Args:
            title (str):
                The summary title.

        Returns:
            text (str):
                The title, wrapped in 'SLACK_SUMMARY_EMOJI' when set.
    """

    if not SLACK_SUMMARY_EMOJI:
        return title

    return f'{SLACK_SUMMARY_EMOJI} {title} {SLACK_SUMMARY_EMOJI}'


def build_summary_blocks(
        summary: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """ Build Slack Block Kit blocks from a sign-up summary.

        The message groups shifts by event, with one line per time slot
        listing every role's sign-up count, then closes with one
        sign-up button per opportunity.  Buttons sit at the end, one per
        'actions' block: several buttons in a single block wrap by
        client width, so a block each keeps them one per row.

        Args:
            summary (Dict[str, Any]):
                Summary data with the keys:

                    title (str):
                        Message heading.

                    as_of (str, optional):
                        Timestamp displayed in a context block.

                    needs (List[Dict], optional):
                        Per-need data, each with 'title', 'signup_url',
                        and 'shifts' (see
                        'amplify_responses.build_summary').

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
                'text': _heading_text(
                    title=summary.get('title', 'star-pass update')
                ),
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

    needs = summary.get('needs', [])
    groups = _group_needs(needs=needs)

    # One section per event, listing its time slots
    for group in groups:
        blocks.append(
            {
                'type': 'section',
                'text': {
                    'type': 'mrkdwn',
                    'text': _format_group_text(group=group)
                }
            }
        )

    # Buttons follow the same order as the sections above, so the
    # message reads consistently top to bottom.
    ordered_needs = [
        need
        for group in groups
        for need in group['needs']
    ]

    # Call to action, then one sign-up button per opportunity.  The
    # 'action_id' carries the loop index because Slack rejects duplicate
    # action_ids within a message.
    if needs:
        blocks.append(
            {
                'type': 'section',
                'text': {
                    'type': 'mrkdwn',
                    'text': SLACK_SIGN_UP_PROMPT
                }
            }
        )

    for index, need in enumerate(ordered_needs):
        signup_url = need.get('signup_url')
        if not signup_url:
            continue

        blocks.append(
            {
                'type': 'actions',
                'elements': [
                    {
                        'type': 'button',
                        'text': {
                            'type': 'plain_text',
                            # Slack rejects button text over 75
                            # characters, so a long title is trimmed.
                            'text': need.get(
                                'title',
                                SLACK_SIGN_UP_BUTTON_TEXT
                            )[:BUTTON_TEXT_LIMIT],
                            'emoji': True
                        },
                        'url': signup_url,
                        'action_id': f'signup_{index}'
                    }
                ]
            }
        )

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
    count = sum(
        len(need.get('shifts', []))
        for need in summary.get('needs', [])
    )

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
            # Redact before logging: the error carries the request that
            # produced it, which can include the bot token.
            detail = self.helpers.redact_secrets(error)
            message = f'Slack API error posting to {target}: {detail}'
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
                    The Slack API response, or None when the summary is
                    empty or the notifier is in check mode.
        """

        # A summary with no shifts is not worth posting.  The summary
        # covers a short day window, so an empty one means a day with
        # nothing scheduled -- routine, not an error.  Skipping in check
        # mode too keeps a dry run an accurate preview of a live run.
        if not summary.get('needs'):
            message = (
                'No shifts in the summary window; skipped posting to '
                'Slack.'
            )
            logger.info(message)
            self.helpers.printer(message=message)
            return None

        # Build the message payload from the summary data
        blocks = build_summary_blocks(summary=summary)
        text = _summary_fallback_text(summary=summary)

        return self.post(
            blocks=blocks,
            channel=channel,
            text=text
        )
