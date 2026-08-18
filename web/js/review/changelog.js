/* What has been done to this run, newest first.
 *
 * Server-owned, and that is the point of it: the log used to be built
 * in the page, so it died on reload and no other client could show
 * it.  It arrives with the run, which is why this panel is a reading
 * of an answer rather than a memory.
 */

import { el, icon } from '../dom.js';
import { moment } from '../format.js';

/* What the panel says when nothing has been done yet. A sentence
 * rather than an empty card, because an empty card reads as a panel
 * that failed to load. */
const NOTHING_YET = (
  'Nothing has been changed in this run yet. Every edit you make is '
  + 'listed here, with when it was made and which revision it belongs '
  + 'to.'
);

/** Return one entry.
 *
 * @param {Object} entry A change log entry.
 * @param {string} timeZone The run's zone.
 * @returns {HTMLElement} The entry.
 */
function logEntry(entry, timeZone) {
  return el(
    'li',
    { class: 'log-entry' },
    el('span', { class: 'log-entry-words meta', text: entry.entry }),
    el('span', {
      class: 'log-entry-meta muted micro mono',
      text: `${moment(entry.loggedAt, timeZone)} · revision ${entry.revision}`
    })
  );
}

/** Return the change log panel.
 *
 * @param {Object} state What the screen is showing.
 * @param {Function} onClose What closing it does.
 * @returns {HTMLElement} The panel.
 */
export function changeLogPanel(state, onClose) {
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
        entries.map((entry) => logEntry(entry, run.window.timezone))
      )
  );
}
