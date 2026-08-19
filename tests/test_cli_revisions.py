#!/usr/bin/env python3
""" The command line client's reading of a run's revisions.

    Its own module rather than a class in 'test_cli_commands.py',
    which is near the thousand-line cap the linter holds a module to.

    What it is mostly about is the wording: the contract publishes
    what kind of revision each is and the revision it was made from,
    and this client puts the two into a sentence.  A test binding that
    map to the core's own tuple is what stops a kind reaching a table
    as 'recollected'.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
from typing import Callable

# Imports - Third-Party
import pytest

# Imports - Local
from star_pass._records import (
    REVISION_COLLECTED,
    REVISION_CONTINUED,
    REVISION_KINDS
)
from star_pass_cli import _render


class TestListingRevisions:
    def test_the_revisions_are_listed_oldest_first(
        self,
        capsys: pytest.CaptureFixture,
        cli: Callable[..., int],
        populated: str
    ) -> None:
        status = cli('runs', 'revisions', populated)
        shown = capsys.readouterr().out
        collected = _render.REVISION_PHRASES[REVISION_COLLECTED]
        continued = _render.REVISION_PHRASES[REVISION_CONTINUED]

        assert status == 0
        assert shown.index(collected) < shown.index(
            continued.format(number=1)
        )

    def test_a_revision_names_the_one_it_was_made_from(
        self,
        capsys: pytest.CaptureFixture,
        cli: Callable[..., int],
        populated: str
    ) -> None:
        # The number is a value the contract publishes rather than
        # part of a sentence, so the client is what puts the two
        # together -- and a client that put the wrong one in would
        # say a run went back somewhere it did not.
        cli('runs', 'revisions', populated)

        assert 'Continued from revision 1' in capsys.readouterr().out

    def test_every_kind_the_core_publishes_is_worded(self) -> None:
        # A kind with no wording reaches the table as 'recollected',
        # which is written for a program to branch on.
        assert set(_render.REVISION_PHRASES) == set(REVISION_KINDS)

    def test_no_kind_is_worded_as_itself(self) -> None:
        for kind, wording in _render.REVISION_PHRASES.items():
            assert wording != kind

    def test_the_revision_being_edited_is_marked(
        self,
        capsys: pytest.CaptureFixture,
        cli: Callable[..., int],
        populated: str
    ) -> None:
        cli('runs', 'revisions', populated)

        assert _render.CURRENT in capsys.readouterr().out

    def test_a_run_with_no_revisions_says_so(
        self,
        capsys: pytest.CaptureFixture,
        cli: Callable[..., int],
        run_id: str
    ) -> None:
        status = cli('runs', 'revisions', run_id)

        assert status == 0
        assert 'no revisions yet' in capsys.readouterr().out
