#!/usr/bin/env python3
""" What to read to answer a question about a run.

    A question like "show me this run" is answered from four places:
    the run, the events of its current revision, the opportunities
    labelling them, and the log of what was done to it.  Deciding
    which four, and reading them on one connection, is the same
    decision wherever the question is asked -- and it is asked twice,
    once by the service and once by the command line client reading
    the same database in the same process (D2).

    So the read plan lives here, below both of them.  Two copies would
    drift, and a mode that read one fewer thing than the other would
    answer a question differently without anything saying so.

    One connection per answer, not one per read: four reads on four
    connections would describe the run at four moments, and a caller
    would see events that had already been replaced beside a log that
    knew it.

    A run that is not there is reported as None rather than raised.
    The repository reports a value it cannot use and a missing run the
    same way, and only the caller knows which of those it asked for.
"""

# Imports - Python Standard Library
import sqlite3
from dataclasses import dataclass
from typing import List, Optional, Tuple

# Imports - Local
from ._records import Event, LogEntry, Opportunity, Revision, Run
from ._repository import (
    ChangeLogRepository,
    EventRepository,
    RevisionRepository,
    RunRepository
)


@dataclass(frozen=True)
class RunDetail:
    """ Everything one read of a run gathered.

        Attributes:
            run (Run):
                The run itself.

            events (List[Event]):
                The current revision's events.

            opportunities (List[Opportunity]):
                Every opportunity the run resolved.

            log (List[LogEntry]):
                The run's change log.
    """

    run: Run
    events: List[Event]
    opportunities: List[Opportunity]
    log: List[LogEntry]


def read_run_detail(
        connection: sqlite3.Connection,
        run_id: str
) -> Optional[RunDetail]:
    """ Read a run and everything shown beside it.

        Args:
            connection (sqlite3.Connection):
                Connection to read on.

            run_id (str):
                Run to read.

        Raises:
            UpstreamError:
                If the run cannot be read.

        Returns:
            detail (RunDetail | None):
                Everything about the run, or None when there is no
                such run.
    """

    runs = RunRepository(connection=connection)
    run = runs.get(run_id=run_id)

    if run is None:
        return None

    return RunDetail(
        run=run,
        # A run before its first revision reports revision 0, which
        # holds nothing and reads back as nothing.  No guard for it:
        # the answer is already the right one.
        events=EventRepository(connection=connection).list_all(
            run_id=run_id,
            revision=run.current_revision
        ),
        opportunities=runs.get_opportunities(run_id=run_id),
        log=ChangeLogRepository(connection=connection).list_all(
            run_id=run_id
        )
    )


def read_run_history(
        connection: sqlite3.Connection,
        run_id: str
) -> Optional[Tuple[Run, List[Revision]]]:
    """ Read a run and its revisions together.

        The run is read as well as the revisions, and not only to know
        it exists: it is what says which revision is the current one.

        Args:
            connection (sqlite3.Connection):
                Connection to read on.

            run_id (str):
                Run to read the history of.

        Raises:
            UpstreamError:
                If the run cannot be read.

        Returns:
            history (Tuple[Run, List[Revision]] | None):
                The run and its revisions oldest first, or None when
                there is no such run.
    """

    run = RunRepository(connection=connection).get(run_id=run_id)

    if run is None:
        return None

    return (
        run,
        RevisionRepository(connection=connection).list_all(run_id=run_id)
    )


def read_run_for_send(
        connection: sqlite3.Connection,
        run_id: str
) -> Optional[Tuple[List[Event], List[Opportunity]]]:
    """ Read what a send would work from.

        The events of the current revision and the opportunities
        labelling them: a preview assembled from two moments could
        label a shift with a title that no longer belongs to it.

        Args:
            connection (sqlite3.Connection):
                Connection to read on.

            run_id (str):
                Run to read.

        Raises:
            UpstreamError:
                If the run cannot be read.

        Returns:
            gathered (Tuple[List[Event], List[Opportunity]] | None):
                The events and the opportunities, or None when there
                is no such run.
    """

    runs = RunRepository(connection=connection)
    run = runs.get(run_id=run_id)

    if run is None:
        return None

    return (
        EventRepository(connection=connection).list_all(
            run_id=run_id,
            revision=run.current_revision
        ),
        runs.get_opportunities(run_id=run_id)
    )
