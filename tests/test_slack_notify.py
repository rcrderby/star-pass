""" Unit tests for star_pass.slack_notify.

    Slack is never contacted: the SlackNotifier is given a Mock client,
    and check-mode tests assert that no post is attempted.
"""
# pylint: disable=missing-function-docstring,missing-class-docstring
# pylint: disable=redefined-outer-name

# Imports - Python Standard Library
from unittest.mock import Mock

# Imports - Third-Party
import pytest

# Imports - Local
from star_pass.slack_notify import (
    SlackNotifier,
    build_summary_blocks,
    _format_shift_text,
)

# A fake bot value for live-post tests.  Bound to a non-secret-looking
# name and passed by reference so Bandit does not flag a string literal
# on a 'token=' argument (B106) or the assignment itself (B105).
FAKE_XOXB = 'xoxb-test'


@pytest.fixture
def summary() -> dict:
    # A two-shift summary; the second shift omits optional fields.
    return {
        'title': 'Scrimmage Sign-Ups',
        'as_of': '2026-07-06 12:00',
        'shifts': [
            {
                'name': 'Adult Scrimmage',
                'start': '2026-07-10 18:00',
                'end': '2026-07-10 20:45',
                'filled': 5,
                'slots': 8,
                'signup_url': 'https://example.org/need/1'
            },
            {
                'name': 'Juniors Scrimmage',
                'filled': 0,
                'slots': 8
            }
        ]
    }


class TestFormatShiftText:
    def test_includes_name_window_and_count(self):
        shift = {
            'name': 'Adult Scrimmage',
            'start': '2026-07-10 18:00',
            'end': '2026-07-10 20:45',
            'filled': 5,
            'slots': 8
        }
        text = _format_shift_text(shift)
        assert '*Adult Scrimmage*' in text
        assert '2026-07-10 18:00 - 2026-07-10 20:45' in text
        assert '5/8 filled' in text

    def test_tolerates_missing_fields(self):
        # No times and no slots -> placeholder window, bare count.
        text = _format_shift_text({'name': 'Mystery'})
        assert '*Mystery*' in text
        assert 'Time TBD' in text
        assert '0 filled' in text


class TestBuildSummaryBlocks:
    def test_header_context_and_divider(self, summary):
        blocks = build_summary_blocks(summary)
        assert blocks[0]['type'] == 'header'
        assert blocks[0]['text']['text'] == 'Scrimmage Sign-Ups'
        assert blocks[1]['type'] == 'context'
        assert 'As of 2026-07-06 12:00' in blocks[1]['elements'][0]['text']
        assert blocks[2] == {'type': 'divider'}

    def test_one_section_per_shift(self, summary):
        blocks = build_summary_blocks(summary)
        sections = [b for b in blocks if b['type'] == 'section']
        assert len(sections) == 2

    def test_link_button_only_when_signup_url(self, summary):
        blocks = build_summary_blocks(summary)
        sections = [b for b in blocks if b['type'] == 'section']
        # First shift has a signup_url -> link button with a URL.
        assert sections[0]['accessory']['type'] == 'button'
        assert sections[0]['accessory']['url'] == (
            'https://example.org/need/1'
        )
        assert sections[0]['accessory']['action_id'] == 'signup_0'
        # Second shift has no signup_url -> no accessory.
        assert 'accessory' not in sections[1]

    def test_omits_context_without_as_of(self):
        blocks = build_summary_blocks({'title': 'No Timestamp'})
        assert all(b['type'] != 'context' for b in blocks)


class TestSlackNotifierPost:
    def test_check_mode_does_not_post(self):
        client = Mock()
        notifier = SlackNotifier(
            channel='C123',
            check_mode=True,
            client=client
        )
        result = notifier.post(blocks=[{'type': 'divider'}])
        assert result is None
        client.chat_postMessage.assert_not_called()

    def test_live_post_calls_client(self):
        client = Mock()
        client.chat_postMessage.return_value = {'ok': True}
        notifier = SlackNotifier(
            channel='C123',
            check_mode=False,
            token=FAKE_XOXB,
            client=client
        )
        blocks = [{'type': 'divider'}]
        result = notifier.post(blocks=blocks, text='hello')
        assert result == {'ok': True}
        client.chat_postMessage.assert_called_once_with(
            channel='C123',
            blocks=blocks,
            text='hello'
        )

    def test_channel_argument_overrides_default(self):
        client = Mock()
        notifier = SlackNotifier(
            channel='C123',
            check_mode=False,
            token=FAKE_XOXB,
            client=client
        )
        notifier.post(blocks=[], channel='C999')
        _, kwargs = client.chat_postMessage.call_args
        assert kwargs['channel'] == 'C999'

    def test_missing_channel_raises(self):
        notifier = SlackNotifier(
            channel=None,
            check_mode=True,
            client=Mock()
        )
        # Instance channel resolves to None (no SLACK_CHANNEL in tests).
        notifier.channel = None
        with pytest.raises(ValueError):
            notifier.post(blocks=[])

    def test_live_post_without_token_raises(self):
        notifier = SlackNotifier(
            channel='C123',
            check_mode=False,
            token=FAKE_XOXB,
            client=Mock()
        )
        # Simulate a missing token at post time.
        notifier.token = None
        with pytest.raises(ValueError):
            notifier.post(blocks=[])

    def test_defaults_to_check_mode(self):
        notifier = SlackNotifier(client=Mock())
        assert notifier.check_mode is True


class TestPostSummary:
    def test_check_mode_builds_but_does_not_post(self, summary):
        client = Mock()
        notifier = SlackNotifier(
            channel='C123',
            check_mode=True,
            client=client
        )
        assert notifier.post_summary(summary=summary) is None
        client.chat_postMessage.assert_not_called()

    def test_live_summary_posts_blocks_and_fallback_text(self, summary):
        client = Mock()
        notifier = SlackNotifier(
            channel='C123',
            check_mode=False,
            token=FAKE_XOXB,
            client=client
        )
        notifier.post_summary(summary=summary)
        _, kwargs = client.chat_postMessage.call_args
        assert kwargs['channel'] == 'C123'
        assert kwargs['blocks'][0]['type'] == 'header'
        # Fallback text names the summary and the shift count.
        assert kwargs['text'] == 'Scrimmage Sign-Ups - 2 shift(s)'
