#!/usr/bin/env python3
""" What carries a database that already exists forward.

    Separate from the schema statements beside it: a
    'CREATE TABLE IF NOT EXISTS' does nothing to a table that already
    exists, so a column added to one arrives here or not at all.

    A version's steps are fixed once a release has run them.  A
    database carried past a step never runs it again, so a correction
    is a further step.
"""

# Imports - Python Standard Library
from dataclasses import dataclass


@dataclass(frozen=True)
class Step:
    """ One statement that carries a database forward.

        A step adds a column, declared exactly as the create above
        declares it, fills one that arrived empty, or removes one.

        Attributes:
            table (str):
                Table the step is about.

            column (str):
                The column that says whether the step still has
                something to do.  Every step of a version is asked
                this before any of them runs, which lets a fill be
                gated on the column it fills.

            removes (bool):
                Which way the question reads.  A step that adds or
                fills has something to do while its column is
                **absent**; a step that removes one has something to
                do while it is still **there**.

            statement (str):
                What to run.
    """

    table: str
    column: str
    statement: str
    removes: bool = False


# What carries a database that already exists forward, by the version
# each step raises it to.  A step runs on a database below its version
# whose table still lacks the column, so a database that predates the
# table itself is given the current table by the statements above and
# leaves the step nothing to add.
#
# A version's steps are fixed once a release has run them.
MIGRATIONS = {
    4: (
        # Which process is holding a job, so a sweep of what a stopped
        # process left behind leaves alone what it never held.  The
        # service and the command line share a database, and a sweep
        # that took everything unfinished would mark a live send
        # interrupted.  The default is a literal because a schema
        # statement takes one; it is the value of
        # '_records.JOB_HOLDER_SERVICE'.
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
        # from, so that each client words them itself.  The empty
        # default is what SQLite requires of a NOT NULL column added
        # to a table that has rows; the four statements below correct
        # it in the same transaction.
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
        # Each sentence the column holds, read back into what it says.
        # Gated on 'kind', which every step of a version is asked
        # about before any of them runs and so is still absent here.
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
        # And the sentence goes: an insert names 'kind' and 'source'
        # and not 'label', so a NOT NULL 'label' would refuse every
        # revision.  A column and not the table -- 'events' points at
        # 'revisions' with a cascade, so rebuilding the table the
        # portable way would delete every event in the database.
        Step(
            table='revisions',
            column='kind',
            statement='ALTER TABLE revisions DROP COLUMN label'
        )
    ),
    8: (
        # What a shift asks of its event, on the event's role rather
        # than the run's opportunity.  One Amplify listing can be
        # named by categories that time it differently -- need 905196
        # by three -- and a table keyed '(run_id, need_id)' holds only
        # one of them.  The defaults are what SQLite requires of a NOT
        # NULL column added to a table that has rows; the fill below
        # replaces them.
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
        # which is what that role was collected with.  'default_slots'
        # falls back to what the role holds, the nearest true thing
        # for a role whose opportunity is missing.
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
        # round -- something to do while the column is still there --
        # because each replacing column is on another table and offers
        # no companion gate to borrow.
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
        # puts the event back under and what 'was_edited' compares
        # against.  Nullable, because a collection matches nothing for
        # some titles.
        Step(
            table='events',
            column='collected_category',
            statement=(
                'ALTER TABLE events ADD COLUMN collected_category TEXT'
            )
        ),
        # Every event takes the category it is under, the nearest true
        # thing about a row that predates the column: an unedited
        # event is under what it was collected under, and an edited
        # one holds nothing else that says what that was.
        Step(
            table='events',
            column='collected_category',
            statement='UPDATE events SET collected_category = category'
        )
    ),
    10: (
        # What an edit did, as the operation it was and the values it
        # carried, so that each client words it itself.  The defaults
        # are what SQLite requires of a NOT NULL column added to a
        # table that has rows, and nothing fills them: recovering an
        # operation from prose would be a migration written against
        # English.  An entry that predates this version says only when
        # it was made, by whom, and in which revision.
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
        # And the sentence goes: an insert names 'action' and not
        # 'entry', so a NOT NULL 'entry' would refuse every entry.  A
        # column and not the table -- 'change_log' points at 'runs'
        # with a cascade.
        Step(
            table='change_log',
            column='entry',
            removes=True,
            statement='ALTER TABLE change_log DROP COLUMN entry'
        )
    ),
    11: (
        # What the calendar's description says, on the event and on
        # the row an event may be added from.  Nullable and filled
        # with nothing: a note comes only from reading the calendar,
        # so a row that predates the column reads as having no note
        # until its run is collected again.
        Step(
            table='events',
            column='calendar_note',
            statement=(
                'ALTER TABLE events ADD COLUMN calendar_note TEXT'
            )
        ),
        Step(
            table='uncollected_events',
            column='calendar_note',
            statement=(
                'ALTER TABLE uncollected_events '
                'ADD COLUMN calendar_note TEXT'
            )
        )
    )
}
