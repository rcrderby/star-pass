/* The gate in front of the things that cannot be undone.
 *
 * There are two: a send, which creates shifts Amplify has no undo
 * for, and a deletion, which destroys the only record on this side of
 * what a run held.  One object for both, the shape the command line's
 * `confirmed()` already has.
 *
 * Its job is to make somebody read the summary, so it **restates**
 * rather than asks: what is about to happen is on the card above the
 * button, supplied by the caller.  A typed confirmation tests typing,
 * and on a monthly task becomes something the hands do while the eyes
 * are elsewhere.
 *
 * On a different surface from the control that opened it, so the
 * click that does the irreversible thing is not in the place the last
 * click was.
 *
 * A caller passes what differs: what each restates and what its
 * button says.  What is the same is here.
 */

import { el, icon } from './dom.js';
import { Modal } from './modal.js';

/**
 * A confirmation, and the focus it takes and gives back.
 */
export class ConfirmDialog {
  /** Build the dialog over whatever opened it.
   *
   * @param {Object} what What is being confirmed.
   * @param {string} what.title The question, as a heading.
   * @param {string} what.about The line under it naming what this is
   *     about: the run and its window, in both cases so far.
   * @param {Array<Node>} what.body What is about to happen, restated.
   * @param {string} what.warning What cannot be taken back, said last
   *     and in the alert colour.
   * @param {string} what.confirmLabel What the button that goes ahead
   *     says. Never a bare "OK": it names what it is about to do.
   * @param {string} what.confirmIcon The glyph beside it.
   * @param {boolean} [what.destructive] Whether going ahead destroys
   *     something here rather than creating something elsewhere.
   * @param {Object} handlers What its two buttons do.
   * @param {Function} handlers.onConfirm Go ahead.
   * @param {Function} handlers.onCancel Close and change nothing.
   */
  constructor(
    {
      title,
      about,
      body,
      warning,
      confirmLabel,
      confirmIcon,
      destructive = false
    },
    handlers
  ) {
    this.handlers = handlers;

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
        el('span', { class: 'muted meta', text: about })
      ),
      ...body,
      el(
        'span',
        { class: 'confirm-warning meta' },
        icon('warning-circle'),
        el('span', { text: warning })
      ),
      el(
        'div',
        { class: 'confirm-actions' },
        el(
          'button',
          {
            type: 'button',
            class: destructive ? 'btn btn-danger' : 'btn btn-primary',
            onclick: () => {
              /* Taken away before the work starts, rather than left
               * over a screen that is about to redraw underneath it:
               * what happens next is a different screen, or a list
               * without the row this was about. */
              this.dismiss();
              handlers.onConfirm();
            }
          },
          icon(confirmIcon),
          confirmLabel
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
   * Separate from closing, because going ahead and changing your mind
   * both remove it and only one of them is a cancellation.
   *
   * @returns {void}
   */
  dismiss() {
    this.modal.dismiss();
  }

  /** Close without going ahead.
   *
   * @returns {void}
   */
  close() {
    this.modal.close();
  }
}
