/* What a refused call says, above the content it was about.
 *
 * A notice rather than the screen-wide failure, which would throw
 * away a run that is still perfectly readable.  The service applies
 * an action whole or not at all, so nothing was half done and what is
 * below this is what it was.
 *
 * **The reason is the service's own sentence.**  A screen that
 * invented one would be a second opinion about what went wrong, and
 * the preview was that screen until #297: it said "Amplify did not
 * answer" for every failure, including the ones where Amplify was
 * never reached.
 *
 * Beside `modal.js` rather than under any one screen: three screens
 * can have a call refused now -- both views over a run, and the runs
 * list -- and two copies of the sentence that says so would
 * eventually differ about what a reference is called.
 */

import { el, icon } from './dom.js';

/* The one banner allowed the alert colour, which is what makes it
 * read as the thing that did not happen. */
const ALERT = 'banner banner-alert';

/** Return what a refused call says.
 *
 * @param {Object} options What was refused.
 * @param {string} options.said What did not happen, as a sentence.
 * @param {ApiError} options.failure Why not.
 * @returns {HTMLElement} The notice.
 */
export function refusalNotice({ said, failure }) {
  return el(
    'div',
    { class: ALERT, role: 'alert' },
    icon('warning-circle'),
    el(
      'span',
      { class: 'banner-words meta' },
      el('span', { text: `${said} ${failure.detail}` }),
      failure.reference
        ? el(
          'span',
          { class: 'muted micro failure-reference' },
          'Reference ',
          el('span', { class: 'mono', text: failure.reference })
        )
        : null
    )
  );
}
