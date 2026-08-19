/* The gate in front of the one thing that cannot be undone (D11).
 *
 * Its job is to make somebody read the summary, which is why it
 * restates rather than asks: the count, the run and its window, and
 * what each opportunity is about to receive.  A typed confirmation
 * was rejected for this -- it tests typing, and on a task done once a
 * month it becomes something the hands do while the eyes are
 * elsewhere.
 *
 * On a different surface from the button that opened it, which is the
 * other half of D11: the click that reaches Amplify is not in the
 * place the last click was.
 *
 * Every figure here is the preview's, not a second reading of it.
 * The number in the title is the number in the button, the number the
 * request carries as `expectedShiftCount`, and the number the service
 * checks against a fresh read before it starts -- so a confirmation
 * agreeing with a screen that no longer agrees with Amplify is
 * refused rather than acted on.
 */

import { el, icon } from '../dom.js';
import { windowText } from '../format.js';
import { Modal } from '../modal.js';
import { counted } from './preview.js';

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

/**
 * The confirmation, and the focus it takes and gives back.
 */
export class ConfirmDialog {
  /** Build the dialog over whatever opened it.
   *
   * @param {Object} what What is being confirmed.
   * @param {Object} what.run The run, which names the window.
   * @param {Object} what.preview What a send would create.
   * @param {Object} handlers What its two buttons do.
   * @param {Function} handlers.onSend Go ahead.
   * @param {Function} handlers.onCancel Close and change nothing.
   */
  constructor({ run, preview }, handlers) {
    this.handlers = handlers;

    const willCreate = preview.totals.willCreate;
    const title = `Create ${counted(willCreate, 'shift')} in Amplify?`;

    this.card = el(
      'div',
      {
        class: 'card elev-lg confirm-card',
        role: 'dialog',
        'aria-modal': 'true',
        'aria-label': title
      },
      el(
        'div',
        {},
        el('h2', { class: 'confirm-title', text: title }),
        el('span', {
          class: 'muted meta',
          text: `${run.calendar} · ${windowText(run.window)}`
        })
      ),
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
      ),
      el(
        'span',
        { class: 'confirm-warning meta' },
        icon('warning-circle'),
        el('span', { text: NO_UNDO })
      ),
      el(
        'div',
        { class: 'confirm-actions' },
        el(
          'button',
          {
            type: 'button',
            class: 'btn btn-primary',
            onclick: () => {
              /* Taken away before the send starts, rather than left
               * over the screen that is about to redraw underneath
               * it: what happens next is a different screen. */
              this.dismiss();
              handlers.onSend();
            }
          },
          icon('paper-plane-tilt'),
          `Create ${counted(willCreate, 'shift')}`
        ),
        el(
          'button',
          {
            type: 'button',
            class: 'btn btn-secondary',
            onclick: () => this.close()
          },
          'Cancel'
        )
      )
    );

    this.modal = new Modal(this.card, {
      scrimClass: 'scrim scrim-centred',
      onClose: () => handlers.onCancel()
    });

    this.element = this.modal.element;
  }

  /** Put the dialog on screen and take focus into it.
   *
   * @param {Node} parent Where it goes.
   * @returns {void}
   */
  open(parent) {
    this.modal.open(parent);
  }

  /** Take the dialog away and give focus back to what opened it.
   *
   * Separate from closing, because going ahead and changing your
   * mind both remove it and only one of them is a cancellation.
   *
   * @returns {void}
   */
  dismiss() {
    this.modal.dismiss();
  }

  /** Close without sending.
   *
   * @returns {void}
   */
  close() {
    this.modal.close();
  }
}
