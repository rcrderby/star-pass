#!/usr/bin/env python3
""" The two modes read a run the same way.

    The command line works with no server running, which only holds
    while both modes answer the same question the same way.  So every
    read is asked of both and the two answers are compared -- not
    described and checked separately, which would compare two
    descriptions rather than two answers.

    The harness that asks both is in 'conftest.py', because the writes
    are compared the same way in 'test_local_writes.py'.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
from typing import Any, Callable, Tuple

# Imports - Third-Party
import pytest

# Imports - Local
from star_pass_client import (
    ApiProblem,
    Client,
    LocalClient,
    LocalOperationUnavailable
)
from star_pass_client._generator import specification
from star_pass_client._local import HANDLERS, UNAVAILABLE


class TestTheTwoModesAgree:
    def test_the_runs_read_the_same(
        self,
        both: Callable[..., Tuple[Any, Any]],
        populated: str
    ) -> None:
        local, remote = both('list_runs')

        assert local == remote
        assert [run['id'] for run in local] == [populated]

    def test_one_run_reads_the_same(
        self,
        both: Callable[..., Tuple[Any, Any]],
        populated: str
    ) -> None:
        local, remote = both('get_run', run_id=populated)

        assert local == remote
        # Guard against both answering an empty document identically.
        assert len(local['events']) == 4
        assert local['opportunities']

    def test_the_revisions_read_the_same(
        self,
        both: Callable[..., Tuple[Any, Any]],
        populated: str
    ) -> None:
        local, remote = both('list_revisions', run_id=populated)

        assert local == remote
        assert [item['number'] for item in local] == [1, 2]

    def test_what_the_window_left_out_reads_the_same(
        self,
        both: Callable[..., Tuple[Any, Any]],
        not_collected: Callable[[str], list],
        populated: str
    ) -> None:
        not_collected(populated)

        local, remote = both('list_uncollected', run_id=populated)

        assert local == remote
        # Guard against both answering an empty document identically.
        assert [group['reason'] for group in local] == [
            'search',
            'excluded',
            'allday',
            'untitled'
        ]

    def test_an_event_pulled_in_reads_as_not_addable_in_both(
        self,
        both: Callable[..., Tuple[Any, Any]],
        events: Any,
        make_event: Callable[..., Any],
        not_collected: Callable[[str], list],
        populated: str
    ) -> None:
        # Whether an event may be pulled in is answered from the
        # revision as well as the stored row, so a mode that read one
        # of the two would offer an event the run already holds.
        left_out = not_collected(populated)
        searched = next(
            row for row in left_out if row.reason == 'search'
        )
        events.add(
            run_id=populated,
            revision=2,
            event=make_event(id=searched.id)
        )

        local, remote = both('list_uncollected', run_id=populated)

        assert local == remote
        assert local[0]['reason'] == 'search'
        assert local[0]['events'][0]['addable'] is False

    def test_the_preview_reads_the_same(
        self,
        both: Callable[..., Tuple[Any, Any]],
        amplify_holds: Callable[..., None],
        make_amplify_shift: Callable[..., dict],
        populated: str
    ) -> None:
        # Amplify holds one of the shifts, so the two modes are
        # compared on the live read as well: a mode that skipped asking
        # would promise a row the other one knows will not arrive.
        amplify_holds({'905196': [make_amplify_shift()]})

        local, remote = both('get_preview', run_id=populated)

        assert local == remote
        assert local['totals']['willCreate']
        assert local['totals']['alreadyInAmplify']
        assert local['totals']['repeatedRows']
        assert local['skipped']
        assert local['blockers']

    def test_a_job_reads_the_same(
        self,
        both: Callable[..., Tuple[Any, Any]],
        job_id: str
    ) -> None:
        local, remote = both('get_job', job_id=job_id)

        assert local == remote
        assert local['id'] == job_id

    def test_the_version_reads_the_same(
        self,
        both: Callable[..., Tuple[Any, Any]]
    ) -> None:
        local, remote = both('get_version')

        assert local == remote

    def test_the_configuration_reads_the_same(
        self,
        both: Callable[..., Tuple[Any, Any]]
    ) -> None:
        local, remote = both('get_config')

        assert local == remote
        # Guard against both answering an empty document identically.
        assert local['timezone']
        assert local['calendars']

    def test_the_credential_tests_the_same(
        self,
        answer_requests: Callable[..., Any],
        both: Callable[..., Tuple[Any, Any]]
    ) -> None:
        # Two answers, so two attempts against the service's limit;
        # the allowance is larger than that, and local mode is not
        # limited at all.
        answer_requests(lambda _request: {'data': []})

        local, remote = both('test_credential')

        assert local == remote
        # Guard against both answering an empty document identically.
        assert local['working'] is True
        assert local['lastFour']

    def test_the_unmatched_titles_read_the_same(
        self,
        both: Callable[..., Tuple[Any, Any]],
        unmatched: Any
    ) -> None:
        unmatched.record(
            calendar='events',
            title='Jet City vs Cherry City',
            principal_id='static-token'
        )

        local, remote = both('list_unmatched_titles')

        assert local == remote
        # Guard against both answering an empty document identically.
        assert local[0]['timesSeen'] == 1

    def test_an_empty_database_reads_the_same(
        self,
        both: Callable[..., Tuple[Any, Any]],
        service_database: Any
    ) -> None:
        del service_database

        local, remote = both('list_runs')

        assert local == remote == []


class TestTheTwoModesFailTheSame:
    def test_an_unknown_run_fails_the_same(
        self,
        local_client: LocalClient,
        remote_client: Client,
        problem_from: Callable[..., ApiProblem],
    ) -> None:
        local = problem_from(local_client, 'get_run', run_id='no-such-run')
        remote = problem_from(
            remote_client,
            'get_run',
            run_id='no-such-run'
        )

        assert local.status == remote.status == 404
        assert local.detail == remote.detail
        assert 'no-such-run' in local.detail

    def test_an_unknown_job_fails_the_same(
        self,
        local_client: LocalClient,
        remote_client: Client,
        problem_from: Callable[..., ApiProblem],
    ) -> None:
        local = problem_from(local_client, 'get_job', job_id='no-such-job')
        remote = problem_from(
            remote_client,
            'get_job',
            job_id='no-such-job'
        )

        assert local.status == remote.status == 404
        assert local.detail == remote.detail

    def test_an_unknown_run_fails_the_same_for_every_run_operation(
        self,
        local_client: LocalClient,
        remote_client: Client,
        problem_from: Callable[..., ApiProblem],
    ) -> None:
        for operation in ('get_run', 'list_revisions', 'get_preview'):
            local = problem_from(
                local_client,
                operation,
                run_id='no-such-run'
            )
            remote = problem_from(
                remote_client,
                operation,
                run_id='no-such-run'
            )

            assert local.detail == remote.detail, operation


class TestWhatLocalModeCannotDo:
    def test_every_operation_is_handled_or_declared_unavailable(
        self
    ) -> None:
        # The point of generating the surface: an endpoint added to
        # the contract without a local answer fails here rather than
        # being discovered when somebody runs the command.
        published = {
            (verb.upper(), path)
            for path, verbs in specification()['paths'].items()
            for verb in verbs
        }

        assert published == set(HANDLERS) | set(UNAVAILABLE)

    def test_nothing_is_both_handled_and_unavailable(self) -> None:
        assert not set(HANDLERS) & set(UNAVAILABLE)

    def test_health_says_why_it_has_no_local_answer(
        self,
        local_client: LocalClient
    ) -> None:
        with pytest.raises(LocalOperationUnavailable) as error:
            local_client.get_health()

        assert 'nothing is serving' in str(error.value).lower()

    def test_following_a_job_says_why_it_has_no_local_answer(
        self,
        local_client: LocalClient
    ) -> None:
        with pytest.raises(LocalOperationUnavailable) as error:
            list(local_client.stream_job_events(job_id='j-1'))

        assert 'local mode' in str(error.value)

    def test_editing_says_where_a_run_is_edited(
        self,
        local_client: LocalClient
    ) -> None:
        # Not a gap to be filled in later: the command line covers
        # what the web interface cannot, and parity with it is not a
        # goal.  The reason says where to go rather than "not yet".
        with pytest.raises(LocalOperationUnavailable) as error:
            local_client.edit_events(
                run_id='r-1',
                idempotency_key='an-attempt',
                body={'operations': []}
            )

        assert 'web interface' in str(error.value)

    def test_pulling_an_event_in_says_where_it_is_done(
        self,
        local_client: LocalClient
    ) -> None:
        # Reading the list is troubleshooting and has a command;
        # pulling one off it is reviewing, and its home is the screen
        # showing the list.
        with pytest.raises(LocalOperationUnavailable) as error:
            local_client.add_event(
                run_id='r-1',
                body={'uncollectedId': 'gcal-1'}
            )

        assert 'web interface' in str(error.value)

    def test_sealing_says_where_a_revision_is_sealed(
        self,
        local_client: LocalClient
    ) -> None:
        # Reading the revisions a run has been through is
        # troubleshooting and has a command; sealing one is done from
        # the screen about to change what it holds.
        with pytest.raises(LocalOperationUnavailable) as error:
            local_client.seal_revision(
                run_id='r-1',
                idempotency_key='an-attempt'
            )

        # The reason says where it is done rather than "not yet",
        # which is the difference between a decision and a gap.
        assert 'sealed from the screen' in str(error.value)

    def test_reverting_says_who_decides_to_revert(
        self,
        local_client: LocalClient
    ) -> None:
        # A revert is a judgement about what the run held before,
        # which is made by somebody looking at what it holds now.
        with pytest.raises(LocalOperationUnavailable) as error:
            local_client.revert_revision(
                run_id='r-1',
                number=1,
                idempotency_key='an-attempt'
            )

        assert 'looking at what the run holds now' in str(error.value)

    def test_recording_a_title_says_where_it_is_done(
        self,
        local_client: LocalClient
    ) -> None:
        # Reading the log is what happens before the model file is
        # edited, so it has a command; recording one is done from the
        # screen showing the event the title blocked.
        with pytest.raises(LocalOperationUnavailable) as error:
            local_client.record_unmatched_title(
                body={'calendar': 'events', 'title': 'Something'}
            )

        assert 'screen showing the event' in str(error.value)

    def test_the_two_clients_offer_the_same_operations(
        self,
        local_client: LocalClient,
        remote_client: Client
    ) -> None:
        # Both inherit the generated surface, so this holds by
        # construction -- and the test is what says so out loud if
        # either ever stops inheriting it.
        published = {
            operation['operationId']
            for verbs in specification()['paths'].values()
            for operation in verbs.values()
        }

        for name in published:
            assert callable(getattr(local_client, name))
            assert callable(getattr(remote_client, name))
