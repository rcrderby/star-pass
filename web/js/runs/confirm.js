/* What a deletion restates before it happens.
 *
 * The second thing that cannot be undone, and it is put the same way
 * as the first, through the same dialog: what is about to go is on
 * the card above the button, so somebody reads it rather than
 * answering a bare "are you sure".  The counts are the point -- a run
 * holding nothing and a run holding a reviewed month read the same
 * way in an identifier alone.
 *
 * **What this destroys is not what Amplify holds.**  A run that sent
 * anything is refused a deletion outright and is offered no control
 * at all, so nothing reachable from here can take a shift out of a
 * volunteer's calendar.  What it destroys is the record on this side,
 * and that is gone.  The wording says so in both directions: what
 * goes with the run, and what stays behind because it outlives it.
 */

import { ConfirmDialog } from '../confirm.js';
import { counted, windowText } from '../format.js';
import { el } from '../dom.js';
import { runStatusTag } from './summary.js';

/* The question, which is the command line's, word for word: one
 * deletion asked about two ways would be two decisions to keep
 * agreeing with each other. */
const QUESTION = 'Delete this run and everything in it?';

/* Said last, above the buttons, in the alert colour. */
const NO_UNDO = 'This cannot be undone.';

/* What goes, and what does not. The titles a window did not match
 * belong to no run: what the data model is missing outlives the
 * window that revealed it. */
const WHAT_GOES = (
  'Its revisions, events, opportunities, change log and jobs go with '
  + 'it. The titles its window did not match stay, because what the '
  + 'shift data model is missing outlives the run that found it.'
);

/* What the button that goes ahead says. Never a bare "Delete": it
 * names what it is about to do, the way the send's does. */
const CONFIRM = 'Delete this run';

/** Return the sentence restating what is about to go.
 *
 * @param {Object} run The run, as the contract lists it.
 * @returns {string} The line.
 */
export function restatement(run) {
  const { counts } = run;

  return (
    `${counted(counts.events, 'event')}, `
    + `${counted(counts.shifts, 'shift')}, `
    + `${counted(run.currentRevision, 'revision')}.`
  );
}

/** Return the confirmation in front of deleting a run.
 *
 * @param {Object} what What is being confirmed.
 * @param {Object} what.run The run about to go.
 * @param {Object} handlers What its two buttons do.
 * @param {Function} handlers.onConfirm Go ahead.
 * @param {Function} handlers.onCancel Close and change nothing.
 * @returns {ConfirmDialog} The dialog, ready to open.
 */
export function deleteDialog({ run }, handlers) {
  return new ConfirmDialog(
    {
      title: QUESTION,
      about: `${run.calendar} · ${windowText(run.window)}`,
      body: [
        el(
          'div',
          { class: 'delete-holds' },
          el('span', { class: 'confirm-line', text: restatement(run) }),
          runStatusTag(run)
        ),
        el('p', { class: 'muted meta', text: WHAT_GOES })
      ],
      warning: NO_UNDO,
      confirmLabel: CONFIRM,
      confirmIcon: 'trash',
      destructive: true
    },
    handlers
  );
}
