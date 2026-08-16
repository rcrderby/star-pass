#!/usr/bin/env python3
""" Tests for the reservations made against idempotency keys. """

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
from typing import Optional

# Imports - Third-Party
import pytest

# Imports - Local
from star_pass._exceptions import ValidationError
from star_pass._records import (
    IdempotencyRecord,
    JOB_KIND_RECOLLECT,
    JOB_KIND_SEND
)
from star_pass._repository import IdempotencyRepository, RunRepository

# Constants
PRINCIPAL = 'static-token'
KEY = 'a-key-a-caller-supplied'
FINGERPRINT = 'expectedShiftCount=12'
ACCEPTED = 202
ANSWER = {'jobId': 'ab12', 'runId': 'cd34'}


def reserve(
    idempotency: IdempotencyRepository,
    run_id: str,
    fingerprint: str = FINGERPRINT,
    operation: str = JOB_KIND_SEND
) -> Optional[IdempotencyRecord]:
    return idempotency.reserve(
        operation=operation,
        key=KEY,
        run_id=run_id,
        fingerprint=fingerprint,
        principal_id=PRINCIPAL
    )


def complete(
    idempotency: IdempotencyRepository,
    operation: str = JOB_KIND_SEND
) -> None:
    idempotency.complete(
        operation=operation,
        key=KEY,
        status_code=ACCEPTED,
        response=ANSWER
    )


class TestClaimingAKey:
    def test_a_key_nobody_has_used_is_claimed(
        self,
        idempotency: IdempotencyRepository,
        run_id: str
    ) -> None:
        assert reserve(idempotency=idempotency, run_id=run_id) is None

    def test_claiming_a_key_records_who_claimed_it_and_when(
        self,
        idempotency: IdempotencyRepository,
        run_id: str
    ) -> None:
        reserve(idempotency=idempotency, run_id=run_id)
        record = idempotency.get(operation=JOB_KIND_SEND, key=KEY)

        assert record.principal_id == PRINCIPAL
        assert record.created_at.endswith('+00:00')
        assert record.run_id == run_id

    def test_a_claimed_key_has_no_answer_yet(
        self,
        idempotency: IdempotencyRepository,
        run_id: str
    ) -> None:
        reserve(idempotency=idempotency, run_id=run_id)
        record = idempotency.get(operation=JOB_KIND_SEND, key=KEY)

        assert record.status_code is None
        assert record.response is None

    def test_a_key_nobody_has_used_reads_back_as_nothing(
        self,
        idempotency: IdempotencyRepository
    ) -> None:
        assert idempotency.get(
            operation=JOB_KIND_SEND,
            key='never-used'
        ) is None

    def test_the_same_key_on_another_operation_is_its_own_claim(
        self,
        idempotency: IdempotencyRepository,
        run_id: str
    ) -> None:
        reserve(idempotency=idempotency, run_id=run_id)

        assert reserve(
            idempotency=idempotency,
            run_id=run_id,
            operation=JOB_KIND_RECOLLECT
        ) is None
        assert idempotency.get(
            operation=JOB_KIND_RECOLLECT,
            key=KEY
        ) is not None

    def test_a_key_used_on_two_operations_leaves_both_claimed(
        self,
        idempotency: IdempotencyRepository,
        run_id: str
    ) -> None:
        # One is not allowed to answer for the other, and a claim
        # that quietly did nothing would read back as neither.
        reserve(idempotency=idempotency, run_id=run_id)
        reserve(
            idempotency=idempotency,
            run_id=run_id,
            operation=JOB_KIND_RECOLLECT
        )
        complete(idempotency=idempotency, operation=JOB_KIND_RECOLLECT)

        assert idempotency.get(
            operation=JOB_KIND_SEND,
            key=KEY
        ).status_code is None
        assert idempotency.get(
            operation=JOB_KIND_RECOLLECT,
            key=KEY
        ).status_code == ACCEPTED

    def test_an_operation_a_key_cannot_be_used_on_is_refused(
        self,
        idempotency: IdempotencyRepository,
        run_id: str
    ) -> None:
        with pytest.raises(ValidationError) as error:
            reserve(
                idempotency=idempotency,
                run_id=run_id,
                operation='delete-everything'
            )

        assert 'Use one of' in str(error.value)

    def test_claiming_against_a_run_that_is_not_there_is_refused(
        self,
        idempotency: IdempotencyRepository
    ) -> None:
        # 'OR IGNORE' gives way to the primary key and to nothing
        # else, so a run that does not exist still fails.
        with pytest.raises(ValidationError):
            reserve(idempotency=idempotency, run_id='no-such-run')


class TestAKeyThatHasAlreadyBeenUsed:
    def test_a_second_claim_is_given_the_first_one(
        self,
        idempotency: IdempotencyRepository,
        run_id: str
    ) -> None:
        reserve(idempotency=idempotency, run_id=run_id)

        assert reserve(
            idempotency=idempotency,
            run_id=run_id
        ).fingerprint == FINGERPRINT

    def test_a_second_claim_does_not_replace_the_first(
        self,
        idempotency: IdempotencyRepository,
        run_id: str,
        other_run_id: str
    ) -> None:
        reserve(idempotency=idempotency, run_id=run_id)
        reserve(
            idempotency=idempotency,
            run_id=other_run_id,
            fingerprint='expectedShiftCount=99'
        )
        record = idempotency.get(operation=JOB_KIND_SEND, key=KEY)

        assert record.run_id == run_id
        assert record.fingerprint == FINGERPRINT

    def test_a_claim_that_asked_for_something_else_is_visible(
        self,
        idempotency: IdempotencyRepository,
        run_id: str
    ) -> None:
        # The repository reports the difference rather than judging
        # it: only the caller knows what its own fingerprint means.
        reserve(idempotency=idempotency, run_id=run_id)

        assert reserve(
            idempotency=idempotency,
            run_id=run_id,
            fingerprint='expectedShiftCount=99'
        ).fingerprint == FINGERPRINT

    def test_a_claim_on_a_write_still_running_has_no_answer(
        self,
        idempotency: IdempotencyRepository,
        run_id: str
    ) -> None:
        reserve(idempotency=idempotency, run_id=run_id)

        assert reserve(
            idempotency=idempotency,
            run_id=run_id
        ).status_code is None


class TestRecordingWhatAWriteAnswered:
    def test_an_answer_is_read_back_as_it_was_recorded(
        self,
        idempotency: IdempotencyRepository,
        run_id: str
    ) -> None:
        reserve(idempotency=idempotency, run_id=run_id)
        complete(idempotency=idempotency)
        record = idempotency.get(operation=JOB_KIND_SEND, key=KEY)

        assert record.status_code == ACCEPTED
        assert record.response == ANSWER

    def test_a_replay_is_given_the_answer_instead_of_claiming(
        self,
        idempotency: IdempotencyRepository,
        run_id: str
    ) -> None:
        reserve(idempotency=idempotency, run_id=run_id)
        complete(idempotency=idempotency)
        replay = reserve(idempotency=idempotency, run_id=run_id)

        assert replay.status_code == ACCEPTED
        assert replay.response == ANSWER

    def test_answering_twice_is_refused(
        self,
        idempotency: IdempotencyRepository,
        run_id: str
    ) -> None:
        reserve(idempotency=idempotency, run_id=run_id)
        complete(idempotency=idempotency)

        with pytest.raises(ValidationError):
            complete(idempotency=idempotency)

    def test_answering_a_key_nobody_claimed_is_refused(
        self,
        idempotency: IdempotencyRepository
    ) -> None:
        with pytest.raises(ValidationError):
            complete(idempotency=idempotency)

    def test_answering_the_wrong_operation_is_refused(
        self,
        idempotency: IdempotencyRepository,
        run_id: str
    ) -> None:
        reserve(idempotency=idempotency, run_id=run_id)

        with pytest.raises(ValidationError):
            complete(
                idempotency=idempotency,
                operation=JOB_KIND_RECOLLECT
            )

    def test_answering_an_operation_a_key_cannot_be_used_on_is_refused(
        self,
        idempotency: IdempotencyRepository,
        run_id: str
    ) -> None:
        reserve(idempotency=idempotency, run_id=run_id)

        with pytest.raises(ValidationError) as error:
            complete(idempotency=idempotency, operation='delete-everything')

        assert 'Use one of' in str(error.value)


class TestWhatAClaimOutlives:
    def test_a_claim_goes_when_its_run_does(
        self,
        idempotency: IdempotencyRepository,
        runs: RunRepository,
        run_id: str
    ) -> None:
        # Unlike the record of what was sent, a claim is about one
        # request rather than about duplicate safety, so it has no
        # reason to outlive the run it was made against.
        reserve(idempotency=idempotency, run_id=run_id)
        complete(idempotency=idempotency)
        runs.delete(run_id=run_id)

        assert idempotency.get(operation=JOB_KIND_SEND, key=KEY) is None
