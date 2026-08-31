/* What a dialog and a drawer both are: a panel over a scrim that
 * holds focus while it is open.
 *
 * Below both of them, because the part they share is the part that is
 * easy to get subtly wrong and impossible to see in a diff.  Focus has
 * to move in when it opens, stay inside while Tab is pressed, and go
 * back to whatever opened it when it closes; Escape has to close it
 * and stop there rather than reaching the screen behind.  Written
 * twice, one of the two would eventually be the one with the bug.
 *
 * What each of them supplies is what actually differs: the panel, and
 * where the scrim puts it.  The confirmation is a card in the middle
 * of the screen; the drawer is 452px against the right edge.
 */

/* What can be focused inside a panel, for the trap.  Queried each
 * time, because a panel is rebuilt when it is drawn.
 *
 * **`a[href]`, never a bare `[href]`.** Every icon is an `<svg>`
 * holding a `<use href="...">`, so a bare attribute selector matches
 * the first icon, which comes before the buttons and cannot take
 * focus - leaving the panel open with focus still behind it.
 */
const FOCUSABLE = [
  'button:not(:disabled)',
  'a[href]',
  'input:not(:disabled)',
  'select:not(:disabled)',
  'textarea:not(:disabled)',
  '[tabindex]:not([tabindex="-1"])'
].join(', ');

/**
 * A panel over a scrim, and the focus it takes and gives back.
 */
export class Modal {
  /** Build one over whatever opened it.
   *
   * @param {Node} panel The card or drawer this puts on screen. It
   *     carries its own `role` and label: what it is is the caller's
   *     to say, and a dialog and a drawer are not the same thing to
   *     something that cannot see them.
   * @param {Object} options How it behaves.
   * @param {string} options.scrimClass Class on the backdrop, which
   *     is what decides where the panel sits.
   * @param {Function} options.onClose Called when Escape or a click
   *     outside dismisses it. Not called when the caller takes the
   *     panel away itself, because going ahead and changing your mind
   *     both remove it and only one of them is a cancellation.
   */
  constructor(panel, { scrimClass, onClose }) {
    this.panel = panel;
    this.onClose = onClose;

    /* Where focus came from, so it can be given back. A panel that
     * dropped focus on the body would leave somebody working by
     * keyboard at the top of the page. */
    this.opener = document.activeElement;

    this.element = document.createElement('div');
    this.element.className = scrimClass;

    /* A click on the scrim is a click outside the panel, and only
     * that: a click that started inside and ended here as the pointer
     * moved is not somebody dismissing it. */
    this.element.onmousedown = (event) => {
      if (event.target === this.element) {
        this.close();
      }
    };

    this.element.append(panel);

    this.onKey = (event) => this.key(event);
    document.addEventListener('keydown', this.onKey);
  }

  /** Put it on screen and take focus into it.
   *
   * @param {Node} parent Where it goes.
   * @returns {void}
   */
  open(parent) {
    parent.append(this.element);

    const first = this.panel.querySelector(FOCUSABLE);

    if (first !== null) {
      first.focus();
    }
  }

  /** Keep Tab inside the panel, and let Escape close it.
   *
   * A modal that let Tab walk out of it would put focus on the screen
   * behind, which is the screen it exists to interrupt.
   *
   * @param {KeyboardEvent} event What was pressed.
   * @returns {void}
   */
  key(event) {
    if (event.key === 'Escape') {
      /* Stopped here rather than let through: the review screen
       * clears its selection on Escape, and closing this is what the
       * key meant while it was open. */
      event.stopPropagation();
      this.close();

      return;
    }

    if (event.key !== 'Tab') {
      return;
    }

    const inside = [...this.panel.querySelectorAll(FOCUSABLE)];

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

  /** Take it away and give focus back to what opened it.
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

  /** Close it the way changing your mind closes it.
   *
   * @returns {void}
   */
  close() {
    this.dismiss();
    this.onClose();
  }
}
