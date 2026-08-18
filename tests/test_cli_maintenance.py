#!/usr/bin/env python3
""" Applying the retention policy from the command line.

    Two claims, and the second is the one that needed a module of its
    own to be true.

    The first is that it works: it opens the database in front of it,
    applies the same policy the service applies, and says what went.

    The second is that it is **not** one of the reading commands. Those
    each name an operation the contract publishes and each take
    '--api-url', by design, so that none of them can be the one that
    forgets to offer the remote mode. This names no operation and must
    offer no service, because the contract publishes no deletion for it
    to ask -- retention removes what a run leaves behind, a caller does
    not.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
from typing import Any, Callable

# Imports - Third-Party
import pytest

# Imports - Local
from star_pass import _defaults
from star_pass._repository import JobRepository, RevisionRepository
from star_pass._retention import Swept
from star_pass_cli._commands import COMMANDS
from star_pass_cli._maintenance import (
    JOB_EVENTS_LABEL,
    NOTHING_REMOVED,
    REVISIONS_LABEL,
    SENT_UNTOUCHED,
    swept_text,
    UNMATCHED_LABEL
)

# Constants
# The words that select it.
SWEEP = ('retention', 'sweep')


@pytest.fixture(name='sweeping')
def fixture_sweeping(
    build_parser: Callable[[], Any],
    entry_point: Any,
    service_database: Any
) -> Callable[[], None]:
    """ Return a way to run the command the entry point actually runs.

        Through 'main' rather than by calling the sweep, because what
        is being checked includes the dispatch: the command names no
        contract operation, so nothing in the command table would
        reach it.
    """
    del build_parser, service_database

    def run() -> None:
        """ Run 'retention sweep'. """
        return entry_point.main(argv=list(SWEEP))

    return run


class TestWhatItDoes:
    def test_it_applies_the_policy_to_the_local_database(
        self,
        finished_job: str,
        jobs: JobRepository,
        monkeypatch: pytest.MonkeyPatch,
        sweeping: Callable[[], None]
    ) -> None:
        # The service sweeps on a timer, which covers a deployment. It
        # does not cover a person with a checkout and a database file,
        # and there the windows would never be applied at all.
        monkeypatch.setattr(_defaults, 'RETENTION_JOB_LOG_DAYS', -1)

        sweeping()

        assert jobs.events(job_id=finished_job) == []

    def test_it_says_what_it_removed(
        self,
        capsys: pytest.CaptureFixture,
        monkeypatch: pytest.MonkeyPatch,
        revisions: RevisionRepository,
        run_id: str,
        sweeping: Callable[[], None]
    ) -> None:
        monkeypatch.setattr(_defaults, 'RETENTION_REVISION_DAYS', -1)
        for number in range(1, 4):
            revisions.create(run_id=run_id, label=f'Revision {number}')

        sweeping()

        shown = capsys.readouterr().out
        assert 'Revisions' in shown
        assert '1' in shown

    def test_it_says_so_when_there_was_nothing_to_remove(
        self,
        capsys: pytest.CaptureFixture,
        sweeping: Callable[[], None]
    ) -> None:
        # The usual answer, and worth saying: a command that printed
        # nothing would leave the operator unsure it had run.
        sweeping()

        assert NOTHING_REMOVED in capsys.readouterr().out


class TestWhatItIsNot:
    def test_it_is_not_one_of_the_reading_commands(self) -> None:
        # Every one of those names a contract operation. This names
        # none, and adding it there would mean weakening the test that
        # holds them to the published surface.
        assert SWEEP not in {
            (command.group, command.word) for command in COMMANDS
        }

    def test_it_offers_no_service_to_ask(
        self,
        build_parser: Callable[[], Any]
    ) -> None:
        # The whole reason it lives outside that table. There is no
        # remote answer and there is deliberately never going to be
        # one, so a flag naming a service would be a flag that lies.
        with pytest.raises(SystemExit):
            build_parser().parse_args(
                list(SWEEP) + ['--api-url', 'https://star-pass.test']
            )

    def test_it_is_still_reachable_from_the_command_line(
        self,
        build_parser: Callable[[], Any]
    ) -> None:
        # A negative test alone would pass on a command that no longer
        # parses at all.
        args = build_parser().parse_args(list(SWEEP))

        assert (args.command, args.subcommand) == SWEEP


class TestWhatItReports:
    def test_a_sweep_that_removed_nothing(self) -> None:
        assert swept_text(swept=Swept()) == NOTHING_REMOVED

    def test_a_sweep_that_removed_something_counts_each_kind(
        self
    ) -> None:
        # Read as label and value rather than as a substring, because
        # the values are aligned on the widest label and a test written
        # against today's padding would break on a longer one -- and,
        # worse, three different numbers would all satisfy a test that
        # only looked for the digits somewhere.
        counted = _counts(
            text=swept_text(
                swept=Swept(
                    job_events=4,
                    revisions=2,
                    unmatched_titles=7
                )
            )
        )

        assert counted == {
            JOB_EVENTS_LABEL: '4',
            REVISIONS_LABEL: '2',
            UNMATCHED_LABEL: '7'
        }

    def test_it_says_the_sent_record_was_not_touched(self) -> None:
        # The one thing somebody running a deletion by hand might fear
        # is the one thing it cannot do.
        assert SENT_UNTOUCHED in swept_text(swept=Swept(revisions=1))


def _counts(
    text: str
) -> dict:
    """ Return the labelled counts a report shows, by label. """
    return {
        label: value
        for label, _, value in (
            line.rpartition('  ')
            for line in text.splitlines()
            if '  ' in line
        )
        for label, value in ((label.strip(), value.strip()),)
    }
