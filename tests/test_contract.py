""" Behaviors the API-first extraction must not change.

    The extraction described in 'docs/design/api-and-security-plan.md'
    moves domain logic behind a core package and a service boundary.
    These tests pin the behaviors that the plan names explicitly, so a
    change to any of them fails here rather than being discovered by an
    operator during a monthly run.

    Behaviors the existing suite already pins are not repeated here; a
    duplicate characterization test reads as coverage while testing
    nothing new.  Those are:

      - duration capped at 'max_length', and a duration of zero or less
        exiting: 'test_gcal_data.TestGetShiftTimeData'
      - fully duplicate rows dropped:
        'test_amplify_shifts.test_fully_duplicate_rows_are_removed'
      - an empty need ID stopping the run:
        'test_amplify_shifts.test_invalid_need_id_fails_schema_validation'
      - an unmatched title routing to review:
        'test_helpers.test_unmatched_title_routes_to_review'

    What is left, and pinned below, is the filter order, the fuzzy match
    threshold, and the search window's bounds.
"""
# pylint: disable=missing-function-docstring,missing-class-docstring
# pylint: disable=protected-access,redefined-outer-name

# Imports - Python Standard Library
import logging
from unittest.mock import Mock

# Imports - Third-Party
import pytest

# Imports - Local
from star_pass import _defaults
from star_pass._helpers import Helpers
from star_pass.gcal_data import GCALData, get_gcal_time_window


@pytest.fixture
def gcal() -> GCALData:
    # auto_prep_data=False prevents any Google Calendar API calls.
    return GCALData(gcal_name='practices', auto_prep_data=False)


@pytest.fixture
def helpers() -> Helpers:
    return Helpers()


def _item(summary: str, key: str, start: str, end: str) -> dict:
    # A Google Calendar item.  'key' is 'dateTime' for a timed event and
    # 'date' for an all-day one, which is the only structural difference
    # between them and the thing the all-day check reads.
    return {'summary': summary, 'start': {key: start}, 'end': {key: end}}


class TestFilterOrder:
    # The title filter runs before the all-day check.  The order is
    # observable: an excluded title is dropped silently, while an
    # all-day event logs a warning naming it.  A cancelled all-day
    # event that produced an all-day warning would tell an operator to
    # look at an event that was never a candidate.

    def test_excluded_title_wins_over_the_all_day_check(
        self, gcal, caplog
    ):
        items = [
            _item(
                summary='Cancelled: Board Retreat',
                key='date',
                start='2099-03-05',
                end='2099-03-06'
            )
        ]

        with caplog.at_level(logging.WARNING, logger='star_pass'):
            result = gcal.filter_gcal_items(gcal_shift_data=items)

        assert result == []
        assert 'all-day event' not in caplog.text

    def test_an_all_day_event_with_a_kept_title_is_named(
        self, gcal, caplog
    ):
        # The companion case, so the assertion above cannot pass because
        # the warning was never emitted for any input.
        items = [
            _item(
                summary='Board Retreat',
                key='date',
                start='2099-03-05',
                end='2099-03-06'
            )
        ]

        with caplog.at_level(logging.WARNING, logger='star_pass'):
            result = gcal.filter_gcal_items(gcal_shift_data=items)

        assert result == []
        assert 'all-day event' in caplog.text
        assert 'Board Retreat' in caplog.text

    def test_an_untitled_event_never_reaches_the_title_filter(
        self, gcal, caplog
    ):
        # An untitled event is dropped first, by its own check, because
        # the title filter has nothing to test.
        items = [
            {
                'start': {'dateTime': '2099-03-05T18:00:00-08:00'},
                'end': {'dateTime': '2099-03-05T20:00:00-08:00'}
            }
        ]

        with caplog.at_level(logging.WARNING, logger='star_pass'):
            result = gcal.filter_gcal_items(gcal_shift_data=items)

        assert result == []
        assert 'no title' in caplog.text

    def test_a_kept_event_survives_every_check(self, gcal):
        items = [
            _item(
                summary='Adult Officiating Practice',
                key='dateTime',
                start='2099-03-05T18:00:00-08:00',
                end='2099-03-05T20:00:00-08:00'
            )
        ]

        assert gcal.filter_gcal_items(gcal_shift_data=items) == items


class TestFuzzyMatchThreshold:
    # The fuzzy fallback accepts a match only at or above 80.  The
    # number is a deliberate setting, not an accident of the library:
    # lowering it assigns shifts to the wrong opportunity, and raising
    # it sends recognizable titles to manual review.

    def test_threshold_is_eighty(self):
        assert _defaults.FUZZY_MATCH_THRESHOLD == 80

    def test_a_title_below_the_threshold_goes_to_review(
        self, helpers, caplog
    ):
        # No alias appears literally and nothing scores 80, so the title
        # takes the review fallback rather than a guess.
        with caplog.at_level(logging.WARNING, logger='star_pass'):
            result = helpers.search_shift_info(
                gcal_name='events',
                need_name='Quilting Circle Meetup'
            )

        assert result['need_ids'][0]['id'] == ''
        assert 'no confident shift-info match' in caplog.text.lower()

    def test_the_threshold_is_what_rejects_the_match(
        self, monkeypatch, helpers
    ):
        # The same title that goes to review at 80 is assigned once the
        # threshold drops, which pins the comparison to the threshold
        # rather than to any particular scorer output.  A title that
        # matches on a literal alias would not exercise this: the
        # deterministic pass returns before the threshold is consulted.
        need_name = 'Quilting Circle Meetup'

        rejected = helpers.search_shift_info(
            gcal_name='practices',
            need_name=need_name
        )
        assert rejected['need_ids'][0]['id'] == ''

        monkeypatch.setattr(
            'star_pass._helpers.FUZZY_MATCH_THRESHOLD', 1
        )
        assigned = helpers.search_shift_info(
            gcal_name='practices',
            need_name=need_name
        )
        assert assigned['need_ids'][0]['id'] != ''


class TestSearchWindow:
    # The window has no cap.  An earlier design invented a 60-day limit;
    # it is not real, and a monthly run over a long window must not be
    # rejected.

    def test_a_window_longer_than_sixty_days_is_accepted(
        self, monkeypatch
    ):
        monkeypatch.setenv('GCAL_WINDOW_START', '2099-01-01')
        monkeypatch.setenv('GCAL_WINDOW_END', '2099-12-31')

        window_start, window_end = get_gcal_time_window()

        assert window_start.startswith('2099-01-01')
        assert window_end.startswith('2099-12-31')

    def test_a_one_day_window_is_accepted(self, monkeypatch):
        monkeypatch.setenv('GCAL_WINDOW_START', '2099-01-01')
        monkeypatch.setenv('GCAL_WINDOW_END', '2099-01-02')

        window_start, window_end = get_gcal_time_window()

        assert window_start.startswith('2099-01-01')
        assert window_end.startswith('2099-01-02')

    def test_a_window_that_does_not_move_forward_is_rejected(
        self, monkeypatch
    ):
        # End equal to start is empty, not a one-day window: the end is
        # exclusive, so an equal pair can only collect nothing.
        monkeypatch.setenv('GCAL_WINDOW_START', '2099-01-01')
        monkeypatch.setenv('GCAL_WINDOW_END', '2099-01-01')

        with pytest.raises(ValueError):
            get_gcal_time_window()

    def test_the_window_end_reaches_the_request_unchanged(
        self, gcal, monkeypatch
    ):
        # Google treats 'timeMax' as exclusive, and that is what makes
        # the window end exclusive.  The exclusivity itself belongs to
        # the service and cannot be tested here, so pin the half that
        # can be: the validated end is sent as given, not shifted by a
        # day on the way out.
        seen_params = []

        def fake_send(api_request_data, **_kwargs):
            seen_params.append(dict(api_request_data['params']))
            response = Mock()
            response.json.return_value = {'items': []}
            return response

        monkeypatch.setattr(gcal.helpers, 'send_api_request', fake_send)

        gcal.get_gcal_shift_data(
            timeMin='2099-01-01T00:00:00-08:00',
            timeMax='2099-01-31T00:00:00-08:00'
        )

        assert seen_params
        for params in seen_params:
            assert params['timeMin'] == '2099-01-01T00:00:00-08:00'
            assert params['timeMax'] == '2099-01-31T00:00:00-08:00'
