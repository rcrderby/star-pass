#!/usr/bin/env python3
""" Tests for the record of what a send put into Amplify. """

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
from typing import Callable

# Imports - Third-Party
import pytest

# Imports - Local
from star_pass import _derived
from star_pass._repository import _sent
from star_pass._exceptions import ValidationError
from star_pass._records import Event, EventRole, ShiftIdentity
from star_pass._repository import RunRepository, SentShiftRepository

# Constants
PRINCIPAL = 'static-token'
KEY = 'a-key-a-caller-supplied'
OTHER_IDENTITY: ShiftIdentity = ('654321', '2026-09-06', '09:00', '23:00')


def record_one(
    sent: SentShiftRepository,
    run_id: str,
    identity: ShiftIdentity
) -> None:
    sent.record(
        run_id=run_id,
        identities=(identity,),
        principal_id=PRINCIPAL,
        idempotency_key=KEY
    )


class TestRecordingWhatWasSent:
    def test_a_recorded_shift_comes_back_in_the_record(
        self,
        sent: SentShiftRepository,
        run_id: str,
        shift_identity: ShiftIdentity
    ) -> None:
        record_one(sent=sent, run_id=run_id, identity=shift_identity)

        assert sent.already_sent(run_id=run_id) == {shift_identity}

    def test_a_run_that_has_sent_nothing_has_an_empty_record(
        self,
        sent: SentShiftRepository,
        run_id: str
    ) -> None:
        assert sent.already_sent(run_id=run_id) == set()

    def test_a_whole_batch_is_recorded(
        self,
        sent: SentShiftRepository,
        run_id: str,
        shift_identity: ShiftIdentity
    ) -> None:
        sent.record(
            run_id=run_id,
            identities=(shift_identity, OTHER_IDENTITY),
            principal_id=PRINCIPAL,
            idempotency_key=KEY
        )

        assert sent.already_sent(run_id=run_id) == {
            shift_identity,
            OTHER_IDENTITY
        }

    def test_an_empty_batch_records_nothing(
        self,
        sent: SentShiftRepository,
        run_id: str
    ) -> None:
        assert sent.record(
            run_id=run_id,
            identities=(),
            principal_id=PRINCIPAL,
            idempotency_key=KEY
        ) == []
        assert sent.already_sent(run_id=run_id) == set()

    def test_a_returned_record_carries_the_identity_it_was_given(
        self,
        sent: SentShiftRepository,
        run_id: str,
        shift_identity: ShiftIdentity
    ) -> None:
        need_id, date, shift_start, shift_end = shift_identity

        shift = sent.record(
            run_id=run_id,
            identities=(shift_identity,),
            principal_id=PRINCIPAL,
            idempotency_key=KEY
        )[0]

        assert shift.run_id == run_id
        assert shift.need_id == need_id
        assert shift.date == date
        assert shift.shift_start == shift_start
        assert shift.shift_end == shift_end


class TestWhatTheRecordSaysAboutTheSend:
    def test_a_shift_records_who_sent_it_and_under_which_key(
        self,
        sent: SentShiftRepository,
        run_id: str,
        shift_identity: ShiftIdentity
    ) -> None:
        record_one(sent=sent, run_id=run_id, identity=shift_identity)
        shift = sent.list_for_run(run_id=run_id)[0]

        assert shift.principal_id == PRINCIPAL
        assert shift.idempotency_key == KEY

    def test_a_shift_records_when_it_was_sent(
        self,
        sent: SentShiftRepository,
        run_id: str,
        shift_identity: ShiftIdentity
    ) -> None:
        record_one(sent=sent, run_id=run_id, identity=shift_identity)

        assert sent.list_for_run(run_id=run_id)[0].sent_at.endswith('+00:00')

    def test_the_record_is_read_back_in_a_stable_order(
        self,
        sent: SentShiftRepository,
        run_id: str,
        shift_identity: ShiftIdentity
    ) -> None:
        sent.record(
            run_id=run_id,
            identities=(OTHER_IDENTITY, shift_identity),
            principal_id=PRINCIPAL,
            idempotency_key=KEY
        )

        assert [
            shift.need_id for shift in sent.list_for_run(run_id=run_id)
        ] == ['123456', '654321']

    def test_the_record_only_holds_the_run_asked_about(
        self,
        sent: SentShiftRepository,
        run_id: str,
        other_run_id: str,
        shift_identity: ShiftIdentity
    ) -> None:
        record_one(sent=sent, run_id=other_run_id, identity=shift_identity)

        assert sent.already_sent(run_id=run_id) == set()
        assert sent.already_sent(run_id=other_run_id) == {shift_identity}


class TestWhatTheRecordRefuses:
    def test_recording_the_same_shift_twice_is_refused(
        self,
        sent: SentShiftRepository,
        run_id: str,
        shift_identity: ShiftIdentity
    ) -> None:
        record_one(sent=sent, run_id=run_id, identity=shift_identity)

        with pytest.raises(ValidationError):
            record_one(sent=sent, run_id=run_id, identity=shift_identity)

    def test_the_same_shift_is_refused_however_much_later(
        self,
        sent: SentShiftRepository,
        run_id: str,
        shift_identity: ShiftIdentity,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # What makes a shift the same one is the run and the four
        # columns it is identified by, and nothing else.  A record
        # that also keyed on the time would refuse a retry made in
        # the same second and accept the same shift a minute later.
        record_one(sent=sent, run_id=run_id, identity=shift_identity)
        monkeypatch.setattr(
            _sent,
            'utc_now',
            lambda: '2099-01-01T00:00:00+00:00'
        )

        with pytest.raises(ValidationError):
            record_one(sent=sent, run_id=run_id, identity=shift_identity)

    def test_recording_against_a_run_that_is_not_there_is_refused(
        self,
        sent: SentShiftRepository,
        shift_identity: ShiftIdentity
    ) -> None:
        with pytest.raises(ValidationError):
            record_one(
                sent=sent,
                run_id='no-such-run',
                identity=shift_identity
            )

    def test_a_run_holding_a_sent_shift_cannot_be_deleted(
        self,
        sent: SentShiftRepository,
        runs: RunRepository,
        run_id: str,
        shift_identity: ShiftIdentity
    ) -> None:
        # The record duplicate safety rests on is never purged,
        # so the reference does not cascade and the deletion fails
        # instead of taking the record with it.
        record_one(sent=sent, run_id=run_id, identity=shift_identity)

        with pytest.raises(ValidationError):
            runs.delete(run_id=run_id)

        assert sent.already_sent(run_id=run_id) == {shift_identity}

    def test_a_run_that_sent_nothing_can_still_be_deleted(
        self,
        runs: RunRepository,
        run_id: str
    ) -> None:
        runs.delete(run_id=run_id)

        assert runs.get(run_id=run_id) is None


class TestTheRecordAndTheIdentityAgree:
    def test_the_record_is_keyed_by_the_identity_the_core_derives(
        self,
        sent: SentShiftRepository,
        run_id: str,
        make_event: Callable[..., Event]
    ) -> None:
        # The two have to be the same four values.  Derived one way
        # and stored another, a retry would ask a question the record
        # could not answer.
        event: Event = make_event()
        role: EventRole = event.roles[0]
        identity = _derived.shift_identity(event=event, role=role)

        record_one(sent=sent, run_id=run_id, identity=identity)
        shift = sent.list_for_run(run_id=run_id)[0]

        assert (
            shift.need_id,
            shift.date,
            shift.shift_start,
            shift.shift_end
        ) == (
            role.need_id,
            event.date,
            event.shift_start,
            event.shift_end
        )
