/* What a send restates before it happens (D11).
 *
 * The first thing that cannot be undone, put through the dialog both
 * of them share: the count, the run and its window, and what each
 * opportunity is about to receive, on the card above the button.
 *
 * Every figure here is the preview's, not a second reading of it.
 * The number in the title is the number in the button, the number the
 * request carries as `expectedShiftCount`, and the number the service
 * checks against a fresh read before it starts -- so a confirmation
 * agreeing with a screen that no longer agrees with Amplify is
 * refused rather than acted on.
 */

import { ConfirmDialog } from '../confirm.js';
import { counted, windowText } from '../format.js';
import { el } from '../dom.js';

/* Said last, above the buttons, in the alert colour. */
const NO_UNDO = (
  'Amplify has no undo. Removing any of these afterwards has to be '
  + 'done in Amplify by hand.'
);

/* Why the number can be trusted even though the screen behind this
 * was drawn a moment ago. */
const CHECKED_AGAIN = (
  'Amplify is checked once more as this starts, so nothing can be '
  + 'created twice.'
);

/** Return the sentence restating what is about to happen.
 *
 * @param {Object} preview What the service answered.
 * @returns {string} The line.
 */
export function restatement(preview) {
  const { totals } = preview;
  const receiving = preview.rows.filter((row) => row.willCreate > 0);
  const parts = [
    `${counted(totals.willCreate, 'shift')} across `
    + `${counted(receiving.length, 'opportunity', 'opportunities')}.`
  ];

  if (totals.alreadyInAmplify) {
    const shifts = counted(totals.alreadyInAmplify, 'shift');
    const verb = totals.alreadyInAmplify === 1 ? 'is' : 'are';

    parts.push(`${shifts} already in Amplify ${verb} left out.`);
  }

  parts.push(CHECKED_AGAIN);

  return parts.join(' ');
}

/** Return the confirmation in front of a send.
 *
 * @param {Object} what What is being confirmed.
 * @param {Object} what.run The run, which names the window.
 * @param {Object} what.preview What a send would create.
 * @param {Object} handlers What its two buttons do.
 * @param {Function} handlers.onConfirm Go ahead.
 * @param {Function} handlers.onCancel Close and change nothing.
 * @returns {ConfirmDialog} The dialog, ready to open.
 */
export function sendDialog({ run, preview }, handlers) {
  const willCreate = preview.totals.willCreate;

  return new ConfirmDialog(
    {
      title: `Create ${counted(willCreate, 'shift')} in Amplify?`,
      about: `${run.calendar} · ${windowText(run.window)}`,
      body: [
        el('p', { class: 'confirm-line', text: restatement(preview) }),
        el(
          'div',
          { class: 'confirm-rows' },
          preview.rows
            .filter((row) => row.willCreate > 0)
            .map((row) => el(
              'span',
              { class: 'confirm-row' },
              el('span', {
                class: 'confirm-row-name',
                text: row.title === null ? row.needId : row.title
              }),
              el('span', { class: 'mono', text: String(row.willCreate) })
            ))
        )
      ],
      warning: NO_UNDO,
      confirmLabel: `Create ${counted(willCreate, 'shift')}`,
      confirmIcon: 'paper-plane-tilt'
    },
    handlers
  );
}
