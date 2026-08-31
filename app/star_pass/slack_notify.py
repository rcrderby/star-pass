#!/usr/local/bin/python3
""" Slack notification classes and methods.

    Builds Block Kit messages from a plain summary data structure and
    posts them to Slack with the Slack Web API (slack_sdk).  In a dry
    run ('check_mode') the message is built and displayed but no
    request is sent.
"""

# Imports - Python Standard Library
from os import getenv
from typing import Any, Dict, List, Optional, Tuple

# Imports - Third-Party
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# Imports - Local
from . import _defaults
from ._helpers import Helpers, load_env_file
from ._logging import get_logger
from . import _models
from ._reporting import Reporter

# Load environment variables
load_env_file()

# Constants
# Authentication (secret; read from the environment, never hard-coded)
SLACK_BOT_TOKEN = getenv(
    key='SLACK_BOT_TOKEN'
)

# Deployment configuration
SLACK_CHANNEL_ID = _defaults.SLACK_CHANNEL_ID
SLACK_DEV_CHANNEL_ID = _defaults.SLACK_DEV_CHANNEL_ID
SLACK_SIGN_UP_BUTTON_STYLE = _defaults.SLACK_SIGN_UP_BUTTON_STYLE
SLACK_SIGN_UP_BUTTON_SUFFIX = _defaults.SLACK_SIGN_UP_BUTTON_SUFFIX
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

        Opportunity titles repeat the event across the roles that
        staff it ('Adult Scrimmages: Skating Officials', 'Adult
        Scrimmages: Non-Skating Officials').  Splitting on the
        separator groups those and shortens each line to the part that
        differs.  A title without the separator is its own group and
        keeps its full text.

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


def _short_role(
        role: str
) -> str:
    """ Shorten a role using the role label model.

        Opportunity titles are written for the Amplify website, where
        there is room for them; a Slack button truncates them.  A role
        with no entry in the model keeps its full text.

        Args:
            role (str):
                The role as it appears in an opportunity title.

        Returns:
            label (str):
                The short label, or the role unchanged.
    """

    return _models.get_slack_role_labels().get(role, role)


def _build_rows(
        needs: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """ Build one display row per event and time slot.

        A row is an event at a time, with a count for each role
        staffing it.  Opportunities staffing the same event at the same
        time merge into one row.

        Rows are ordered by start time, then by where their
        opportunities appear in 'needs', so the caller controls the
        order.

        Args:
            needs (List[Dict[str, Any]]):
                Summary needs, each with 'title' and 'shifts' (see
                'amplify_responses.build_summary').

        Returns:
            rows (List[Dict[str, Any]]):
                One entry per event and time slot, each with 'event',
                'when', 'day', 'sort_key', and 'entries' (label and
                filled count, in need order).
    """

    rows: Dict[Any, Dict[str, Any]] = {}
    event_order: Dict[str, int] = {}

    for need in needs:
        event, role = _split_title(title=need.get('title', 'Shifts'))
        event_order.setdefault(event, len(event_order))

        for shift in need.get('shifts', []):
            sort_key = shift.get('sort_key', '')
            row = rows.setdefault(
                (sort_key, event),
                {
                    'event': event,
                    'when': shift.get('when', 'Time TBD'),
                    'day': shift.get('day', ''),
                    'sort_key': sort_key,
                    'entries': []
                }
            )
            row['entries'].append(
                {
                    'label': role,
                    'filled': shift.get('filled', 0)
                }
            )

    return sorted(
        rows.values(),
        key=lambda row: (row['sort_key'], event_order[row['event']])
    )


def _group_rows_by_day(
        rows: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """ Collect rows into the day each belongs to, preserving order.

        Args:
            rows (List[Dict[str, Any]]):
                Display rows in order (see '_build_rows').

        Returns:
            days (List[Dict[str, Any]]):
                One entry per day, each with 'day' and 'rows'.
    """

    days: Dict[str, Dict[str, Any]] = {}

    for row in rows:
        day = days.setdefault(
            row['day'],
            {'day': row['day'], 'rows': []}
        )
        day['rows'].append(row)

    return list(days.values())


def _format_count(
        entry: Dict[str, Any],
        event: str
) -> str:
    """ Format one role's sign-up count for a row.

        Args:
            entry (Dict[str, Any]):
                A row entry with 'label' and 'filled'.

            event (str):
                The row's event name.

        Returns:
            count (str):
                The count and its label, shortened where the role label
                model has an entry, and singular when exactly one
                volunteer signed up.
    """

    filled = entry['filled']
    label = entry['label']

    if label == event:
        # A title with no separator makes the label the event name, so
        # repeating it on the line would be noise; name the role
        # generically instead.
        label = _models.get_slack_default_role_label()
    else:
        label = _short_role(role=label)

    # Shortening happens first so that the singular rule sees the label
    # a reader will: 'SOs' gives '1 x SO', not '1 x Skating Official'.
    #
    # One volunteer is an Official, not Officials.  'ss' endings (Class)
    # are left alone; an irregular plural would need spelling out in the
    # role label model rather than abbreviating.
    if filled == 1 and label.endswith('s') and not label.endswith('ss'):
        label = label[:-1]

    return f'{filled} x {label}'


def _bold(
        text: str
) -> Dict[str, Any]:
    """ Build a bold 'rich_text' span.

        Args:
            text (str):
                The text to embolden.

        Returns:
            element (Dict[str, Any]):
                A 'rich_text' text element styled bold.
    """

    return {
        'type': 'text',
        'text': text,
        'style': {'bold': True}
    }


def _build_day_elements(
        day: Dict[str, Any],
        show_heading: bool
) -> List[Dict[str, Any]]:
    """ Build one day's rows as Block Kit 'rich_text' elements.

        The styling is carried by explicit spans rather than 'mrkdwn'
        markup: Slack reads a ':...:' pair as an emoji shortcode
        candidate, which breaks a bold run wrapping a time range.
        Every time range holds two colons, so no markup spelling avoids
        it; a styled span is not parsed and renders the same on every
        client.

        Args:
            day (Dict[str, Any]):
                A day with 'day' and 'rows' (see '_group_rows_by_day').

            show_heading (bool):
                Whether to lead with the date.  A single-day summary
                omits it, because the title already names the day.

        Returns:
            elements (List[Dict[str, Any]]):
                The day's rows, each an event and time in bold followed
                by one line per role.
    """

    elements: List[Dict[str, Any]] = []

    if show_heading is True and day['day']:
        elements.append(_bold(text=day['day']))
        elements.append({'type': 'text', 'text': '\n\n'})

    last_row = len(day['rows']) - 1
    for index, row in enumerate(day['rows']):
        counts = '\n'.join(
            _format_count(entry=entry, event=row['event'])
            for entry in row['entries']
        )
        # A blank line separates rows, but not after the final one,
        # which would pad the bottom of the day.
        gap = '\n\n' if index < last_row else ''
        elements.append(_bold(text=f'{row["event"]} {row["when"]}'))
        elements.append({'type': 'text', 'text': f'\n{counts}{gap}'})

    return elements


def _build_summary_elements(
        days: List[Dict[str, Any]],
        show_headings: bool
) -> List[Dict[str, Any]]:
    """ Build every day's rows as one run of 'rich_text' elements.

        The days share a single block, so the spacing between them is
        set here.  Adjacent 'rich_text' blocks sit closer together than
        a blank line, which puts a new date nearer the previous day's
        rows than its own.

        Args:
            days (List[Dict[str, Any]]):
                Days in order (see '_group_rows_by_day').

            show_headings (bool):
                Whether each day leads with its date.

        Returns:
            elements (List[Dict[str, Any]]):
                The days in order, separated by a wider gap than the
                one between rows.
    """

    elements: List[Dict[str, Any]] = []

    for day in days:
        day_elements = _build_day_elements(
            day=day,
            show_heading=show_headings
        )
        if not day_elements:
            continue

        if elements:
            # Two blank lines set a new date apart; one is the gap
            # between rows and would read as just another row.
            elements.append({'type': 'text', 'text': '\n\n\n'})

        elements.extend(day_elements)

    return elements


def _event_position(
        need: Dict[str, Any],
        rows: List[Dict[str, Any]]
) -> int:
    """ Return where a need's event first appears among the rows.

        Args:
            need (Dict[str, Any]):
                A summary need with a 'title'.

            rows (List[Dict[str, Any]]):
                Display rows in order (see '_build_rows').

        Returns:
            position (int):
                The index of the first row for the need's event, or the
                row count when the need has no rows, which sorts it
                last.
    """

    event, _role = _split_title(title=need.get('title', 'Shifts'))

    for index, row in enumerate(rows):
        if row['event'] == event:
            return index

    return len(rows)


def _button_text(
        title: str
) -> str:
    """ Build a sign-up button's label.

        The role is shortened, because Slack truncates a button that
        outgrows its width.  The configured suffix marks that the
        button opens a browser rather than acting inside Slack.

        The suffix is plain text rather than an emoji shortcode, which
        Slack renders as a full emoji tile that crowds out the label on
        a narrow button.

        Args:
            title (str):
                The opportunity title.

        Returns:
            text (str):
                The shortened title and the suffix, trimmed so that the
                whole label stays inside Slack's 75-character limit.
    """

    event, role = _split_title(title=title)

    # A title with no role is its own event, so there is nothing to
    # rejoin and nothing to shorten.
    if role == title:
        label = title
    else:
        label = f'{event}{TITLE_SEPARATOR}{_short_role(role=role)}'

    # Trim the label, never the suffix: a button losing its arrow to a
    # long opportunity title would be the wrong thing to drop.
    room = BUTTON_TEXT_LIMIT - len(SLACK_SIGN_UP_BUTTON_SUFFIX)

    return f'{label[:room].rstrip()}{SLACK_SIGN_UP_BUTTON_SUFFIX}'


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

        Shifts are grouped by event, one line per time slot listing
        every role's sign-up count, closing with one sign-up button per
        opportunity.  Buttons sit one per 'actions' block: several in
        one block wrap by client width.

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
    rows = _build_rows(needs=needs)

    # One block for the whole list, rather than one per row: Slack caps
    # a message at 50 blocks, which a week-long window would approach a
    # row at a time.  Holding the days together also keeps the spacing
    # between them under this module's control.
    summary_elements = _build_summary_elements(
        days=_group_rows_by_day(rows=rows),
        show_headings=summary.get('multi_day', False)
    )
    if summary_elements:
        blocks.append(
            {
                'type': 'rich_text',
                'elements': [
                    {
                        'type': 'rich_text_section',
                        'elements': summary_elements
                    }
                ]
            }
        )

    # Buttons follow the order the events appear above, so the message
    # reads consistently top to bottom.
    ordered_needs = sorted(
        needs,
        key=lambda need: _event_position(
            need=need,
            rows=rows
        )
    )

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

        button: Dict[str, Any] = {
            'type': 'button',
            'text': {
                'type': 'plain_text',
                'text': _button_text(title=need.get('title', 'Sign up')),
                'emoji': True
            },
            'url': signup_url,
            'action_id': f'signup_{index}'
        }

        # An empty style is invalid; Slack expects the key to be absent
        # for a default button.
        if SLACK_SIGN_UP_BUTTON_STYLE:
            button['style'] = SLACK_SIGN_UP_BUTTON_STYLE

        blocks.append(
            {
                'type': 'actions',
                'elements': [button]
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
            client: Optional[WebClient] = None,
            reporter: Optional[Reporter] = None
    ) -> None:
        """ Class initialization method.

            Args:
                channel (str, optional):
                    Destination channel ID.  Defaults to the
                    'SLACK_CHANNEL_ID' environment value.

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

                reporter (Reporter, optional):
                    Receives progress and result events.  Defaults to
                    None, which discards them.

            Returns:
                None.
        """

        # Initialize helper methods
        self.helpers = Helpers()

        # Report progress nowhere unless the caller supplies a
        # destination
        self.reporter = reporter if reporter is not None else Reporter()

        # Determine the value of 'check_mode' (dry run)
        if isinstance(check_mode, bool) is True:
            self.check_mode = check_mode
        else:
            self.check_mode = self.helpers.convert_to_bool(check_mode)

        # Resolve the token and destination channel
        self.token = token if token is not None else SLACK_BOT_TOKEN
        self.channel = channel if channel is not None else SLACK_CHANNEL_ID

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
                'No Slack channel configured; set SLACK_CHANNEL_ID or '
                'pass a channel argument.'
            )
            logger.error(message)
            raise ValueError(message)

        # Dry run: report the payload and skip the API request
        if self.check_mode is True:
            self.reporter.slack_dry_run(payload=blocks)
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
            self.reporter.summary_skipped()
            return None

        # Build the message payload from the summary data
        blocks = build_summary_blocks(summary=summary)
        text = _summary_fallback_text(summary=summary)

        return self.post(
            blocks=blocks,
            channel=channel,
            text=text
        )
