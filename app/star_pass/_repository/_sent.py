#!/usr/bin/env python3
""" What a send put into Amplify, and who put it there. """

# Imports - Python Standard Library
import sqlite3
from typing import List, Sequence, Set

# Imports - Local
from .._database import execute_many, query
from .._logging import get_logger
from .._records import SentShift, ShiftIdentity
from ._common import insert_statement, Repository, utc_now

# Constants
# Columns a sent shift is written with, in the order the record's
# values are supplied.  The first five are the primary key: the run,
# and the four that make a 'ShiftIdentity'.
SENT_SHIFT_COLUMNS = (
    'run_id',
    'need_id',
    'date',
    'shift_start',
    'shift_end',
    'sent_at',
    'principal_id',
    'idempotency_key'
)

# Module logger
logger = get_logger(__name__)


def _to_sent_shift(
        row: sqlite3.Row
) -> SentShift:
    """ Build a sent shift record from a row.

        Args:
            row (sqlite3.Row):
                A row from the sent shifts table.

        Returns:
            shift (SentShift):
                The shift the row describes.
    """

    return SentShift(
        run_id=row['run_id'],
        need_id=row['need_id'],
        date=row['date'],
        shift_start=row['shift_start'],
        shift_end=row['shift_end'],
        sent_at=row['sent_at'],
        principal_id=row['principal_id'],
        idempotency_key=row['idempotency_key']
    )


class SentShiftRepository(Repository):
    """ The rows a run's sends created.

        Written as a set per batch rather than one row at a time,
        because that is how a send reaches Amplify: one request per
        opportunity carrying every shift for it.  Recording the batch
        as a unit is what makes the record match what actually
        happened -- a row written before its request succeeded would
        claim a shift exists that does not.

        Nothing here deletes.  The record is what duplicate safety
        rests on, so it outlives the CSVs and the job logs that expire
        around it (D12).
    """

    def record(
            self,
            run_id: str,
            identities: Sequence[ShiftIdentity],
            principal_id: str,
            idempotency_key: str
    ) -> List[SentShift]:
        """ Record shifts a send has created.

            Recording the same shift twice is refused rather than
            ignored: a send that reaches this with a shift already in
            the record has lost track of what it did, and writing the
            second row quietly would leave that undetectable.  A retry
            asks 'already_sent' first and sends the difference.

            Args:
                run_id (str):
                    Run whose send created them.

                identities (Sequence[ShiftIdentity]):
                    The shifts created, as need ID, date, start and
                    end.

                principal_id (str):
                    Who sent them (D13).

                idempotency_key (str):
                    The key the send was made under (D13).

            Raises:
                ValidationError:
                    If there is no such run, or one of the shifts is
                    already recorded.

                UpstreamError:
                    If the record cannot be written.

            Returns:
                shifts (List[SentShift]):
                    The records as stored, in the order supplied.
        """

        sent_at = utc_now()
        shifts = [
            SentShift(
                run_id=run_id,
                need_id=need_id,
                date=date,
                shift_start=shift_start,
                shift_end=shift_end,
                sent_at=sent_at,
                principal_id=principal_id,
                idempotency_key=idempotency_key
            )
            for need_id, date, shift_start, shift_end in identities
        ]

        execute_many(
            connection=self._connection,
            statement=insert_statement(
                table='sent_shifts',
                columns=SENT_SHIFT_COLUMNS
            ),
            parameters=[
                (
                    shift.run_id,
                    shift.need_id,
                    shift.date,
                    shift.shift_start,
                    shift.shift_end,
                    shift.sent_at,
                    shift.principal_id,
                    shift.idempotency_key
                )
                for shift in shifts
            ]
        )

        message = f'Recorded {len(shifts)} sent shift(s) for run {run_id}'
        logger.debug(message)

        return shifts

    def already_sent(
            self,
            run_id: str
    ) -> Set[ShiftIdentity]:
        """ Return the shifts a run has already created.

            A set rather than a list, because the only question asked
            of it is whether a shift about to be sent is in it.

            Args:
                run_id (str):
                    Run to read the record of.

            Raises:
                UpstreamError:
                    If the record cannot be read.

            Returns:
                identities (Set[ShiftIdentity]):
                    Every shift the run has created.
        """

        rows = query(
            connection=self._connection,
            statement=(
                'SELECT need_id, date, shift_start, shift_end '
                'FROM sent_shifts WHERE run_id = ?'
            ),
            parameters=(run_id,)
        )

        return {
            (
                row['need_id'],
                row['date'],
                row['shift_start'],
                row['shift_end']
            )
            for row in rows
        }

    def list_for_run(
            self,
            run_id: str
    ) -> List[SentShift]:
        """ Return a run's sent shifts, in the order they were created.

            Ordered by when they were sent and then by identity, so
            that the shifts of one batch keep a stable order among
            themselves: a batch is recorded in one statement and every
            row in it carries the same timestamp.

            Args:
                run_id (str):
                    Run to read the record of.

            Raises:
                UpstreamError:
                    If the record cannot be read.

            Returns:
                shifts (List[SentShift]):
                    Every shift the run created.
        """

        rows = query(
            connection=self._connection,
            statement=(
                'SELECT * FROM sent_shifts WHERE run_id = ? '
                'ORDER BY sent_at, need_id, date, shift_start, shift_end'
            ),
            parameters=(run_id,)
        )

        return [_to_sent_shift(row=row) for row in rows]
