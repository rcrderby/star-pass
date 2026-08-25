#!/usr/bin/env python3
""" What carries a database that already exists forward.

    Separate from the schema statements beside it because those create
    things and these change a thing that is already there: a
    'CREATE TABLE IF NOT EXISTS' does nothing at all to a table that
    exists, so a column added to one arrives here or not at all.

    A version's steps are the record of one release's change to the
    shape of the data, and nothing here may be edited after a release
    has run it: a database already carried past a step will never run
    it again, so a correction is a further step.
"""

# Imports - Python Standard Library
from dataclasses import dataclass


@dataclass(frozen=True)
class Step:
    """ One statement that carries a database forward.

        Most add a column, and their statement declares it exactly as
        the create above declares it, so a database carried here and
        one built here are the same database.  Some fill one instead:
        a column added to rows that already exist arrives empty, and
        what belongs in it is worked out from what those rows already
        say.

        Attributes:
            table (str):
                Table the step is about.

            column (str):
                The column that says whether the step still has
                something to do -- the one being added, the one a
                filling step fills, or the one a step removes.  Every
                step of a version is asked this before any of them
                runs, which is what lets a fill be gated on the column
                it fills rather than needing a test of its own.

            removes (bool):
                Which way the question reads.  A step that adds or
                fills has something to do while its column is
                **absent**; a step that removes one has something to
                do while it is still **there**.  The same question
                asked the other way round, and it is needed the
                moment a version drops a column from a table other
                than the one it adds to -- version 8 does, so a drop
                cannot borrow the gate of the column that replaced it.

            statement (str):
                What to run.
    """

    table: str
    column: str
    statement: str
    removes: bool = False


# What carries a database that already exists forward, by the version
# each step raises it to.  Separate from the statements above because
# those create things and these change a thing that is already there:
# a 'CREATE TABLE IF NOT EXISTS' does nothing at all to a table that
# exists, so a column added to one arrives here or not at all.
#
# A step runs on a database below its version whose table still lacks
# the column.  The second half of that matters: a database from before
# the table itself existed is given the current table by the
# statements above, so there is nothing left for the step to add and
# adding it again would fail.
#
# Nothing here may be edited after a release has run it, because a
# database already carried past it will never run it again; a
# correction is a further step.
MIGRATIONS = {
    4: (
        # Which process is holding a job, so a sweep of what a stopped
        # process left behind can leave alone what it never held.  The
        # service and the command line share a database, and a sweep
        # that took everything unfinished would mark a live send
        # interrupted.
        #
        # The default is what a job written before the column existed
        # was held by: the service, which was the only thing writing
        # jobs then.  It is a literal because a schema statement takes
        # one, and it is the value of '_records.JOB_HOLDER_SERVICE'.
        Step(
            table='jobs',
            column='held_by',
            statement=(
                'ALTER TABLE jobs '
                "ADD COLUMN held_by TEXT NOT NULL DEFAULT 'service'"
            )
        ),
    ),
    7: (
        # How a revision came to exist, and the revision it was made
        # from.  Both were one column of English written by the core
        # and printed unchanged by every client, so neither client
        # could word it and a change of wording would have left the
        # revisions already recorded saying the old thing.
        #
        # The default is false of every row and is corrected by the
        # four statements below, which run in the same transaction:
        # SQLite cannot add a column that is NOT NULL without one, and
        # a default that was true of some rows would be a guess about
        # the rest.
        Step(
            table='revisions',
            column='kind',
            statement=(
                'ALTER TABLE revisions '
                "ADD COLUMN kind TEXT NOT NULL DEFAULT ''"
            )
        ),
        Step(
            table='revisions',
            column='source',
            statement='ALTER TABLE revisions ADD COLUMN source INTEGER'
        ),
        # The four sentences the core ever wrote, read back into what
        # they were saying.  Gated on 'kind', which is asked about
        # before any statement of this version runs and so is still
        # absent when these are chosen.
        Step(
            table='revisions',
            column='kind',
            statement=(
                "UPDATE revisions SET kind = 'collected' "
                "WHERE label = 'As collected'"
            )
        ),
        Step(
            table='revisions',
            column='kind',
            statement=(
                "UPDATE revisions SET kind = 'recollected' "
                "WHERE label = 'As recollected'"
            )
        ),
        Step(
            table='revisions',
            column='kind',
            statement=(
                "UPDATE revisions SET kind = 'continued', "
                "source = CAST("
                "SUBSTR(label, LENGTH('Continued from revision ') + 1) "
                'AS INTEGER) '
                "WHERE label LIKE 'Continued from revision %'"
            )
        ),
        Step(
            table='revisions',
            column='kind',
            statement=(
                "UPDATE revisions SET kind = 'reverted', "
                "source = CAST("
                "SUBSTR(label, LENGTH('Reverted to revision ') + 1) "
                'AS INTEGER) '
                "WHERE label LIKE 'Reverted to revision %'"
            )
        ),
        # And the sentence goes.  It has to: an insert now names
        # 'kind' and 'source' and not 'label', so a NOT NULL column
        # left behind would refuse every revision written after this.
        # A column and not the table -- 'events' points at
        # 'revisions' with a cascade, so rebuilding the table the
        # portable way would delete every event in the database.
        Step(
            table='revisions',
            column='kind',
            statement='ALTER TABLE revisions DROP COLUMN label'
        )
    ),
    8: (
        # What a shift asks of its event moves from the run's
        # opportunity to the event's role (D25).  One Amplify listing
        # can be named by categories that time it differently -- need
        # 905196 by three -- and a table keyed '(run_id, need_id)'
        # can hold only one of them, which is why the 'events'
        # calendar has never been collected successfully.
        #
        # The defaults are what a role written before these existed is
        # timed by until the fill below corrects it: SQLite cannot add
        # a NOT NULL column without one, and the create above declares
        # these without a default because a role written now always
        # carries its own.
        Step(
            table='event_roles',
            column='offset_start',
            statement=(
                'ALTER TABLE event_roles '
                'ADD COLUMN offset_start INTEGER NOT NULL DEFAULT 0'
            )
        ),
        Step(
            table='event_roles',
            column='offset_end',
            statement=(
                'ALTER TABLE event_roles '
                'ADD COLUMN offset_end INTEGER NOT NULL DEFAULT 0'
            )
        ),
        Step(
            table='event_roles',
            column='max_length',
            statement=(
                'ALTER TABLE event_roles ADD COLUMN max_length INTEGER'
            )
        ),
        Step(
            table='event_roles',
            column='default_slots',
            statement=(
                'ALTER TABLE event_roles '
                'ADD COLUMN default_slots INTEGER NOT NULL DEFAULT 0'
            )
        ),
        # Every role takes the timing of the opportunity it names,
        # which is where that role's timing was recorded until now and
        # so is exactly what it was collected with.  Gated on
        # 'offset_start', which is asked about before any statement of
        # this version runs and so is still absent when this is
        # chosen.  'default_slots' falls back to what the role holds:
        # a role whose opportunity is missing has no default recorded
        # anywhere else, and what it holds is the nearest true thing.
        Step(
            table='event_roles',
            column='offset_start',
            statement=(
                'UPDATE event_roles SET '
                'offset_start = COALESCE(('
                '    SELECT o.offset_start FROM opportunities AS o'
                '    WHERE o.run_id = event_roles.run_id'
                '      AND o.need_id = event_roles.need_id'
                '), 0), '
                'offset_end = COALESCE(('
                '    SELECT o.offset_end FROM opportunities AS o'
                '    WHERE o.run_id = event_roles.run_id'
                '      AND o.need_id = event_roles.need_id'
                '), 0), '
                'max_length = ('
                '    SELECT o.max_length FROM opportunities AS o'
                '    WHERE o.run_id = event_roles.run_id'
                '      AND o.need_id = event_roles.need_id'
                '), '
                'default_slots = COALESCE(('
                '    SELECT o.default_slots FROM opportunities AS o'
                '    WHERE o.run_id = event_roles.run_id'
                '      AND o.need_id = event_roles.need_id'
                '), event_roles.slots)'
            )
        ),
        # And the opportunity keeps what Amplify says about the
        # listing and nothing else.  These are gated the other way
        # round -- there is something to do while the column is still
        # there -- because the column that replaces each of them is on
        # another table, so there is no companion gate to borrow.
        #
        # Columns and not the table: nothing references
        # 'opportunities', but a rebuild is still the wrong habit in a
        # file where 'events' points at 'revisions' with a cascade.
        Step(
            table='opportunities',
            column='max_length',
            removes=True,
            statement=(
                'ALTER TABLE opportunities DROP COLUMN max_length'
            )
        ),
        Step(
            table='opportunities',
            column='offset_start',
            removes=True,
            statement=(
                'ALTER TABLE opportunities DROP COLUMN offset_start'
            )
        ),
        Step(
            table='opportunities',
            column='offset_end',
            removes=True,
            statement=(
                'ALTER TABLE opportunities DROP COLUMN offset_end'
            )
        ),
        Step(
            table='opportunities',
            column='default_slots',
            removes=True,
            statement=(
                'ALTER TABLE opportunities DROP COLUMN default_slots'
            )
        )
    ),
    9: (
        # The category the collection matched, which is what an undo
        # puts the event back under (D26).  An event stored only the
        # category it is under now, so changing it left nothing
        # saying what it had been: the change was invisible to
        # 'was_edited' and there was nothing for an undo to restore.
        #
        # No default, and none is needed: the column is nullable
        # because a collection matches nothing for some titles, and
        # that is what an event of any age says about itself until
        # the fill below.
        Step(
            table='events',
            column='collected_category',
            statement=(
                'ALTER TABLE events ADD COLUMN collected_category TEXT'
            )
        ),
        # Every event takes the category it is under, which is the
        # nearest true thing a database can say about rows written
        # before the column existed: an unedited event is under what
        # it was collected under, and an edited one has nothing left
        # that says what that was.  Gated on 'collected_category',
        # which is asked about before any statement of this version
        # runs and so is still absent when this is chosen.
        Step(
            table='events',
            column='collected_category',
            statement='UPDATE events SET collected_category = category'
        )
    ),
    10: (
        # What an edit did, as the operation it was and the values it
        # carried, rather than as an English sentence written into a
        # row (D27).  A sentence stored in a column cannot be reworded
        # without rewriting every row already holding the old one, and
        # this one was already wrong in the way a stored sentence
        # cannot be corrected: it carried a raw category key.
        #
        # The defaults are what SQLite requires of a NOT NULL column
        # added to a table that has rows.  Nothing fills them in
        # afterwards: recovering an operation and its values from
        # prose would be a migration written against English, for
        # entries that carry nothing a later reader can act on.  An
        # entry from before this version therefore says only when it
        # was made, by whom, and in which revision.
        Step(
            table='change_log',
            column='action',
            statement=(
                'ALTER TABLE change_log '
                "ADD COLUMN action TEXT NOT NULL DEFAULT ''"
            )
        ),
        Step(
            table='change_log',
            column='subject',
            statement='ALTER TABLE change_log ADD COLUMN subject TEXT'
        ),
        Step(
            table='change_log',
            column='subject_count',
            statement=(
                'ALTER TABLE change_log '
                'ADD COLUMN subject_count INTEGER NOT NULL DEFAULT 1'
            )
        ),
        Step(
            table='change_log',
            column='category',
            statement='ALTER TABLE change_log ADD COLUMN category TEXT'
        ),
        Step(
            table='change_log',
            column='shift_time',
            statement='ALTER TABLE change_log ADD COLUMN shift_time TEXT'
        ),
        Step(
            table='change_log',
            column='minutes',
            statement='ALTER TABLE change_log ADD COLUMN minutes INTEGER'
        ),
        Step(
            table='change_log',
            column='slots',
            statement='ALTER TABLE change_log ADD COLUMN slots INTEGER'
        ),
        Step(
            table='change_log',
            column='need_id',
            statement='ALTER TABLE change_log ADD COLUMN need_id TEXT'
        ),
        # And the sentence goes.  It has to: an insert now names
        # 'action' and not 'entry', so a NOT NULL column left behind
        # would refuse every entry written after this.  A column and
        # not the table -- 'change_log' points at 'runs' with a
        # cascade, so rebuilding it the portable way is the wrong
        # habit in this file.
        Step(
            table='change_log',
            column='entry',
            removes=True,
            statement='ALTER TABLE change_log DROP COLUMN entry'
        )
    )
}
