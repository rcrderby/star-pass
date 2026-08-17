#!/usr/bin/env python3
""" Writes that have been asked for, and what each one answered. """

# Imports - Python Standard Library
import json
import sqlite3
from typing import Any, Dict, Optional

# Imports - Local
from .._database import execute, query_one
from .._logging import get_logger
from .._records import IdempotencyRecord, IDEMPOTENT_OPERATIONS
from ._common import (
    insert_statement,
    Repository,
    require_one_of,
    require_row,
    utc_now
)

# Constants
# Columns a reservation is written with.  The response columns are not
# among them: they are what the write answered, and a reservation is
# made before it has.
RESERVATION_COLUMNS = (
    'operation',
    'key',
    'run_id',
    'fingerprint',
    'principal_id',
    'created_at'
)

# What an operation is called in a message, so that a caller reading
# one is told the vocabulary rather than the column.
OPERATION_DESCRIPTION = 'an operation an idempotency key can be used on'

# Module logger
logger = get_logger(__name__)


def _to_record(
        row: sqlite3.Row
) -> IdempotencyRecord:
    """ Build an idempotency record from a row.

        Args:
            row (sqlite3.Row):
                A row from the idempotency keys table.

        Returns:
            record (IdempotencyRecord):
                The reservation the row describes.
    """

    response = row['response']

    return IdempotencyRecord(
        operation=row['operation'],
        key=row['key'],
        run_id=row['run_id'],
        fingerprint=row['fingerprint'],
        principal_id=row['principal_id'],
        created_at=row['created_at'],
        status_code=row['status_code'],
        response=json.loads(response) if response is not None else None
    )


class IdempotencyRepository(Repository):
    """ Reservations against a key, and the answers they were completed with.

        A reservation is made before the write and completed after it.
        Both halves matter: without the first, two requests carrying
        one key would both find nothing recorded and both write;
        without the second, a replay would have no answer to be given
        and would have to write again to produce one.

        The reservation is an insert that gives way rather than a read
        followed by a write.  Two requests arriving together would both
        read nothing, and the primary key is what makes the second one
        find the first instead of joining it.
    """

    def reserve(
            self,
            operation: str,
            key: str,
            run_id: str,
            fingerprint: str,
            principal_id: str
    ) -> Optional[IdempotencyRecord]:
        """ Claim a key for a write, or report who claimed it first.

            Args:
                operation (str):
                    Which write, one of 'IDEMPOTENT_OPERATIONS'.

                key (str):
                    What the caller supplied.

                run_id (str):
                    Run the write acts on.

                fingerprint (str):
                    What the request asked for, as the caller
                    summarized it, for comparing against a replay.

                principal_id (str):
                    Who asked (D13).

            Raises:
                ValidationError:
                    If the operation is not one a key can be used on,
                    or there is no such run.

                UpstreamError:
                    If the reservation cannot be written.

            Returns:
                existing (IdempotencyRecord | None):
                    The reservation that was already there, or None
                    when this call made it.  A caller that is given one
                    is a replay: it compares the fingerprint, and
                    answers from the stored response or reports that
                    the first request is still running.
        """

        require_one_of(
            value=operation,
            allowed=IDEMPOTENT_OPERATIONS,
            description=OPERATION_DESCRIPTION
        )

        # 'OR IGNORE' gives way to the primary key and nothing else: a
        # run that does not exist is a foreign key violation, which
        # SQLite raises whatever the conflict clause says.  A key
        # already taken is the one case that has to come back as an
        # answer rather than an error, because it is the ordinary way
        # a replay arrives.
        cursor = execute(
            connection=self._connection,
            statement=insert_statement(
                table='idempotency_keys',
                columns=RESERVATION_COLUMNS,
                or_ignore=True
            ),
            parameters=(
                operation,
                key,
                run_id,
                fingerprint,
                principal_id,
                utc_now()
            )
        )

        if cursor.rowcount:
            message = f'Reserved a {operation} for run {run_id}'
            logger.debug(message)

            return None

        message = (
            f'An idempotency key already reserved a {operation}; '
            'answering from what it recorded'
        )
        logger.info(message)

        return self.get(
            operation=operation,
            key=key
        )

    def complete(
            self,
            operation: str,
            key: str,
            status_code: int,
            response: Dict[str, Any]
    ) -> None:
        """ Record what a reserved write answered.

            Only a reservation with no answer yet is completed.  One
            that already has an answer is a write that finished, and
            overwriting it would mean a replay of the first request is
            given the second one's result.

            Args:
                operation (str):
                    Which write, one of 'IDEMPOTENT_OPERATIONS'.

                key (str):
                    The key it was reserved under.

                status_code (int):
                    The status the write answered with.

                response (Dict[str, Any]):
                    The body it answered with, which a replay is given
                    in place of writing again.

            Raises:
                ValidationError:
                    If the operation is not one a key can be used on,
                    or nothing is reserved under the key and still
                    waiting for an answer.

                UpstreamError:
                    If the answer cannot be written.

            Returns:
                None.
        """

        require_one_of(
            value=operation,
            allowed=IDEMPOTENT_OPERATIONS,
            description=OPERATION_DESCRIPTION
        )

        cursor = execute(
            connection=self._connection,
            statement=(
                'UPDATE idempotency_keys SET status_code = ?, '
                'response = ? WHERE operation = ? AND key = ? '
                'AND status_code IS NULL'
            ),
            parameters=(
                status_code,
                json.dumps(response, sort_keys=True),
                operation,
                key
            )
        )

        require_row(
            cursor=cursor,
            message=(
                f'This {operation} cannot be recorded: nothing is '
                'reserved under its idempotency key, or what is '
                'reserved has already answered.'
            )
        )

        return None

    def get(
            self,
            operation: str,
            key: str
    ) -> Optional[IdempotencyRecord]:
        """ Return what a key reserved.

            Args:
                operation (str):
                    Which write, one of 'IDEMPOTENT_OPERATIONS'.

                key (str):
                    The key to look up.

            Raises:
                UpstreamError:
                    If the reservation cannot be read.

            Returns:
                record (IdempotencyRecord | None):
                    The reservation, or None when the key has not been
                    used on that operation.
        """

        row = query_one(
            connection=self._connection,
            statement=(
                'SELECT * FROM idempotency_keys '
                'WHERE operation = ? AND key = ?'
            ),
            parameters=(operation, key)
        )

        return _to_record(row=row) if row is not None else None
