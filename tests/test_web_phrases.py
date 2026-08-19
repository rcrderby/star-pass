#!/usr/bin/env python3
""" The web interface's wordings, held to what the core publishes.

    The contract answers with identifiers, and each client words them
    itself: the command line has 'UNCOLLECTED_PHRASES' and
    'BLOCKER_PHRASES', and the browser has 'web/phrases.json'.  Those
    two command line maps are held to the core's own tuples by tests in
    'test_cli_commands.py'; this is the same test for the third client.

    It is a Python test for a file the browser reads because there is
    no build step and no JavaScript test runner, which is why the
    wordings are JSON rather than a module: one file, read by the page
    at run time and by this test at build time, with nothing generated
    in between.  A status with no wording reaches a screen as
    'partly_sent', which is written for a program to branch on.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
import json
from pathlib import Path
from re import findall
from typing import Any, Dict

# Imports - Local
from star_pass._preview import BLOCKER_REASONS
from star_pass._records import MATCH_KINDS, RUN_STATUSES
from star_pass._reporting import STEPS

# Where the page keeps them, from this file.
PHRASES_PATH = Path(__file__).parent.parent / 'web' / 'phrases.json'


def phrases() -> Dict[str, Any]:
    return json.loads(PHRASES_PATH.read_text(encoding='utf-8'))


class TestWebPhrases:
    def test_the_page_ships_its_wordings(self) -> None:
        assert PHRASES_PATH.is_file()

    def test_every_run_status_the_core_publishes_is_worded(self) -> None:
        # A status with no wording reaches the run list as its
        # identifier.
        assert set(phrases()['runStatus']) == set(RUN_STATUSES)

    def test_no_wording_is_for_a_status_that_does_not_exist(self) -> None:
        # The other direction, which is what catches a status being
        # renamed rather than added: the wording would survive, and
        # nothing would say it is now unreachable.
        for status in phrases()['runStatus']:
            assert status in RUN_STATUSES

    def test_nothing_is_worded_as_itself(self) -> None:
        # A wording identical to the identifier is a placeholder
        # somebody meant to come back to.
        for status, wording in phrases()['runStatus'].items():
            assert wording != status

    def test_every_match_kind_the_core_publishes_is_worded(self) -> None:
        # The note under a row saying how its title reached its
        # category. A kind with no wording reaches the row as
        # 'fuzzy'.
        assert set(phrases()['matchKind']) == set(MATCH_KINDS)

    def test_no_match_wording_is_for_a_kind_that_does_not_exist(
        self
    ) -> None:
        for kind in phrases()['matchKind']:
            assert kind in MATCH_KINDS

    def test_every_step_the_core_publishes_is_worded(self) -> None:
        # The collecting screen draws one row per step and the sending
        # screen names the opportunity each read is about. A step with
        # no wording reaches both as 'read_opportunities'.
        assert set(phrases()['step']) == set(STEPS)

    def test_no_step_wording_is_for_a_step_that_does_not_exist(
        self
    ) -> None:
        for step in phrases()['step']:
            assert step in STEPS

    def test_no_step_is_worded_as_itself(self) -> None:
        for step, wording in phrases()['step'].items():
            assert wording != step

    def test_every_blocker_the_core_publishes_is_worded(self) -> None:
        # The preview names why nothing can be sent, and the reason
        # crosses the wire as an identifier. One with no wording
        # reaches the line under the send button as
        # 'ends_before_start'.
        assert set(phrases()['blocker']) == set(BLOCKER_REASONS)

    def test_no_blocker_wording_is_for_a_reason_that_is_gone(
        self
    ) -> None:
        for reason in phrases()['blocker']:
            assert reason in BLOCKER_REASONS

    def test_no_blocker_is_worded_as_itself(self) -> None:
        for reason, wording in phrases()['blocker'].items():
            assert wording != reason

    def test_a_wording_only_asks_for_values_it_is_given(self) -> None:
        # The row notes carry '{name}' where a value goes, and a name
        # the page does not pass is left on screen in braces.
        allowed = {
            'matchKind': {'keyword', 'category', 'score'},
            'step': {'subject'},
            'blocker': set(),
            'row': {
                'start', 'end', 'minutes', 'direction', 'title'
            }
        }

        for group, names in allowed.items():
            for wording in phrases()[group].values():
                assert set(findall(r'\{(\w+)\}', wording)) <= names
