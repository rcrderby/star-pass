/* The top of the review screen: which run, which revision, and the
 * two things you can do to the whole of it.
 *
 * Everything here reads.  'Collect again' opens the drawer over this
 * run, which is where the warning about what a replacement discards
 * belongs -- the drawer is what shows the window being asked for, and
 * the count is a fact about the run rather than about the button.
 */

import { el, icon } from '../dom.js';
import { moment, windowText } from '../format.js';
import { Popover } from '../popover.js';
import { phrase } from '../phrases.js';

/* What the two tabs are called. The count belongs to the second. */
const SHIFTS_TAB = 'Shifts to create';
const UNCOLLECTED_TAB = 'Not collected';

/** Return the sentence under the run label.
 *
 * @param {Object} run The run being reviewed.
 * @returns {string} What it says.
 */
function metaText(run) {
  const when = moment(run.collectedAt, run.window.timezone);
  const events = run.counts.events;
  const shifts = run.counts.shifts;

  return (
    `Collected ${when}, changes save as you make them`
    + ` · ${events} event${events === 1 ? '' : 's'}`
    + ` · ${shifts} shift${shifts === 1 ? '' : 's'}`
  );
}

/** Return one run's line in the run picker.
 *
 * @param {Object} run A run, as the contract lists it.
 * @param {boolean} current Whether it is the one being reviewed.
 * @param {Function} onOpen What choosing it does.
 * @returns {HTMLElement} The line.
 */
function runLine(run, current, onOpen) {
  return el(
    'button',
    {
      type: 'button',
      class: current ? 'picker-row picker-row-current' : 'picker-row',
      onclick: () => onOpen(run.id)
    },
    el(
      'span',
      { class: 'picker-row-main' },
      el('span', {
        class: 'picker-row-label',
        text: `${run.calendar} · ${windowText(run.window)}`
      }),
      el('span', {
        class: 'picker-row-meta muted micro',
        text: `${moment(run.collectedAt, run.window.timezone)}`
          + ` · ${run.counts.events} events`
      })
    ),
    el('span', {
      class: run.sentAt ? 'tag tag-neutral' : 'tag tag-outline',
      text: phrase('runStatus', run.status)
    })
  );
}

/** Return one revision's line in the revision picker.
 *
 * Reverting is a write and arrives with editing. The line names what
 * each revision is and how much was done while it was current, which
 * is what a reader needs to tell them apart.
 *
 * @param {Object} revision A revision, as the contract lists it.
 * @returns {HTMLElement} The line.
 */
function revisionLine(revision) {
  const changes = revision.changes;

  return el(
    'div',
    {
      class: revision.current
        ? 'picker-row picker-row-current'
        : 'picker-row'
    },
    el(
      'span',
      { class: 'picker-row-main' },
      el('span', {
        class: 'picker-row-label',
        text: `Revision ${revision.number} · ${revision.label}`
      }),
      el('span', {
        class: 'picker-row-meta muted micro',
        text: `${changes} change${changes === 1 ? '' : 's'} made while `
          + 'it was current'
      })
    ),
    revision.current
      ? el('span', { class: 'tag tag-outline', text: 'Current' })
      : null
  );
}

/** Return the run picker.
 *
 * @param {Object} state What the screen is showing.
 * @param {Function} onOpenRun What choosing a run does.
 * @returns {HTMLElement} The picker.
 */
function runPicker(state, onOpenRun) {
  const { run, runs } = state;
  const trigger = el(
    'button',
    { type: 'button', class: 'run-picker' },
    `${run.calendar} · ${windowText(run.window)}`,
    icon('caret-down')
  );

  return new Popover({
    trigger,
    width: 340,
    contents: () => [
      el('span', { class: 'popover-heading muted', text: 'Runs' }),
      runs.map(
        (each) => runLine(each, each.id === run.id, onOpenRun)
      )
    ]
  }).element;
}

/** Return the revision picker.
 *
 * @param {Object} state What the screen is showing.
 * @returns {HTMLElement} The picker.
 */
function revisionPicker(state) {
  const { run, revisions } = state;
  const trigger = el(
    'button',
    { type: 'button', class: 'revision-picker' },
    icon('clock-counter-clockwise'),
    `Revision ${run.currentRevision} of ${revisions.length}`,
    icon('caret-down')
  );

  return new Popover({
    trigger,
    width: 330,
    top: 30,
    contents: () => [
      el('span', { class: 'popover-heading muted', text: 'Revisions' }),
      revisions.map(revisionLine),
      el('p', {
        class: 'popover-note muted micro',
        text: 'Saving a revision and going back to one arrive with '
          + 'editing.'
      })
    ]
  }).element;
}

/** Return the two-tab control.
 *
 * @param {Object} state What the screen is showing.
 * @param {Function} onView What changing tab does.
 * @returns {HTMLElement} The control.
 */
function tabs(state, onView) {
  const uncollected = state.run.counts.uncollected;

  return el(
    'div',
    { class: 'seg', role: 'tablist', 'aria-label': 'What to look at' },
    el(
      'button',
      {
        type: 'button',
        class: 'seg-opt',
        role: 'tab',
        'aria-selected': String(state.view === 'shifts'),
        'aria-pressed': String(state.view === 'shifts'),
        onclick: () => onView('shifts')
      },
      SHIFTS_TAB
    ),
    el(
      'button',
      {
        type: 'button',
        class: 'seg-opt',
        role: 'tab',
        'aria-selected': String(state.view === 'uncollected'),
        'aria-pressed': String(state.view === 'uncollected'),
        onclick: () => onView('uncollected')
      },
      UNCOLLECTED_TAB,
      uncollected > 0
        ? el('span', {
          class: 'tag tag-neutral mono',
          text: String(uncollected)
        })
        : null
    )
  );
}

/** Return the review screen's header.
 *
 * @param {Object} state What the screen is showing.
 * @param {Object} handlers What its controls do.
 * @returns {HTMLElement} The header.
 */
export function reviewHeader(state, handlers) {
  const { run } = state;

  return el(
    'header',
    { class: 'run-header' },
    el(
      'div',
      { class: 'run-header-main' },
      el(
        'div',
        { class: 'run-header-top' },
        runPicker(state, handlers.onOpenRun),
        run.sentAt
          ? el('span', {
            class: 'tag tag-accent',
            text: phrase('runStatus', run.status)
          })
          : null,
        tabs(state, handlers.onView)
      ),
      el('p', { class: 'run-meta muted meta', text: metaText(run) }),
      revisionPicker(state)
    ),
    el(
      'div',
      { class: 'run-header-actions' },
      el(
        'button',
        {
          type: 'button',
          class: 'btn btn-secondary',
          onclick: handlers.onCollectAgain
        },
        icon('arrows-clockwise'),
        'Collect again'
      ),
      el(
        'button',
        {
          type: 'button',
          class: 'btn btn-primary',
          onclick: handlers.onPreview
        },
        icon('arrow-right'),
        'Preview shifts'
      )
    )
  );
}
