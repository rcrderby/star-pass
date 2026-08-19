/* Not collected: everything the run's window held that did not become
 * a shift, and why.
 *
 * Read from `GET /runs/{id}/uncollected`, which answers from what the
 * collection stored rather than from a calendar read -- so this
 * describes the window as the collection found it, and recollecting
 * is what refreshes it.
 *
 * **Whether a row may be pulled in is `addable`, and nothing here
 * works it out.**  The reason a group is drawn under and the reason a
 * row may be added happen to line up today, and reading the first to
 * decide the second would be a second opinion about what the endpoint
 * will accept -- one that would go on disagreeing quietly once the
 * two stopped lining up.  A row already pulled in keeps its entry and
 * stops being addable, because reverting to the first revision drops
 * the hand-added events and this list is where they come back to.
 *
 * The titles noted for the model belong to **no run**: a run is a
 * window that is eventually superseded, and what the data model is
 * missing outlives it.  So the last section is read beside the run
 * rather than out of it, and there is nothing on it to remove -- a
 * title leaves that log when the data model matches it (D20), which
 * is the edit somebody notes one in order to make.
 */

import { el, icon } from '../dom.js';
import { moment, shortDay } from '../format.js';
import { phrase } from '../phrases.js';

/* What the tab says above the groups. */
const LEDE = (
  'Everything in this window that will not become a shift, and why. '
  + 'Only events the calendar search never looked for can be added to '
  + 'the run by hand.'
);

/* Said when the collection took everything its window held. */
const NOTHING_LEFT_OUT = (
  'Nothing in this window was left out. Every event the search '
  + 'returned became a row on the other tab.'
);

/* The heading over the titles kept for the next edit of the data
 * model, and what that list is. */
const NOTED_HEADING = 'Noted for the model';
const NOTED_NOTE = (
  'Titles no category matched, kept for the next edit of the shift '
  + 'data model. The collections record what they find themselves, and '
  + 'one can be noted by hand as well. This list belongs to no run, '
  + 'and a title leaves it when the data model matches it, so there is '
  + 'nothing here to remove.'
);
const NOTHING_NOTED = (
  'No title has been noted yet, and no collection has found one.'
);

/* What a row's two controls say. */
const ADD = 'Add to run';
const NOTE = 'Note for the model';
const NOTED = 'Noted for the model';

/* Stood in for a value the calendar did not give. An untitled event
 * has no title and one whose date could not be read has no date,
 * which are the events three of the four reasons describe. */
const NO_TITLE = '(no title)';
const NO_DATE = 'No date';

/* Said of an event with a day and no times, which is what all day
 * means on a calendar. */
const ALL_DAY = 'All day';

/* The one reason a row may be pulled in under, which is what the
 * line naming the calendar's query strings explains. Read to pick
 * an explanation and never to decide whether a row is addable --
 * `addable` answers that, and is the server's. */
const SEARCH_REASON = 'search';

/** Return what one title and calendar are keyed by.
 *
 * The pair rather than the title: the categories a title is matched
 * against belong to a calendar, so the same title can be matched in
 * one and unmatched in another, and the log keys an entry by both.
 *
 * Exported because the screen holding the Set builds it and the row
 * reading the Set asks it, and two spellings of one key would be a
 * row that never says it has been noted.
 *
 * @param {string} calendar Which calendar it was seen in.
 * @param {string} title The title.
 * @returns {string} A key for a Set.
 */
export function notedKey(calendar, title) {
  return JSON.stringify([calendar, title]);
}

/** Return when an uncollected event was, as its row says it.
 *
 * @param {Object} event One row of a group.
 * @returns {string} The day and the calendar times, where there are
 *     any.
 */
function whenText(event) {
  const day = event.date === null ? NO_DATE : shortDay(event.date, true);

  if (event.calendarStart === null || event.calendarEnd === null) {
    return `${day} · ${ALL_DAY}`;
  }

  return `${day} · ${event.calendarStart} to ${event.calendarEnd}`;
}

/** Return the line naming what a calendar is searched for.
 *
 * Only under the group it explains, and only when the deployment
 * configured something to name. A calendar searched for an empty
 * query string is searched for everything, which is a calendar
 * nothing can be a search miss on -- so this line is under a group
 * that could not have been drawn, and is left out.
 *
 * @param {Object} state What the screen is showing.
 * @returns {HTMLElement|null} The line, or nothing to say.
 */
function searchTermsLine(state) {
  const calendar = state.config.calendars.find(
    (each) => each.key === state.run.calendar
  );
  const terms = calendar === undefined
    ? []
    : calendar.searchTerms.filter((term) => term !== '');

  if (terms.length === 0) {
    return null;
  }

  return el(
    'p',
    { class: 'uncollected-terms muted note' },
    icon('magnifying-glass'),
    el('span', {
      text: `The ${state.run.calendar} calendar is searched for `
        + `${terms.map((term) => `"${term}"`).join(', ')}.`
    })
  );
}

/** Return one row of one group.
 *
 * @param {Object} event The event, as the contract lists it.
 * @param {Object} state What the screen is showing.
 * @param {Object} handlers What its controls do.
 * @returns {HTMLElement} The row.
 */
function uncollectedRow(event, state, handlers) {
  /* An untitled event cannot be noted: what the log holds is a title,
   * and the request refuses an empty one. So the control is absent
   * rather than offered and refused. */
  const noted = event.title === null
    ? false
    : state.notedKeys.has(notedKey(state.run.calendar, event.title));

  return el(
    'div',
    { class: 'row-card uncollected-row' },
    el('span', {
      class: event.title === null
        ? 'uncollected-title muted'
        : 'uncollected-title',
      text: event.title === null ? NO_TITLE : event.title
    }),
    el('span', {
      class: 'uncollected-when mono muted note',
      text: whenText(event)
    }),
    el(
      'span',
      { class: 'uncollected-actions' },
      event.title === null
        ? null
        : el(
          'button',
          {
            type: 'button',
            class: 'btn btn-ghost',
            disabled: state.busy || noted,
            onclick: () => handlers.onNote(event.title)
          },
          icon(noted ? 'check' : 'note-pencil'),
          noted ? NOTED : NOTE
        ),
      event.addable
        ? el(
          'button',
          {
            type: 'button',
            class: 'btn btn-secondary',
            disabled: state.busy,
            onclick: () => handlers.onAdd(event.id)
          },
          icon('plus'),
          ADD
        )
        : null
    )
  );
}

/** Return one reason's section.
 *
 * @param {Object} group A group, as the contract lists it.
 * @param {Object} state What the screen is showing.
 * @param {Object} handlers What its controls do.
 * @returns {HTMLElement} The section.
 */
function uncollectedGroup(group, state, handlers) {
  return el(
    'section',
    { class: 'uncollected-group' },
    el(
      'div',
      { class: 'uncollected-head' },
      el('h4', { text: phrase('uncollected', group.reason) }),
      el('span', {
        class: 'mono muted meta',
        text: String(group.events.length)
      })
    ),
    el('p', {
      class: 'uncollected-note muted note',
      text: phrase('uncollectedNote', group.reason)
    }),
    group.reason === SEARCH_REASON ? searchTermsLine(state) : null,
    el(
      'div',
      { class: 'uncollected-rows' },
      group.events.map(
        (event) => uncollectedRow(event, state, handlers)
      )
    )
  );
}

/** Return one entry of the log kept for the data model.
 *
 * The calendar is the entry's source, and the count is what the log
 * is for: a title turning up every month is a category the model is
 * missing, and one seen once is an event that happened once.
 *
 * @param {Object} entry An entry, as the contract lists it.
 * @param {string} timeZone The zone the service reads its dates in.
 * @returns {HTMLElement} The row.
 */
function notedRow(entry, timeZone) {
  const seen = entry.timesSeen;

  return el(
    'div',
    { class: 'row-card noted-row' },
    el('span', { class: 'uncollected-title', text: entry.title }),
    el('span', {
      class: 'uncollected-when muted note',
      text: `Seen in the ${entry.calendar} calendar`
    }),
    el('span', {
      class: 'uncollected-seen mono muted note',
      text: `${seen} sighting${seen === 1 ? '' : 's'},`
        + ` most recent ${moment(entry.lastSeen, timeZone)}`
    })
  );
}

/** Return the section listing what has been noted.
 *
 * @param {Object} state What the screen is showing.
 * @returns {HTMLElement} The section.
 */
function notedSection(state) {
  return el(
    'section',
    { class: 'uncollected-group uncollected-noted' },
    el(
      'div',
      { class: 'uncollected-head' },
      el('h4', { text: NOTED_HEADING }),
      el('span', {
        class: 'mono muted meta',
        text: String(state.noted.length)
      })
    ),
    el('p', { class: 'uncollected-note muted note', text: NOTED_NOTE }),
    state.noted.length === 0
      ? el('p', { class: 'muted meta', text: NOTHING_NOTED })
      : el(
        'div',
        { class: 'uncollected-rows' },
        state.noted.map(
          (entry) => notedRow(entry, state.config.timezone)
        )
      )
  );
}

/** Return the Not collected tab.
 *
 * @param {Object} state What the screen is showing.
 * @param {Object} handlers What its controls do.
 * @param {Function} handlers.onAdd Pull one event into the run.
 * @param {Function} handlers.onNote Record one title for the model.
 * @returns {Array<Node>} What the body holds.
 */
export function uncollectedView(state, handlers) {
  return [
    el('p', { class: 'uncollected-lede muted meta', text: LEDE }),
    state.uncollected.length === 0
      ? el('p', { class: 'muted meta', text: NOTHING_LEFT_OUT })
      : el(
        'div',
        { class: 'uncollected-groups' },
        state.uncollected.map(
          (group) => uncollectedGroup(group, state, handlers)
        )
      ),
    notedSection(state)
  ];
}
