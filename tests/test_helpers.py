""" Characterization tests for star_pass._helpers.Helpers.

    These tests capture the *current* behavior of the helper methods so
    that later refactoring (Phase 2+) cannot change it unnoticed. Where
    current behavior differs from a method's docstring, the test asserts
    the real behavior and notes the discrepancy.
"""
# pylint: disable=missing-function-docstring,missing-class-docstring
# pylint: disable=protected-access

# Imports - Python Standard Library
import json
import logging
from pathlib import Path
from unittest.mock import Mock

# Imports - Third-Party
import pytest
from thefuzz import fuzz
from urllib3.exceptions import MaxRetryError, ReadTimeoutError

# Imports - Local
from star_pass import _defaults, _models, _helpers
from star_pass._exceptions import ConfigurationError, UpstreamError
from star_pass._records import MATCH_KIND_FUZZY, MATCH_KIND_KEYWORD


class TestConvertToBool:
    @pytest.mark.parametrize(
        'value, expected',
        [
            ('true', True),
            ('false', False),
            ('True', True),
            ('False', False),
            ('  TRUE  ', True),
            ('yes', True),
            ('y', True),
            ('t', True),
            ('1', True),
            ('no', False),
            ('n', False),
            ('f', False),
            ('0', False),
        ]
    )
    def test_valid_boolean_strings(self, helpers, value, expected):
        assert helpers.convert_to_bool(value) is expected

    @pytest.mark.parametrize(
        'value',
        ['maybe', 'flase', '', '2', 'tru', 'noo']
    )
    def test_invalid_input_raises_value_error(self, helpers, value):
        # Fail fast: a typo must never be silently coerced (e.g. so a
        # mistyped check_mode can't accidentally send live requests).
        with pytest.raises(ValueError):
            helpers.convert_to_bool(value)


class TestDateTimeFormatting:
    @pytest.mark.parametrize(
        'value, expected',
        [
            ('5/6/24 11:30', '2024-05-06 11:30'),
            ('6 may 2024 11:30 am', '2024-05-06 11:30'),
        ]
    )
    def test_format_date_time_amplify(self, helpers, value, expected):
        assert helpers.format_date_time_amplify(value) == expected

    def test_format_shift_date_simple(self, helpers):
        # The '%d' directive zero-pads the day.
        result = helpers.format_shift_date_simple('2025-04-09 11:30')
        assert result == 'Wednesday, April 09 2025'

    def test_format_shift_time_simple_adds_end_time(self, helpers):
        result = helpers.format_shift_time_simple('2025-04-09 11:30', '60')
        assert result == '11:30-12:30'


# Independent baseline of the need_ids each keyword resolved to before the
# data-model refactor, with the two documented fixes applied (hr, aoa ->
# standard adult_game). Keys are '<calendar>|<keyword>'.
_NEED_IDS_BASELINE = json.loads(
    (
        Path(__file__).resolve().parent
        / 'fixtures' / 'shift_need_ids_expected.json'
    ).read_text(encoding='utf-8')
)


class TestSearchShiftInfo:
    @pytest.mark.parametrize(
        'key, expected_need_ids',
        list(_NEED_IDS_BASELINE.items())
    )
    def test_need_ids_unchanged_after_refactor(
        self, helpers, key, expected_need_ids
    ):
        # Every keyword in the shift data model resolves to the
        # need_ids recorded in the fixture.
        gcal_name, need_name = key.split('|', 1)
        result = helpers.search_shift_info(
            gcal_name=gcal_name,
            need_name=need_name
        )
        assert result['need_ids'] == expected_need_ids

    @pytest.mark.parametrize(
        'gcal_name, need_name, expected_description',
        [
            # Real event titles sampled from Google Calendar exports.
            ('events', 'GNR v HH', 'Adult Games'),
            (
                'events',
                'G1: Petals Exhibition Bout',
                'Rose Petals Games'
            ),
            ('practices', 'Officials', 'Adult Officiating Practices'),
            (
                'practices',
                'Adult HT Scrimmage: BB/HH',
                'Adult Scrimmages'
            ),
            ('practices', 'Wreckers A/B Scrimmage', 'Adult Scrimmages'),
            ('practices', 'Buds Mixed Scrimmage', 'Junior Scrimmages'),
            # Synthesized titles a human might reasonably use.
            ('events', 'Axles vs. Jet City', 'Adult Games'),
            (
                'practices',
                'Officiating Practice',
                'Adult Officiating Practices'
            ),
            ('events', 'PTT vs Cherry City', 'Rose Petals Games'),
            ('events', 'BB vs. JRD', 'Adult Games'),
            (
                'practices',
                'Officials Training',
                'Adult Officiating Practices'
            ),
            ('practices', 'Wreckers Mod. Contact', 'Adult Scrimmages'),
        ]
    )
    def test_realistic_event_name_matches(
        self, helpers, gcal_name, need_name, expected_description
    ):
        result = helpers.search_shift_info(
            gcal_name=gcal_name,
            need_name=need_name
        )
        assert result['description'] == expected_description

    def test_unmatched_title_routes_to_review(self, helpers, caplog):
        # A title with no recognized team must not be guessed; it falls
        # back to the review default and logs a warning so the operator
        # can add an alias.
        with caplog.at_level(logging.WARNING, logger='star_pass'):
            result = helpers.search_shift_info(
                gcal_name='events',
                need_name='Jet City vs Cherry City'
            )

        assert result['description'] == 'Unknown Game'
        assert result['need_ids'][0]['id'] == ''
        assert 'review' in caplog.text.lower()


class TestMatchShiftInfo:
    # What 'search_shift_info' returns one field of.  A run stores the
    # match it made, so the category and the way the title reached it
    # have to survive the lookup.

    def test_a_keyword_match_names_the_category(self, helpers):
        matched = helpers.match_shift_info(
            gcal_name='events',
            need_name='Wheels of Justice vs Rose City'
        )

        assert matched.category is not None
        assert matched.need_details['description'] == 'Adult Games'

    def test_a_keyword_match_records_the_alias_that_won(self, helpers):
        matched = helpers.match_shift_info(
            gcal_name='events',
            need_name='Wheels of Justice vs Rose City'
        )

        assert matched.match.kind == MATCH_KIND_KEYWORD
        assert matched.match.keyword in ('wheels', 'woj', 'justice')
        assert matched.match.score is None

    def test_a_fuzzy_match_records_a_score_and_no_alias(
        self, monkeypatch, helpers
    ):
        # The deterministic pass returns before the threshold is
        # consulted, so a title that matches an alias literally would
        # never reach the fallback this checks.
        monkeypatch.setattr(
            'star_pass._helpers.FUZZY_MATCH_THRESHOLD', 1
        )

        matched = helpers.match_shift_info(
            gcal_name='practices',
            need_name='Quilting Circle Meetup'
        )

        assert matched.match.kind == MATCH_KIND_FUZZY
        assert matched.match.keyword is None

    def test_a_fuzzy_score_is_the_one_that_cleared_the_threshold(
        self, monkeypatch, helpers
    ):
        # A fuzzy match is recorded only when it clears the threshold,
        # so the score stored cannot be below it.  A value that did
        # not come from that comparison could be anything.
        threshold = 30
        monkeypatch.setattr(
            'star_pass._helpers.FUZZY_MATCH_THRESHOLD', threshold
        )

        matched = helpers.match_shift_info(
            gcal_name='practices',
            need_name='Quilting Circle Meetup'
        )

        assert threshold <= matched.match.score <= 100

    def test_the_scorer_answers_in_whole_numbers(self):
        # A match is stored with the score as it came, in a field
        # typed for a whole number.  A library that began answering
        # in fractions would put one there and nothing else would
        # notice, so the assumption is held here rather than worked
        # around at the call site.
        assert isinstance(
            fuzz.token_set_ratio('Quilting Circle Meetup', 'juniors'),
            int
        )

    def test_an_unmatched_title_names_no_category_and_no_match(
        self, helpers
    ):
        # Neither is what happened, and a run that recorded one would
        # be claiming the model matched something it did not.
        matched = helpers.match_shift_info(
            gcal_name='events',
            need_name='Jet City vs Cherry City'
        )

        assert matched.category is None
        assert matched.match is None

    def test_an_unmatched_title_still_carries_the_review_fallback(
        self, helpers
    ):
        matched = helpers.match_shift_info(
            gcal_name='events',
            need_name='Jet City vs Cherry City'
        )

        assert matched.need_details['description'] == 'Unknown Game'
        assert matched.need_details['need_ids'][0]['id'] == ''

    @pytest.mark.parametrize(
        'gcal_name, need_name',
        [
            ('events', 'Wheels of Justice vs Rose City'),
            ('events', 'Jet City vs Cherry City'),
            ('practices', 'Adult Officiating Practice')
        ]
    )
    def test_the_two_lookups_agree_about_the_configuration(
        self, helpers, gcal_name, need_name
    ):
        # One is the other's answer with two fields dropped.  Answered
        # separately, the run and the CSV could match a title to
        # different opportunities.
        assert helpers.search_shift_info(
            gcal_name=gcal_name,
            need_name=need_name
        ) == helpers.match_shift_info(
            gcal_name=gcal_name,
            need_name=need_name
        ).need_details

    def test_the_configuration_carries_no_alias_list(self, helpers):
        # The aliases are how the model is searched, not something a
        # run has any use for.
        matched = helpers.match_shift_info(
            gcal_name='events',
            need_name='Wheels of Justice vs Rose City'
        )

        assert 'aliases' not in matched.need_details


class TestRedactSecrets:
    @pytest.mark.parametrize(
        'text, secret',
        [
            (
                'https://www.googleapis.com/events?key=SUPERSECRET&x=1',
                'SUPERSECRET'
            ),
            (
                "{'Authorization': 'Bearer abc123.token'}",
                'abc123.token'
            ),
        ]
    )
    def test_secret_is_removed(self, helpers, text, secret):
        result = helpers.redact_secrets(text)
        assert secret not in result
        assert 'REDACTED' in result

    def test_preserves_the_label_prefix(self, helpers):
        result = helpers.redact_secrets('?key=SUPERSECRET&page=2')
        assert result == '?key=REDACTED&page=2'

    def test_ordinary_text_is_unchanged(self, helpers):
        text = 'HTTP 404 Not Found for /needs/123/shifts'
        assert helpers.redact_secrets(text) == text

    @pytest.mark.parametrize(
        'text, sentinel',
        [
            ('?api_key=SENTINELVALUE&x=1', 'SENTINELVALUE'),
            ('?access_token=SENTINELVALUE', 'SENTINELVALUE'),
            ('?token=SENTINELVALUE', 'SENTINELVALUE'),
            # A Slack credential carries its own prefix, so it can leak
            # with no adjacent label to match on.
            ('posted with xoxb-123-456-SENTINELVALUE', 'SENTINELVALUE'),
            ('xoxp-9-9-SENTINELVALUE in a message', 'SENTINELVALUE'),
        ]
    )
    def test_additional_secret_shapes_are_removed(
        self, helpers, text, sentinel
    ):
        result = helpers.redact_secrets(text)
        assert sentinel not in result
        assert 'REDACTED' in result

    def test_a_word_ending_in_token_is_not_mangled(self, helpers):
        # The label patterns require the '=' separator.
        text = 'the token was rejected'
        assert helpers.redact_secrets(text) == text


def _send_and_expect_upstream_error(
    helpers, monkeypatch, caplog, raise_conn_error
):
    # Force the session's HTTP call to raise, and capture the error
    # record logged before the exception reaches the caller.  Shared by
    # the redaction tests, which differ only in the error they raise.
    monkeypatch.setattr(_helpers.Session, 'request', raise_conn_error)

    with caplog.at_level(logging.ERROR, logger='star_pass'):
        with pytest.raises(UpstreamError):
            helpers.send_api_request(
                api_request_data={
                    'method': 'GET',
                    'url': 'https://x/events',
                    'timeout': 3
                }
            )


class TestSearchShiftInfoNeedsTheModel:
    # The model is read when a caller needs it, so a bad one surfaces
    # as a ConfigurationError from the call that needed it rather than
    # from an import.

    def test_a_malformed_model_reaches_the_caller(
        self, helpers, monkeypatch, tmp_path
    ):
        bad = tmp_path / 'bad.yml'
        bad.write_text('calendar: [unclosed\n', encoding='utf-8')
        monkeypatch.setattr(_defaults, 'SHIFTS_INFO_FILE', bad)
        _models.get_shifts_info.cache_clear()

        try:
            with pytest.raises(ConfigurationError):
                helpers.search_shift_info(
                    gcal_name='events',
                    need_name='GNR v HH'
                )
        finally:
            _models.get_shifts_info.cache_clear()


class TestSendApiRequestRedaction:
    def test_error_repr_with_key_is_redacted(
            self, helpers, monkeypatch, caplog
    ):
        # 'sentinel' (not 'secret'/'token') avoids a false-positive
        # bandit B105 hardcoded-password finding on the test value.
        sentinel = 'TOPSECRET'

        def raise_conn_error(_self, **_kwargs):
            raise _helpers.exceptions.ConnectionError(
                f'Failed for url https://x/events?key={sentinel}'
            )

        _send_and_expect_upstream_error(
            helpers=helpers,
            monkeypatch=monkeypatch,
            caplog=caplog,
            raise_conn_error=raise_conn_error
        )

        assert sentinel not in caplog.text
        assert 'REDACTED' in caplog.text

    def test_read_timeout_error_is_handled(
            self, helpers, monkeypatch, caplog
    ):
        # A realistic requests ConnectionError from an exhausted retry:
        # args[0] is a MaxRetryError whose reason is a ReadTimeoutError.
        # A handler that assumes a '>: ' delimiter raises IndexError
        # on this exact shape.
        sentinel = 'TOPSECRET'
        reason = ReadTimeoutError(
            None,
            'https://x/events',
            'Read timed out. (read timeout=10)'
        )
        conn_error = _helpers.exceptions.ConnectionError(
            MaxRetryError(
                None,
                f'https://x/events?key={sentinel}',
                reason=reason
            )
        )

        def raise_conn_error(_self, **_kwargs):
            raise conn_error

        _send_and_expect_upstream_error(
            helpers=helpers,
            monkeypatch=monkeypatch,
            caplog=caplog,
            raise_conn_error=raise_conn_error
        )

        # Handled cleanly (no IndexError), logged, and redacted.
        assert 'An HTTP error occurred' in caplog.text
        assert sentinel not in caplog.text


class TestResponseJson:
    def test_returns_parsed_json(self, helpers):
        response = Mock()
        response.json.return_value = {'data': [1, 2]}
        assert helpers.response_json(response) == {'data': [1, 2]}

    def test_non_json_body_exits(self, helpers, caplog):
        # e.g. an HTML gateway error page returned with a 2xx status.
        response = Mock()
        response.json.side_effect = ValueError('Expecting value')

        with caplog.at_level(logging.ERROR, logger='star_pass'):
            with pytest.raises(UpstreamError):
                helpers.response_json(response)

        assert 'not valid JSON' in caplog.text


class TestBuildSession:
    def test_session_retry_is_configured(self, helpers):
        session = helpers._build_session()
        retry = session.get_adapter('https://example.test').max_retries

        assert retry.total == 3
        assert retry.backoff_factor == 0.5
        assert 429 in retry.status_forcelist
        assert 503 in retry.status_forcelist

    def test_the_session_is_reused(self, helpers):
        # A session per request left pooled connections unreleased and
        # defeated the connection reuse a Session exists to provide.
        assert helpers._build_session() is helpers._build_session()

    def test_each_helpers_instance_has_its_own_session(self):
        assert (
            _helpers.Helpers()._build_session()
            is not _helpers.Helpers()._build_session()
        )

    def test_post_is_not_retried(self, helpers):
        # POST creates Amplify shifts; it must not be auto-retried on a
        # read error or bad status, which could duplicate a shift. The
        # urllib3 default allowed-methods set excludes POST.
        session = helpers._build_session()
        retry = session.get_adapter('https://example.test').max_retries

        assert 'POST' not in retry.allowed_methods
        assert 'GET' in retry.allowed_methods
