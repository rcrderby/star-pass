/* The run's events, a day at a time.
 *
 * A grid rather than a table element, because a row is two rows -- the
 * event and the shifts it creates -- and the second spans every
 * column.  The roles a table element would have carried are stated
 * outright, so what a screen reader is told matches what is drawn:
 * `table`, `rowgroup` per day, `row`, `columnheader`, `cell`.
 *
 * Every control sends **one** operation, through 'context.onEdit',
 * and the answer to it is the whole revision -- so a row redraws from
 * what the server said rather than from what this page hoped.  While
 * one is in flight the controls are disabled: two edits in the air at
 * once would each be applied to a revision the other had already
 * changed.
 */

import { chooser, el, icon } from '../dom.js';
import { counted, lengthText, dayHeading } from '../format.js';
import { filled, phrase } from '../phrases.js';
import { Popover } from '../popover.js';
import { timeField } from './timepicker.js';

/* How many columns the grid has. Stated for assistive technology,
 * which cannot count them from a grid the way it can from a table. */
const COLUMNS = 8;

/* The three columns whose headers show nothing. A header with no
 * words still has to say what its column is for. */
const HEADERS = [
  ['', 'Select'],
  ['Calendar event', ''],
  ['Opportunity', ''],
  ['Shift start', ''],
  ['Shift end', ''],
  ['Length', ''],
  ['', 'Remove'],
  ['', 'Undo changes']
];

/** Return the control showing what the calendar said about a row.
 *
 * Drawn on every row of a calendar that carries notes, including the
 * rows that have none: a control that appeared only where there was
 * something to read would make its absence look like a fault, and a
 * reader could not tell "nothing was written" from "this row is
 * different".  Which calendars carry notes is the service's answer
 * (D30), never a test of the calendar's name.
 *
 * The note is set as text, so what a calendar's description held
 * cannot become markup here.  It is already text by the time it is
 * published -- the conversion happens once, at collection -- and this
 * is the second of the two reasons it can be shown safely.
 *
 * @param {Object} event The event.
 * @returns {HTMLElement} The trigger, and the callout it opens.
 */
function calendarNote(event) {
  const trigger = el('button', {
    type: 'button',
    class: 'note-open',
    'aria-label': `${phrase('row', 'calendarNote')} for ${event.title}`
  }, icon('info'));

  return new Popover({
    trigger,
    width: 260,
    top: 26,
    contents: () => el(
      'span',
      { class: 'note-callout' },
      el('span', {
        class: 'note-callout-head micro muted',
        text: phrase('row', 'calendarNote')
      }),
      el('span', {
        class: event.calendarNote === null
          ? 'note-callout-body micro muted'
          : 'note-callout-body micro',
        text: event.calendarNote === null
          ? phrase('row', 'noCalendarNote')
          : event.calendarNote
      })
    )
  }).element;
}


/** Return the note saying how a title reached its category.
 *
 * @param {Object} event The event.
 * @param {Map} categories The calendar's categories, by key.
 * @returns {HTMLElement|null} The note, or nothing when the event
 *     matched nothing and the row says so another way.
 */
function matchNote(event, categories) {
  if (event.match === null) {
    return null;
  }

  const category = categories.get(event.category);

  return el('span', {
    class: 'row-note micro muted',
    text: filled('matchKind', event.match.kind, {
      keyword: event.match.keyword,
      category: category ? category.label : event.category,
      score: event.match.score
    })
  });
}

/** Return the note naming an earlier row this one repeats.
 *
 * @param {Object} event The event.
 * @param {Map} byId Every event in the revision, by identifier.
 * @returns {HTMLElement|null} The note, or nothing.
 */
function duplicateNote(event, byId) {
  if (event.duplicateOf === null) {
    return null;
  }

  const earlier = byId.get(event.duplicateOf);

  return el(
    'span',
    { class: 'row-note row-note-accent micro' },
    icon('copy'),
    el('span', {
      text: filled('row', 'duplicate', {
        title: earlier ? earlier.title : event.duplicateOf
      })
    })
  );
}

/** Return the note under a shift time, naming the offset that set it.
 *
 * The offset belongs to the opportunity rather than to the event, so
 * it stays put when somebody edits a time: it says what the
 * opportunity asks for, not what the time currently is.
 *
 * @param {string} which `offsetStart` or `offsetEnd`.
 * @param {number} minutes The opportunity's offset.
 * @returns {HTMLElement|null} The note, or nothing when it is zero.
 */
function offsetNote(which, minutes) {
  if (!minutes) {
    return null;
  }

  return el('span', {
    class: 'row-note row-note-accent micro',
    text: filled('row', which, {
      minutes: Math.abs(minutes),
      direction: minutes > 0 ? 'after' : 'before'
    })
  });
}

/* What the chooser's unassigned option carries. Not a category key,
 * so it cannot collide with one: every key the contract publishes
 * comes from the data model, and the empty string is what a select
 * gives for an option with no value of its own. */
const UNASSIGNED = '';

/** Return the opportunity chooser for one event.
 *
 * The options are the calendar's categories: a run holds only the
 * opportunities its own events reached, and the event that needs this
 * chooser is the one that matched nothing.
 *
 * **Unassigned is offered where the row may hold it**, which the
 * server says (`mayUnassign`): a row the collection matched nothing
 * for started there and can be put back, and a row it did match
 * cannot - the service refuses that, and an option whose only outcome
 * is a refusal is not a choice. A matched row that should create no
 * shift is removed from the run instead.
 *
 * The question is what the **collection** matched, not what the row
 * holds now, so a row somebody has since assigned an opportunity to
 * keeps its way back.
 *
 * @param {Object} event The event.
 * @param {Object} context What the rows are drawn against.
 * @returns {HTMLElement} The chooser.
 */
function opportunityChooser(event, context) {
  return chooser(el('select', {
    class: 'input',
    disabled: context.busy,
    'aria-label': `Opportunity for ${event.title}`,
    onchange: (changed) => context.onEdit(
      changed.target.value === UNASSIGNED
        ? { op: 'unassign', eventIds: [event.id] }
        : {
          op: 'set_category',
          eventIds: [event.id],
          category: changed.target.value
        }
    )
  }, [
    event.mayUnassign
      ? el('option', {
        value: UNASSIGNED,
        text: phrase('row', 'unassigned'),
        selected: event.category === null
      })
      : null,
    context.categories.map((category) => el('option', {
      value: category.key,
      text: category.label,
      selected: category.key === event.category
    }))
  ]));
}

/** Return one role sub-row: an opportunity this event creates under.
 *
 * @param {Object} event The event it belongs to.
 * @param {Object} role One of the event's roles.
 * @param {Object} context What the rows are drawn against.
 * @returns {HTMLElement} The sub-row.
 */
function roleRow(event, role, context) {
  const opportunity = context.opportunities.get(role.needId);

  return el(
    'div',
    { class: 'role-row', role: 'row' },
    el(
      'span',
      { class: 'role-chip-cell', role: 'cell' },
      icon('arrow-elbow-down-right'),
      el('span', {
        class: 'role-chip',
        text: opportunity ? opportunity.title : role.needId
      }),
      opportunity && opportunity.url
        ? el(
          'a',
          {
            class: 'role-link',
            href: opportunity.url,
            target: '_blank',
            rel: 'noreferrer noopener',
            'aria-label': `Open ${opportunity.title} in Amplify`
          },
          icon('arrow-square-out')
        )
        : null
    ),
    el('span', {
      class: 'role-time mono micro muted',
      role: 'cell',
      text: filled('row', 'shiftTime', {
        start: event.shiftStart,
        end: event.shiftEnd,
        minutes: event.lengthMinutes
      })
    }),
    el(
      'span',
      { class: 'role-slots', role: 'cell' },
      el('input', {
        class: 'input mono',
        type: 'text',
        inputMode: 'numeric',
        value: String(role.slots),
        disabled: context.busy,
        'aria-label': `Volunteers wanted for ${
          opportunity ? opportunity.title : role.needId
        }`,
        onchange: (changed) => {
          const wanted = Number(changed.target.value);

          /* Put back what it was rather than sending something the
           * service would refuse: slots is a count, and a count is a
           * whole number above nothing. */
          if (!Number.isInteger(wanted) || wanted < 1) {
            changed.target.value = String(role.slots);

            return;
          }

          if (wanted !== role.slots) {
            context.onEdit({
              op: 'set_slots',
              eventIds: [event.id],
              needId: role.needId,
              slots: wanted
            });
          }
        }
      }),
      el('span', { class: 'muted micro', text: 'slots' })
    ),
    el(
      'span',
      { class: 'role-edited', role: 'cell' },
      role.edited
        ? [
          el('span', { class: 'muted micro', text: 'edited,' }),
          el(
            'button',
            {
              type: 'button',
              class: 'btn btn-ghost micro',
              disabled: context.busy,
              title: 'Put this back to what the opportunity asks for',
              onclick: () => context.onEdit({
                op: 'reset_slots',
                eventIds: [event.id]
              })
            },
            'undo'
          )
        ]
        : null
    )
  );
}

/** Return the two rows one event is drawn as.
 *
 * @param {Object} event The event.
 * @param {Object} context What the rows are drawn against.
 * @returns {Array<HTMLElement>} The main row and its details row.
 */
function eventRows(event, context) {
  const { categoriesByKey, byId } = context;
  const capped = event.cappedAt !== null;
  const endsFirst = event.lengthMinutes <= 0;

  /* Built rather than chosen, because a row can be both: a repeat
   * that also has no opportunity to create a shift under carries the
   * two marks, and the stylesheet decides which edge is drawn by
   * putting the alert one last. */
  const marks = ['row-card', 'event-row'];

  if (event.duplicateOf !== null) {
    marks.push('event-row-repeat');
  }

  if (event.blocking) {
    marks.push('event-row-blocking');
  }

  const main = el(
    'div',
    {
      class: marks.join(' '),
      role: 'row'
    },
    el(
      'span',
      { class: 'cell-check', role: 'cell' },
      el('button', {
        type: 'button',
        class: context.selection.has(event.id)
          ? 'checkbox checkbox-on'
          : 'checkbox',
        role: 'checkbox',
        'aria-checked': String(context.selection.has(event.id)),
        'aria-label': `Select ${event.title}`,
        onclick: () => context.onToggleSelected(event.id)
      })
    ),
    el(
      'span',
      { class: 'cell-title', role: 'cell' },
      el('span', { class: 'row-title', text: event.title }),
      el(
        'span',
        { class: 'row-note row-note-line' },
        el('span', {
          class: 'mono micro muted',
          text: filled('row', 'calendarTimes', {
            start: event.calendarStart,
            end: event.calendarEnd
          })
        }),
        context.calendarNotes ? calendarNote(event) : null
      ),
      event.blocking
        ? el(
          'span',
          { class: 'row-note row-note-alert micro' },
          icon('warning-circle'),
          el('span', { text: phrase('row', 'noOpportunity') })
        )
        : null,
      matchNote(event, categoriesByKey),
      duplicateNote(event, byId)
    ),
    el(
      'span',
      { class: 'cell-opportunity', role: 'cell' },
      opportunityChooser(event, context)
    ),
    el(
      'span',
      { class: 'cell-time', role: 'cell' },
      timeField({
        value: event.shiftStart,
        label: `Shift start for ${event.title}`,
        busy: context.busy,
        onChoose: (time) => context.onEdit({
          op: 'set_start',
          eventIds: [event.id],
          time
        })
      }),
      offsetNote('offsetStart', context.offsetOf(event).start)
    ),
    el(
      'span',
      { class: 'cell-time', role: 'cell' },
      timeField({
        value: event.shiftEnd,
        label: `Shift end for ${event.title}`,
        busy: context.busy,
        onChoose: (time) => context.onEdit({
          op: 'set_end',
          eventIds: [event.id],
          time
        })
      }),
      offsetNote('offsetEnd', context.offsetOf(event).end)
    ),
    el(
      'span',
      { class: 'cell-length', role: 'cell' },
      el('span', {
        class: endsFirst ? 'mono row-length-alert' : 'mono',
        text: endsFirst ? 'ends first' : lengthText(event.lengthMinutes)
      }),
      endsFirst
        ? el('span', {
          class: 'row-note row-note-alert micro',
          text: phrase('row', 'endsFirst')
        })
        : null,
      capped
        ? el('span', {
          class: 'row-note micro muted',
          text: filled('row', 'capped', { minutes: event.cappedAt })
        })
        : null
    ),
    el(
      'span',
      { class: 'cell-remove', role: 'cell' },
      el(
        'button',
        {
          type: 'button',
          class: 'btn btn-ghost btn-icon row-remove',
          disabled: context.busy,
          'aria-label': `Remove ${event.title} from this run`,
          title: 'Remove from this run',
          onclick: () => context.onEdit({
            op: 'remove',
            eventIds: [event.id]
          })
        },
        icon('trash')
      )
    ),
    el(
      'span',
      { class: 'cell-undo', role: 'cell' },
      /* Only where there is something to undo, which the server says:
       * it runs the same arithmetic the operation would and answers
       * whether it would change the row. The cell is drawn either way,
       * because the row is a grid and a missing cell would shift every
       * column after it. */
      event.edited
        ? el(
          'button',
          {
            type: 'button',
            class: 'btn btn-ghost micro',
            disabled: context.busy,
            title: 'Put this row back as it was collected - its '
              + 'opportunity, its shift times and the volunteers '
              + 'each opportunity asks for',
            onclick: () => context.onEdit({
              op: 'undo',
              eventIds: [event.id]
            })
          },
          icon('arrow-counter-clockwise'),
          'Undo'
        )
        : null
    )
  );

  const details = el(
    'div',
    { class: 'event-details', role: 'row' },
    el(
      'span',
      { class: 'event-details-cell', role: 'cell' },
      event.roles.map((role) => roleRow(event, role, context))
    )
  );

  return [main, details];
}

/** Return one day's group of events.
 *
 * @param {string} day The day, as an ISO date.
 * @param {Array<Object>} events What falls on it.
 * @param {Object} context What the rows are drawn against.
 * @returns {HTMLElement} The group.
 */
function dayGroup(day, events, context) {
  const shifts = events.reduce(
    (total, event) => total + event.roles.length,
    0
  );
  const collapsed = context.collapsed.has(day);

  /* Said only while the group is folded shut. Open, the ticks are on
   * screen and counting them again would be noise; shut, a selection
   * reaches in and nothing else on the page says so -- the toolbar's
   * own "N not shown" counts what a filter or a search is hiding, and
   * a folded group is neither. Select-all reaches in here too, so
   * this can be arrived at without ticking anything a person saw. */
  const chosen = collapsed
    ? events.filter((event) => context.selection.has(event.id)).length
    : 0;

  const body = el(
    'div',
    { class: 'day-body' },
    el(
      'div',
      { class: 'day-body-inner' },
      events.map((event) => eventRows(event, context))
    )
  );

  const heading = el(
    'button',
    {
      type: 'button',
      class: 'day-heading',
      'aria-expanded': String(!collapsed),
      onclick: () => context.onToggleDay(day)
    },
    icon(collapsed ? 'caret-right' : 'caret-down'),
    el('span', { class: 'day-heading-name', text: dayHeading(day) }),
    el('span', {
      class: 'day-heading-count muted micro',
      text: `${counted(events.length, 'event')},`
        + ` ${counted(shifts, 'shift')}`
        + (chosen > 0 ? `, ${chosen} selected` : '')
    })
  );

  const group = el(
    'div',
    { class: 'day-group', role: 'rowgroup' },
    el('div', { class: 'day-heading-row', role: 'row' },
      el('span', { class: 'day-heading-cell', role: 'cell' }, heading)),
    body
  );

  /* The collapse animates 'grid-template-rows' from one fraction to
   * none, which is what lets a group of unknown height slide rather
   * than jump. Set through the CSSOM, which the Content Security
   * Policy permits where a style attribute is refused. */
  body.style.setProperty('grid-template-rows', collapsed ? '0fr' : '1fr');

  return group;
}

/** Return the table's own header row.
 *
 * @returns {HTMLElement} The row.
 */
function headerRow() {
  return el(
    'div',
    { class: 'table-head', role: 'row' },
    HEADERS.map(([words, label]) => el('span', {
      class: 'table-head-cell',
      role: 'columnheader',
      'aria-label': words === '' ? label : null,
      text: words
    }))
  );
}

/** Return the run's events, grouped by day.
 *
 * @param {Array<Object>} events The events to show, already filtered.
 * @param {Object} context What the rows are drawn against.
 * @returns {HTMLElement} The table.
 */
export function reviewTable(events, context) {
  const days = new Map();

  for (const event of events) {
    if (!days.has(event.date)) {
      days.set(event.date, []);
    }

    days.get(event.date).push(event);
  }

  return el(
    'div',
    {
      class: 'review-table',
      role: 'table',
      'aria-colcount': String(COLUMNS),
      'aria-label': 'Shifts this run would create'
    },
    headerRow(),
    [...days.entries()].map(
      ([day, onThatDay]) => dayGroup(day, onThatDay, context)
    )
  );
}
