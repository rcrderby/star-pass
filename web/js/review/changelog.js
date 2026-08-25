/* What has been done to this run, newest first.
 *
 * Server-owned, and that is the point of it: the log arrives with the
 * run, so it survives a reload and every client shows the same one.
 * This panel is a reading of an answer rather than a memory.
 *
 * **The answer carries what was done, not a sentence.** An entry
 * names its action and the values that action carried, and the words
 * below are this client's. So the wording can change without every
 * entry already recorded still saying the old thing, and a category
 * is shown by the name this screen calls it rather than by the key
 * the data model files it under.
 */

import { el, icon } from '../dom.js';
import { moment } from '../format.js';
import { filled, phrase } from '../phrases.js';

/* What the panel says when nothing has been done yet. A sentence
 * rather than an empty card, because an empty card reads as a panel
 * that failed to load. */
const NOTHING_YET = (
  'Nothing has been changed in this run yet. Every edit you make is '
  + 'listed here, with when it was made and which revision it belongs '
  + 'to.'
);

/** Return how many changes were made in the revision being edited.
 *
 * Counted from the log rather than read off the revision, which is
 * the same number -- a revision's count is what was logged while it
 * was current -- and stays right after an edit without asking the
 * service for the revisions again. Only the current one is worked
 * out this way: every revision below it is history and is never
 * written to, so the count the service published for one of those is
 * already final.
 *
 * Here rather than beside either caller, because the toolbar's tag
 * and the revision picker's line are the same number said twice.
 *
 * @param {Object} run The run, which carries its whole log.
 * @returns {number} Entries made in the current revision.
 */
export function changesNow(run) {
  return run.log.filter(
    (entry) => entry.revision === run.currentRevision
  ).length;
}

/** Return what an entry was done to.
 *
 * One event is named and a selection is counted: a line listing
 * thirty titles is one nobody reads. An entry carries a title exactly
 * when it named one event, so the title being there is the question
 * to ask.
 *
 * @param {Object} entry A change log entry.
 * @returns {string} The title in quotes, or a count.
 */
function subjectOf(entry) {
  if (entry.subject !== null) {
    return filled('logSubject', 'one', { title: entry.subject });
  }

  return filled('logSubject', 'many', { count: entry.subjectCount });
}

/** Return what an entry says.
 *
 * The values it carried are shown the way the rest of the screen
 * shows them: a category by its label and an opportunity by its
 * Amplify title, both looked up where the table looks them up, and
 * falling back to the identifier the entry carries when the run holds
 * no name for it.
 *
 * @param {Object} entry A change log entry.
 * @param {Object} context What the rows are drawn against.
 * @returns {string} The sentence.
 */
function wordsOf(entry, context) {
  const category = context.categoriesByKey.get(entry.category);
  const opportunity = context.opportunities.get(entry.needId);

  return filled('logAction', entry.action, {
    subject: subjectOf(entry),
    category: category ? category.label : entry.category,
    opportunity: opportunity
      ? opportunity.title
      : filled('logValue', 'unknownOpportunity', { needId: entry.needId }),
    time: entry.shiftTime,
    slots: entry.slots,
    minutes: Math.abs(entry.minutes),
    direction: phrase('logDirection', entry.minutes > 0 ? 'later' : 'earlier')
  });
}

/** Return one entry.
 *
 * @param {Object} entry A change log entry.
 * @param {Object} context What the rows are drawn against.
 * @param {string} timeZone The run's zone.
 * @returns {HTMLElement} The entry.
 */
function logEntry(entry, context, timeZone) {
  return el(
    'li',
    { class: 'log-entry' },
    el('span', {
      class: 'log-entry-words meta',
      text: wordsOf(entry, context)
    }),
    el('span', {
      class: 'log-entry-meta muted micro mono',
      text: `${moment(entry.loggedAt, timeZone)} · revision ${entry.revision}`
    })
  );
}

/** Return the change log panel.
 *
 * @param {Object} state What the screen is showing.
 * @param {Object} context What the rows are drawn against, read for
 *     the names an entry's values are shown under.
 * @param {Function} onClose What closing it does.
 * @returns {HTMLElement} The panel.
 */
export function changeLogPanel(state, context, onClose) {
  const { run } = state;
  const entries = [...run.log].reverse();

  return el(
    'aside',
    { class: 'log-panel card elev-md', 'aria-label': 'Change log' },
    el(
      'div',
      { class: 'log-panel-head' },
      el('h2', { class: 'log-panel-title', text: 'Change log' }),
      el(
        'button',
        {
          type: 'button',
          class: 'btn btn-ghost btn-icon',
          'aria-label': 'Close the change log',
          onclick: onClose
        },
        icon('x')
      )
    ),
    entries.length === 0
      ? el('p', { class: 'muted meta', text: NOTHING_YET })
      : el(
        'ol',
        { class: 'log-entries' },
        entries.map(
          (entry) => logEntry(entry, context, run.window.timezone)
        )
      )
  );
}
