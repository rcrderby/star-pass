/* How a run says what it is, wherever one is listed.
 *
 * Two screens list runs: the runs list, which is home, and the run
 * picker on the review screen, which is how you move between them
 * without going home.  A run has to read the same way in both -- the
 * same label, the same status, the same word for the status -- so
 * these are here rather than in either, the way `.row-card` is in
 * `components.css` rather than in the two screens that draw one.
 *
 * The status is the core's key and the wording is the page's: the
 * contract publishes `unsent`, and `phrases.json` is what turns that
 * into something to read.
 */

import { el } from '../dom.js';
import { moment, windowText } from '../format.js';
import { phrase } from '../phrases.js';

/** Return what a run is called: its calendar and its window.
 *
 * @param {Object} run A run, as the contract lists it.
 * @returns {string} The label.
 */
export function runLabel(run) {
  return `${run.calendar} · ${windowText(run.window)}`;
}

/** Return the tag saying where a run is.
 *
 * A run that has sent is drawn as a filled tag and one that has not
 * as an outline, which is the same distinction the two screens made
 * separately before this.
 *
 * @param {Object} run A run, as the contract lists it.
 * @returns {HTMLElement} The tag.
 */
export function runStatusTag(run) {
  return el('span', {
    class: run.sentAt ? 'tag tag-neutral' : 'tag tag-outline',
    text: phrase('runStatus', run.status)
  });
}

/** Return when a run was collected, in its own window's zone.
 *
 * The zone is the calendar's, not the browser's: a run's dates mean
 * what the service read them as, which is the whole reason the window
 * carries one.
 *
 * @param {Object} run A run, as the contract lists it.
 * @returns {string} The time.
 */
export function collectedAt(run) {
  return moment(run.collectedAt, run.window.timezone);
}
