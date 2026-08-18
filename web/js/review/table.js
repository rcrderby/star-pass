/* The run's events, a day at a time.
 *
 * A grid rather than a table element, because a row is two rows -- the
 * event and the shifts it creates -- and the second spans every
 * column.  The roles a table element would have carried are stated
 * outright, so what a screen reader is told matches what is drawn:
 * `table`, `rowgroup` per day, `row`, `columnheader`, `cell`.
 *
 * Nothing here writes.  The controls a reviewer will use are drawn in
 * their places and are not yet live, so the layout that editing lands
 * into is the layout being reviewed now, and a reader can see what
 * the run holds today.
 */

import { el, icon } from '../dom.js';
import { lengthText, dayHeading } from '../format.js';
import { filled, phrase } from '../phrases.js';

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

/** Return the opportunity chooser for one event.
 *
 * Drawn with its options and its current value, and not yet live.
 * The options are the calendar's categories: a run holds only the
 * opportunities its own events reached, and the event that needs this
 * chooser is the one that matched nothing.
 *
 * @param {Object} event The event.
 * @param {Array<Object>} categories The calendar's categories.
 * @returns {HTMLElement} The chooser.
 */
function opportunityChooser(event, categories) {
  const chooser = el('select', {
    class: 'input',
    disabled: true,
    'aria-label': `Opportunity for ${event.title}`
  }, [
    el('option', {
      value: '',
      text: 'Select an opportunity',
      selected: event.category === null
    }),
    categories.map((category) => el('option', {
      value: category.key,
      text: category.label,
      selected: category.key === event.category
    }))
  ]);

  return chooser;
}

/** Return one role sub-row: an opportunity this event creates under.
 *
 * @param {Object} event The event it belongs to.
 * @param {Object} role One of the event's roles.
 * @param {Map} opportunities The run's opportunities, by need ID.
 * @returns {HTMLElement} The sub-row.
 */
function roleRow(event, role, opportunities) {
  const opportunity = opportunities.get(role.needId);

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
        value: String(role.slots),
        readOnly: true,
        'aria-label': `Volunteers wanted for ${
          opportunity ? opportunity.title : role.needId
        }`
      }),
      el('span', { class: 'muted micro', text: 'slots' })
    ),
    el(
      'span',
      { class: 'role-edited', role: 'cell' },
      role.edited
        ? el('span', { class: 'muted micro', text: 'edited' })
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
  const { categories, categoriesByKey, opportunities, byId } = context;
  const capped = event.cappedAt !== null;
  const endsFirst = event.lengthMinutes <= 0;

  const main = el(
    'div',
    {
      class: event.blocking ? 'event-row event-row-blocking' : 'event-row',
      role: 'row'
    },
    el(
      'span',
      { class: 'cell-check', role: 'cell' },
      el('span', {
        class: 'checkbox',
        role: 'checkbox',
        'aria-checked': 'false',
        'aria-disabled': 'true',
        'aria-label': `Select ${event.title}`
      })
    ),
    el(
      'span',
      { class: 'cell-title', role: 'cell' },
      el('span', { class: 'row-title', text: event.title }),
      el('span', {
        class: 'row-note mono micro muted',
        text: filled('row', 'calendarTimes', {
          start: event.calendarStart,
          end: event.calendarEnd
        })
      }),
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
      opportunityChooser(event, categories)
    ),
    el(
      'span',
      { class: 'cell-time', role: 'cell' },
      el('input', {
        class: 'input mono',
        type: 'text',
        value: event.shiftStart,
        readOnly: true,
        'aria-label': `Shift start for ${event.title}`
      }),
      offsetNote('offsetStart', context.offsetOf(event).start)
    ),
    el(
      'span',
      { class: 'cell-time', role: 'cell' },
      el('input', {
        class: 'input mono',
        type: 'text',
        value: event.shiftEnd,
        readOnly: true,
        'aria-label': `Shift end for ${event.title}`
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
    el('span', { class: 'cell-remove', role: 'cell' }),
    el('span', { class: 'cell-undo', role: 'cell' })
  );

  const details = el(
    'div',
    { class: 'event-details', role: 'row' },
    el(
      'span',
      { class: 'event-details-cell', role: 'cell' },
      event.roles.map((role) => roleRow(event, role, opportunities))
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
      text: `${events.length} event${events.length === 1 ? '' : 's'},`
        + ` ${shifts} shift${shifts === 1 ? '' : 's'}`
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
