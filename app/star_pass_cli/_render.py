#!/usr/bin/env python3
""" Turning an answer into something to read in a terminal.

    Rendering only.  Everything here takes what a client answered --
    the same document in either mode -- and returns text, so what is
    shown cannot depend on which mode produced it.

    The window is the one place a value is converted rather than
    printed.  The contract carries an exclusive end, because that is
    what the server stores and what arithmetic wants; a person reading
    a run means the last day it covers.  Converting here is what
    CLAUDE.md asks for -- times and window bounds are converted for
    display -- and it keeps the authoritative value unconverted
    everywhere else.
"""

# Imports - Python Standard Library
from datetime import date, timedelta
from typing import Any, Dict, List, Sequence

# Constants
# Two spaces between columns: enough to separate them, little enough
# that a narrow terminal still fits a run's row.
COLUMN_GAP = '  '

# What a run's row shows, in order.
RUN_HEADERS = (
    'ID',
    'CALENDAR',
    'WINDOW',
    'STATUS',
    'EVENTS',
    'SHIFTS',
    'UNMATCHED',
    'REVISED'
)

# Shown in a column that has nothing to show, so a row keeps its shape.
NOTHING = '-'


def last_day(
        window: Dict[str, Any]
) -> str:
    """ Return the last day a window covers, as a reader means it.

        Args:
            window (Dict[str, Any]):
                A window from an answer, whose end is exclusive.

        Returns:
            day (str):
                The last day covered, as an ISO date.
    """

    return str(
        date.fromisoformat(window['end']) - timedelta(days=1)
    )


def window_text(
        window: Dict[str, Any]
) -> str:
    """ Return a window as a reader means it.

        Args:
            window (Dict[str, Any]):
                A window from an answer.

        Returns:
            text (str):
                The first and last days it covers.
    """

    return f'{window["start"]} to {last_day(window=window)}'


def run_row(
        run: Dict[str, Any]
) -> List[str]:
    """ Return one run as a row.

        Args:
            run (Dict[str, Any]):
                A run from an answer.

        Returns:
            row (List[str]):
                One value per column in 'RUN_HEADERS'.
    """

    counts = run['counts']

    return [
        run['id'],
        run['calendar'],
        window_text(window=run['window']),
        run['status'],
        str(counts['events']),
        str(counts['shifts']),
        str(counts['unmatched']) if counts['unmatched'] else NOTHING,
        run['revisedAt']
    ]


def table(
        headers: Sequence[str],
        rows: Sequence[Sequence[str]]
) -> str:
    """ Return rows as aligned columns under their headers.

        Args:
            headers (Sequence[str]):
                One name per column.

            rows (Sequence[Sequence[str]]):
                The rows, each as wide as the headers.

        Returns:
            text (str):
                The table, without a trailing newline.
    """

    widths = [
        max(
            len(str(header)),
            *(len(str(row[column])) for row in rows)
        ) if rows else len(str(header))
        for column, header in enumerate(headers)
    ]

    return '\n'.join(
        COLUMN_GAP.join(
            str(value).ljust(width)
            for value, width in zip(line, widths)
        ).rstrip()
        for line in (headers, *rows)
    )


def runs_table(
        runs: Sequence[Dict[str, Any]]
) -> str:
    """ Return every run as a table.

        Args:
            runs (Sequence[Dict[str, Any]]):
                The runs an answer carried.

        Returns:
            text (str):
                The table, or a sentence when there are no runs.
    """

    if not runs:
        return 'No runs yet.'

    return table(
        headers=RUN_HEADERS,
        rows=[run_row(run=run) for run in runs]
    )
