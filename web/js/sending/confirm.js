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

/* What can be focused inside the dialog, for the trap. Queried rather
 * than kept as a list, because the buttons are rebuilt when the
 * dialog is drawn and a remembered element would be one that is no
 * longer on screen.
 *
 * **`a[href]`, never a bare `[href]`.** Every icon on these screens is
 * an `<svg>` holding a `<use href="...">`, so a bare attribute
 * selector matches the first icon in the card -- which comes before
 * the buttons, and which focusing does nothing at all. The dialog
 * then opens with focus still on the button behind it, which is the
 * one thing a modal must not do. */
const FOCUSABLE = [
  'button:not(:disabled)',
  'a[href]',
  'input:not(:disabled)',
  'select:not(:disabled)',
  'textarea:not(:disabled)',
  '[tabindex]:not([tabindex="-1"])'
].join(', ');

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

    /* Where focus came from, so it can be given back. A dialog that
     * dropped focus on the body would leave somebody working by
     * keyboard at the top of the page. */
    this.opener = document.activeElement;

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

    this.element = el(
      'div',
      {
        class: 'scrim',
        /* A click on the scrim is a click outside the dialog, and
         * only that: a click that started inside and ended here as
         * the pointer moved is not somebody dismissing it. */
        onmousedown: (event) => {
          if (event.target === this.element) {
            this.close();
          }
        }
      },
      this.card
    );

    this.onKey = (event) => this.key(event);
    document.addEventListener('keydown', this.onKey);
  }

  /** Put the dialog on screen and take focus into it.
   *
   * @param {Node} parent Where it goes.
   * @returns {void}
   */
  open(parent) {
    parent.append(this.element);

    const first = this.card.querySelector(FOCUSABLE);

    if (first !== null) {
      first.focus();
    }
  }

  /** Keep Tab inside the dialog, and let Escape close it.
   *
   * A modal that let Tab walk out of it would put focus on the
   * screen behind, which is the screen this exists to interrupt.
   *
   * @param {KeyboardEvent} event What was pressed.
   * @returns {void}
   */
  key(event) {
    if (event.key === 'Escape') {
      event.stopPropagation();
      this.close();

      return;
    }

    if (event.key !== 'Tab') {
      return;
    }

    const inside = [...this.card.querySelectorAll(FOCUSABLE)];

    if (inside.length === 0) {
      return;
    }

    const first = inside[0];
    const last = inside[inside.length - 1];

    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  /** Take the dialog away and give focus back to what opened it.
   *
   * Separate from closing, because going ahead and changing your
   * mind both remove it and only one of them is a cancellation.
   *
   * @returns {void}
   */
  dismiss() {
    document.removeEventListener('keydown', this.onKey);
    this.element.remove();

    if (this.opener !== null && this.opener.isConnected) {
      this.opener.focus();
    }
  }

  /** Close without sending.
   *
   * @returns {void}
   */
  close() {
    this.dismiss();
    this.handlers.onCancel();
  }
}
