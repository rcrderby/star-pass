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

/* How close to the window's edge a panel is allowed to sit, so that
 * one pulled back inside it does not sit flush against it. */
const EDGE = 8;

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

    this.element.append(this.panel);
    this.place();
    this.trigger.setAttribute('aria-expanded', 'true');

    /* Where a fixed panel belongs is a fact about the drawn layout,
     * and the layout moves under it: the table scrolls sideways, the
     * page scrolls down, the run header is sticky and travels. Scroll
     * is listened for in the capture phase because it does not
     * bubble, and a scroll inside the table is the one that moves
     * this furthest. */
    this.follow = () => this.place();
    document.addEventListener('scroll', this.follow, true);
    window.addEventListener('resize', this.follow);

    open = this;
  }

  /** Put the panel where its anchor is.
   *
   * 'top' is how far below the anchor's own top edge the panel
   * sits and 'left' is the anchor's left edge, both read from the
   * anchor rather than stated.
   *
   * A panel wider than the room to its right is pulled back inside
   * the window; one taller than the room below it opens upwards where
   * there is room above.
   *
   * @returns {void}
   */
  place() {
    if (this.panel === null) {
      return;
    }

    /* The panel's own size is read from the layout rather than from
     * its drawn box: it animates in from 'translateY(-5px)
     * scale(0.98)', and a rectangle measured while that is running
     * is a couple of per cent short -- which would decide the flip
     * and the clamp below on a size the panel is about to stop
     * having. The anchor is not animated, so its box is its box. */
    const anchor = this.element.getBoundingClientRect();
    const width = this.panel.offsetWidth;
    const height = this.panel.offsetHeight;
    const below = anchor.top + this.top;
    const above = anchor.top - height - EDGE;
    const room = below + height <= window.innerHeight - EDGE;

    this.panel.style.setProperty(
      'left',
      `${Math.max(
        EDGE,
        Math.min(anchor.left, window.innerWidth - width - EDGE)
      )}px`
    );
    this.panel.style.setProperty(
      'top',
      `${room || above < EDGE ? below : above}px`
    );
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
      document.removeEventListener('scroll', this.follow, true);
      window.removeEventListener('resize', this.follow);
      this.panel.remove();
      this.panel = null;
      this.trigger.setAttribute('aria-expanded', 'false');
    }
  }
}
