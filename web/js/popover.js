/* Something that opens beside the control that opened it.
 *
 * The run picker and the revision picker are the two here; the time
 * picker on each shift time is the third, and arrives with editing.
 * One implementation because all three close the same way -- Escape,
 * or a click anywhere else -- and three copies of that would be three
 * chances to forget the second one.
 *
 * Only one is open at a time.  Opening one closes whatever was open,
 * which is what stops two popovers overlapping each other with no way
 * back to the page.
 */

import { el } from './dom.js';

/* The popover showing now, so that opening another closes it. */
let open = null;

/** Return whether anything is open.
 *
 * Read by whoever else handles Escape: the design gives it an order,
 * and the selection is only cleared when there was no popover in
 * front of it.
 *
 * @returns {boolean} Whether a popover is showing.
 */
export function anyPopoverOpen() {
  return open !== null;
}

/** Close whatever is open, if anything.
 *
 * @returns {void}
 */
export function closeAnyPopover() {
  if (open !== null) {
    const closing = open;

    open = null;
    closing.close();
  }
}

/* Escape closes the innermost thing, and a click outside closes a
 * popover. Registered once for the page rather than per popover: a
 * listener added on open and removed on close is a listener that
 * survives whichever close path forgot to remove it.
 *
 * The click listener is on the capture phase so that a click landing
 * on another popover's trigger closes this one before that one opens. */
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') {
    closeAnyPopover();
  }
});

document.addEventListener('pointerdown', (event) => {
  if (open !== null && !open.element.contains(event.target)) {
    closeAnyPopover();
  }
}, true);

/**
 * A button, and what it opens beside itself.
 */
export class Popover {
  /** Build the trigger and hold what fills the panel.
   *
   * @param {Object} options How it behaves.
   * @param {HTMLElement} options.trigger The button that opens it.
   * @param {Function} options.contents Called on open, returning what
   *     goes inside. Called each time rather than once, so a panel
   *     shows what is true now.
   * @param {number} options.width How wide the panel is, in pixels.
   * @param {number} [options.top] How far below the trigger it sits.
   * @param {boolean} [options.bindClick] Whether clicking the trigger
   *     opens it. False for a field that opens on focus, where the
   *     click that follows the focus would toggle it straight shut.
   */
  constructor({ trigger, contents, width, top = 38, bindClick = true }) {
    this.trigger = trigger;
    this.contents = contents;
    this.width = width;
    this.top = top;
    this.panel = null;

    this.element = el('div', { class: 'popover-anchor' }, trigger);
    this.trigger.setAttribute('aria-expanded', 'false');

    if (bindClick) {
      this.trigger.addEventListener('click', () => this.toggle());
    }
  }

  /** Open it if closed, close it if open.
   *
   * @returns {void}
   */
  toggle() {
    if (this.panel === null) {
      this.show();
    } else {
      closeAnyPopover();
    }
  }

  /** Open it, closing whatever else was open.
   *
   * @returns {void}
   */
  show() {
    closeAnyPopover();

    this.panel = el('div', { class: 'popover' }, this.contents());

    /* Set through the CSSOM rather than a style attribute, which the
     * Content Security Policy refuses. */
    this.panel.style.setProperty('width', `${this.width}px`);
    this.panel.style.setProperty('top', `${this.top}px`);

    this.element.append(this.panel);
    this.trigger.setAttribute('aria-expanded', 'true');
    open = this;
  }

  /** Take it off the page.
   *
   * Called through 'closeAnyPopover' rather than directly, so that
   * what is open and what is on screen cannot disagree.
   *
   * @returns {void}
   */
  close() {
    if (this.panel !== null) {
      this.panel.remove();
      this.panel = null;
      this.trigger.setAttribute('aria-expanded', 'false');
    }
  }
}
