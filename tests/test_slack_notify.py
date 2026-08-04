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
from star_pass import slack_notify
from star_pass.slack_notify import (
    SlackNotifier,
    build_summary_blocks,
    _build_rows,
    _format_count,
    _format_day_text,
    _group_rows_by_day,
    _split_title,
)

# A fake bot value for live-post tests.  Bound to a non-secret-looking
# name and passed by reference so Bandit does not flag a string literal
# on a 'token=' argument (B106) or the assignment itself (B105).
FAKE_XOXB = 'xoxb-test'


@pytest.fixture
def summary() -> dict:
    # The 12/17 scrimmage night: two events, four opportunities, with
    # the adult event running two back-to-back slots.
    def _need(title, url, slots):
        return {
            'title': title,
            'signup_url': url,
            'shifts': [
                {
                    'when': when,
                    'day': 'Wednesday, December 17',
                    'sort_key': sort_key,
                    'filled': filled
                }
                for when, sort_key, filled in slots
            ]
        }

    adult = [
        ('7:00-8:00 p.m.', '2025-12-17 19:00:00', 1),
        ('8:00-9:00 p.m.', '2025-12-17 20:00:00', 1),
    ]
    adult_skating = [
        ('7:00-8:00 p.m.', '2025-12-17 19:00:00', 4),
        ('8:00-9:00 p.m.', '2025-12-17 20:00:00', 3),
    ]

    return {
        'title': 'Shift sign-ups for Wednesday, December 17 2025',
        'as_of': '4:50 p.m. on Wednesday, December 17 2025',
        'multi_day': False,
        'needs': [
            _need(
                'Adult Scrimmages: Non-Skating Officials',
                'https://example.org/need/1',
                adult
            ),
            _need(
                'Adult Scrimmages: Skating Officials',
                'https://example.org/need/2',
                adult_skating
            ),
            _need(
                'Juniors Scrimmages: Non-Skating Officials',
                'https://example.org/need/3',
                [('6:00-7:00 p.m.', '2025-12-17 18:00:00', 4)]
            ),
            _need(
                'Juniors Scrimmages: Skating Officials',
                'https://example.org/need/4',
                [('6:00-7:00 p.m.', '2025-12-17 18:00:00', 6)]
            ),
        ]
    }


class TestSplitTitle:
    def test_default_separator_matches_amplify_titles(self):
        # Live titles read 'Adult Scrimmages: Skating Officials'.
        assert slack_notify.TITLE_SEPARATOR == ': '

    def test_splits_on_the_separator(self):
        event, role = _split_title('Adult Scrimmages: Skating Officials')
        assert event == 'Adult Scrimmages'
        assert role == 'Skating Officials'

    def test_title_without_a_separator_is_its_own_group(self):
        # Nothing to shorten, so the full title is used for both.
        event, role = _split_title('Bout Day Volunteers')
        assert event == 'Bout Day Volunteers'
        assert role == 'Bout Day Volunteers'

    def test_empty_role_falls_back_to_the_full_title(self):
        event, role = _split_title('Trailing Separator: ')
        assert event == 'Trailing Separator: '
        assert role == 'Trailing Separator: '

    def test_only_the_first_separator_splits(self):
        event, role = _split_title('Adult: Skating: Crew Chief')
        assert event == 'Adult'
        assert role == 'Skating: Crew Chief'


class TestBuildRows:
    def test_orders_rows_by_start_time(self, summary):
        rows = _build_rows(summary['needs'])
        # Juniors run first that night, so their row leads even though
        # the adult opportunities are listed first.
        assert [(row['event'], row['when']) for row in rows] == [
            ('Juniors Scrimmages', '6:00-7:00 p.m.'),
            ('Adult Scrimmages', '7:00-8:00 p.m.'),
            ('Adult Scrimmages', '8:00-9:00 p.m.')
        ]

    def test_merges_roles_staffing_the_same_slot(self, summary):
        rows = _build_rows(summary['needs'])
        # One row for the juniors hour, carrying both roles' counts in
        # the order their opportunities were given.
        assert [
            (entry['label'], entry['filled'])
            for entry in rows[0]['entries']
        ] == [
            ('Non-Skating Officials', 4),
            ('Skating Officials', 6)
        ]

    def test_same_time_events_follow_the_need_order(self):
        # The tie-break a reader can control: the order of the need IDs.
        def _need(title, filled):
            return {
                'title': title,
                'signup_url': 'https://example.org/need/1',
                'shifts': [
                    {
                        'when': '6:00-7:00 p.m.',
                        'day': 'Wednesday, December 17',
                        'sort_key': '2025-12-17 18:00:00',
                        'filled': filled
                    }
                ]
            }

        rows = _build_rows(
            [
                _need('Adult Scrimmages: Skating Officials', 1),
                _need('Juniors Scrimmages: Skating Officials', 2)
            ]
        )
        assert [row['event'] for row in rows] == [
            'Adult Scrimmages',
            'Juniors Scrimmages'
        ]

        reversed_rows = _build_rows(
            [
                _need('Juniors Scrimmages: Skating Officials', 2),
                _need('Adult Scrimmages: Skating Officials', 1)
            ]
        )
        assert [row['event'] for row in reversed_rows] == [
            'Juniors Scrimmages',
            'Adult Scrimmages'
        ]

    def test_handles_no_needs(self):
        assert not _build_rows([])


class TestGroupRowsByDay:
    def test_collects_rows_into_days_in_order(self):
        rows = [
            {'day': 'Wednesday, December 17', 'event': 'A', 'sort_key': '1'},
            {'day': 'Wednesday, December 17', 'event': 'B', 'sort_key': '2'},
            {'day': 'Thursday, December 18', 'event': 'C', 'sort_key': '3'},
        ]
        days = _group_rows_by_day(rows)

        assert [day['day'] for day in days] == [
            'Wednesday, December 17',
            'Thursday, December 18'
        ]
        assert len(days[0]['rows']) == 2
        assert len(days[1]['rows']) == 1


class TestFormatCount:
    def test_singular_at_exactly_one(self):
        # One volunteer is an Official, not Officials.
        entry = {'label': 'Skating Officials', 'filled': 1}
        assert _format_count(entry, 'Adult Scrimmages') == (
            '1 x Skating Official'
        )

    def test_plural_at_any_other_count(self):
        for filled in (0, 2, 11):
            entry = {'label': 'Skating Officials', 'filled': filled}
            assert _format_count(entry, 'Adult Scrimmages') == (
                f'{filled} x Skating Officials'
            )

    def test_double_s_endings_are_left_alone(self):
        entry = {'label': 'Class', 'filled': 1}
        assert _format_count(entry, 'Event') == '1 x Class'

    def test_label_without_a_plural_is_unchanged(self):
        entry = {'label': 'Crew Chief', 'filled': 1}
        assert _format_count(entry, 'Event') == '1 x Crew Chief'

    def test_label_matching_the_event_reports_a_bare_count(self):
        # The label would just repeat the row heading.
        entry = {'label': 'Bout Day Volunteers', 'filled': 3}
        assert _format_count(entry, 'Bout Day Volunteers') == '3 signed up'


class TestFormatDayText:
    def test_row_heading_joins_event_and_time(self, summary):
        rows = _build_rows(summary['needs'])
        day = _group_rows_by_day(rows)[0]
        text = _format_day_text(day, show_heading=False)

        assert text.split('\n')[0] == '*Juniors Scrimmages 6:00-7:00 p.m.*'

    def test_omits_the_date_heading_for_a_single_day(self, summary):
        rows = _build_rows(summary['needs'])
        day = _group_rows_by_day(rows)[0]
        text = _format_day_text(day, show_heading=False)

        assert 'December 17' not in text

    def test_leads_with_the_date_heading_when_asked(self, summary):
        rows = _build_rows(summary['needs'])
        day = _group_rows_by_day(rows)[0]
        text = _format_day_text(day, show_heading=True)

        assert text.startswith('*Wednesday, December 17*')

    def test_one_line_per_role_beneath_the_heading(self, summary):
        rows = _build_rows(summary['needs'])
        day = _group_rows_by_day(rows)[0]
        text = _format_day_text(day, show_heading=False)

        assert text == (
            '*Juniors Scrimmages 6:00-7:00 p.m.*\n'
            '4 x Non-Skating Officials\n'
            '6 x Skating Officials\n\n'
            '*Adult Scrimmages 7:00-8:00 p.m.*\n'
            '1 x Non-Skating Official\n'
            '4 x Skating Officials\n\n'
            '*Adult Scrimmages 8:00-9:00 p.m.*\n'
            '1 x Non-Skating Official\n'
            '3 x Skating Officials'
        )


class TestBuildSummaryBlocks:
    def test_header_context_and_divider(self, summary):
        blocks = build_summary_blocks(summary)
        assert blocks[0]['type'] == 'header'
        assert blocks[0]['text']['text'] == (
            'Shift sign-ups for Wednesday, December 17 2025'
        )
        assert blocks[1]['type'] == 'context'
        assert '4:50 p.m.' in blocks[1]['elements'][0]['text']
        assert blocks[2] == {'type': 'divider'}

    def test_one_section_per_day_plus_the_prompt(self, summary):
        blocks = build_summary_blocks(summary)
        sections = [b for b in blocks if b['type'] == 'section']
        # One day, then the call to action.  A section per day rather
        # than per row keeps a long window inside Slack's 50-block cap.
        assert len(sections) == 2
        assert '*Juniors Scrimmages 6:00-7:00 p.m.*' in (
            sections[0]['text']['text']
        )

    def test_a_multi_day_summary_gets_a_section_per_day(self, summary):
        summary['multi_day'] = True
        summary['needs'][0]['shifts'][0]['day'] = 'Thursday, December 18'
        summary['needs'][0]['shifts'][0]['sort_key'] = '2025-12-18 19:00:00'

        blocks = build_summary_blocks(summary)
        sections = [b for b in blocks if b['type'] == 'section']

        # Two days, then the call to action.
        assert len(sections) == 3
        assert sections[0]['text']['text'].startswith(
            '*Wednesday, December 17*'
        )
        assert sections[1]['text']['text'].startswith(
            '*Thursday, December 18*'
        )

    def test_one_button_per_need_each_on_its_own_row(self, summary):
        blocks = build_summary_blocks(summary)
        actions = [b for b in blocks if b['type'] == 'actions']
        # A block each keeps Slack from wrapping them by client width.
        assert len(actions) == 4
        assert all(len(block['elements']) == 1 for block in actions)

    def test_buttons_carry_the_full_title_and_url(self, summary):
        blocks = build_summary_blocks(summary)
        actions = [b for b in blocks if b['type'] == 'actions']
        button = actions[0]['elements'][0]

        # Buttons follow the section order, so the juniors event leads
        # even though the adult opportunities come first in the summary.
        assert button['text']['text'] == (
            'Juniors Scrimmages: Non-Skating Officials'
        )
        assert button['url'] == 'https://example.org/need/3'
        # Slack rejects duplicate action_ids within a message.
        ids = [block['elements'][0]['action_id'] for block in actions]
        assert len(set(ids)) == 4

    def test_button_order_matches_the_section_order(self, summary):
        blocks = build_summary_blocks(summary)
        actions = [b for b in blocks if b['type'] == 'actions']

        assert [
            block['elements'][0]['text']['text'] for block in actions
        ] == [
            'Juniors Scrimmages: Non-Skating Officials',
            'Juniors Scrimmages: Skating Officials',
            'Adult Scrimmages: Non-Skating Officials',
            'Adult Scrimmages: Skating Officials'
        ]

    def test_buttons_appear_after_every_section(self, summary):
        blocks = build_summary_blocks(summary)
        types = [block['type'] for block in blocks]
        assert types.index('actions') > max(
            index for index, kind in enumerate(types) if kind == 'section'
        )

    def test_long_button_text_is_trimmed(self):
        long_title = 'A' * 100
        blocks = build_summary_blocks(
            {
                'title': 'Long',
                'needs': [
                    {
                        'title': long_title,
                        'signup_url': 'https://example.org/need/1',
                        'shifts': []
                    }
                ]
            }
        )
        button = [
            b for b in blocks if b['type'] == 'actions'
        ][0]['elements'][0]

        assert len(button['text']['text']) == 75

    def test_no_button_without_a_signup_url(self):
        blocks = build_summary_blocks(
            {
                'title': 'No Link',
                'needs': [{'title': 'Orphan', 'shifts': []}]
            }
        )
        assert all(block['type'] != 'actions' for block in blocks)

    def test_omits_context_without_as_of(self):
        blocks = build_summary_blocks({'title': 'No Timestamp'})
        assert all(b['type'] != 'context' for b in blocks)

    def test_no_prompt_without_needs(self):
        blocks = build_summary_blocks({'title': 'Nothing'})
        assert all(block['type'] != 'section' for block in blocks)


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
        assert kwargs['text'] == (
            'Shift sign-ups for Wednesday, December 17 2025 - '
            '6 shift(s)'
        )


class TestPostSummarySkipsEmpty:
    # A summary covers a short day window, so a day with nothing
    # scheduled is routine.  Posting "nothing today" every off day would
    # be noise, especially once the summary runs on a schedule.
    def _empty_summary(self) -> dict:
        return {
            'title': 'Shift sign-ups for Tuesday, July 14 2026',
            'as_of': '2026-07-14 09:00',
            'needs': []
        }

    def test_live_post_is_skipped(self):
        client = Mock()
        notifier = SlackNotifier(
            channel='C123',
            check_mode=False,
            token=FAKE_XOXB,
            client=client
        )

        assert notifier.post_summary(summary=self._empty_summary()) is None
        client.chat_postMessage.assert_not_called()

    def test_check_mode_is_skipped_too(self, capsys):
        # A dry run must preview what a live run would do, including
        # doing nothing.
        client = Mock()
        notifier = SlackNotifier(
            channel='C123',
            check_mode=True,
            client=client
        )

        assert notifier.post_summary(summary=self._empty_summary()) is None
        client.chat_postMessage.assert_not_called()
        # The Block Kit payload is not printed for an empty summary.
        assert 'blocks' not in capsys.readouterr().out

    def test_missing_shifts_key_is_treated_as_empty(self):
        client = Mock()
        notifier = SlackNotifier(
            channel='C123',
            check_mode=False,
            token=FAKE_XOXB,
            client=client
        )

        assert notifier.post_summary(summary={'title': 'No key'}) is None
        client.chat_postMessage.assert_not_called()
