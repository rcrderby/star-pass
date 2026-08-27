/** The control that shows a run's identifier, and what it opens.
 *
 * Two screens offer it -- the run picker on the review screen and the
 * runs list -- and neither is below the other, so it lives here
 * rather than in either.  Two copies would also be two answers to
 * what the callout says and how it closes, which is the thing that
 * drifts.
 *
 * Not a 'Popover': that places a panel over the page beside its
 * trigger, and this opens inside the row it belongs to, pushing what
 * is under it down.  A run identifier is something to read and copy
 * rather than a menu to pick from, and a row that grows says which
 * run it belongs to without an arrow having to.
 */

// Imports - Local
import { copyText } from './clipboard.js';
import { el, icon } from './dom.js';

/* What the label above the identifier says.  Written as a word and
 * drawn in capitals by the CSS, which is what the collecting screen
 * does with the same label -- they share the class, so there is one
 * answer to what it looks like. */
const RUN_ID = 'Run id';

/* On the control that copies, and what it says once it has. */
const COPY = 'Copy';
const COPIED = 'Copied';

/* On the control that opens it, and the one that shuts it again. */
const OPEN = 'The run id';
const CLOSE = 'Close';

/** Return the control that opens a run's identifier, and the callout.
 *
 * The two are returned together rather than as one element because
 * the caller puts them in different places: the control belongs
 * beside the row's other controls, and the callout below the whole
 * row, where it has the width to hold an identifier without wrapping
 * it.
 *
 * @param {Object} run A run, as the contract lists it.
 * @param {string} named What to call the run in the label a screen
 *     reader reads, so that a page of these says which is which.
 * @returns {Object} The 'info' control and the 'callout' it opens.
 */
export function runIdCallout(run, named) {
  const copy = el(
    'button',
    {
      type: 'button',
      class: 'btn btn-ghost',
      onclick: async () => {
        const went = await copyText(run.id);

        copy.replaceChildren(
          icon(went ? 'check' : 'copy'),
          went ? COPIED : COPY
        );
      }
    },
    icon('copy'),
    COPY
  );

  const close = el(
    'button',
    {
      type: 'button',
      class: 'btn btn-icon btn-ghost run-id-close',
      'aria-label': CLOSE,
      title: CLOSE,
      onclick: () => show(false)
    },
    icon('x')
  );

  const callout = el(
    'div',
    { class: 'run-id-callout', hidden: true },
    close,
    el('span', { class: 'muted run-id-label', text: RUN_ID }),
    el(
      'span',
      { class: 'run-id-line' },
      el('span', { class: 'mono run-id-value', text: run.id }),
      copy
    )
  );

  const info = el(
    'button',
    {
      type: 'button',
      class: 'btn btn-ghost btn-icon run-id-open',
      'aria-label': `${OPEN} for ${named}`,
      'aria-expanded': 'false',
      title: OPEN,
      onclick: () => show(callout.hidden)
    },
    icon('info')
  );

  /** Open it or shut it, from either control.
   *
   * Stated once because two controls change the same thing, and the
   * attribute a screen reader reads has to move with the panel it
   * describes whichever of them was pressed.
   *
   * @param {boolean} opening Whether it is being opened.
   * @returns {void}
   */
  function show(opening) {
    callout.hidden = !opening;
    info.setAttribute('aria-expanded', String(opening));

    if (!opening) {
      info.focus();
    }
  }

  return { info, callout };
}
