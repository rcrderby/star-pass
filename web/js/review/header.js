/* The top of the review screen: which run, which revision, and the
 * two things you can do to the whole of it.
 *
 * Everything here reads.  'Collect again' opens the drawer over this
 * run, which is where the warning about what a replacement discards
 * belongs -- the drawer is what shows the window being asked for, and
 * the count is a fact about the run rather than about the button.
 */

import { changesNow } from './changelog.js';
import { el, icon } from '../dom.js';
import { runIdCallout } from '../runid.js';
import { counted, moment, windowText } from '../format.js';
import { Popover } from '../popover.js';
import { filled, phrase } from '../phrases.js';

/* What the two tabs are called. The count belongs to the second. */
const SHIFTS_TAB = 'Shifts to create';
const UNCOLLECTED_TAB = 'Not collected';

/* The last entry in the run picker. */
const NEW_RUN = 'Start a new run';

/* What the revision picker's two actions say. */
/* Over the identifier the callout shows. The run has an id because
 * the service minted one, and it is what names the run to the command
 * line and in a service's log -- which is the whole reason for
 * showing it, and why the callout says where it came from. */

/* On the control beside it, before and after it has been pressed. */

const SEAL = 'Save a revision now';
const REVERT = 'Revert';

/* What the revision picker says under its list. */
const ABOUT_REVISIONS = (
  'Reverting opens a new revision that duplicates the one you go '
  + 'back to. Nothing is deleted, so a revert can itself be reverted.'
);

/** Return the sentence under the run label.
 *
 * Counted off the rows the run is holding rather than off
 * 'run.counts', which is a second copy of the same two numbers and
 * was the one that could disagree: it arrives with the read and no
 * edit rewrites it, so removing a row left the line still counting
 * it. The picker's other runs keep using 'counts', which is all
 * they have -- the runs list carries no events.
 *
 * @param {Object} run The run being reviewed, with its events.
 * @returns {string} What it says.
 */
export function metaText(run) {
  const when = moment(run.collectedAt, run.window.timezone);
  const events = run.events.length;
  const shifts = run.events.reduce(
    (total, event) => total + event.roles.length,
    0
  );

  return (
    `Collected ${when}`
    + ` · ${counted(events, 'event')}`
    + ` · ${counted(shifts, 'shift')}`
  );
}

/** Return one run's line in the run picker.
 *
 * @param {Object} run A run, as the contract lists it.
 * @param {boolean} current Whether it is the one being reviewed.
 * @param {Function} onOpen What choosing it does.
 * @param {number} events How many it holds. Passed rather than read
 *     off 'run.counts', because the line for the run being reviewed
 *     has to agree with the line above it: that one counts the rows
 *     on screen, and an edit moves it.
 * @returns {HTMLElement} The line.
 */
function runLine(run, current, onOpen, events) {
  const { info, callout } = runIdCallout(
    run,
    `${run.calendar} ${windowText(run.window)}`
  );

  /* The row is a container holding controls rather than one control,
   * because it now holds two: the way into the run, and the way to
   * what the run is called. The revision picker's rows are already
   * built this way, and the CSS states what a row looks like apart
   * from what a button adds to it. */
  return el(
    'div',
    { class: 'picker-row-group' },
    el(
      'div',
      {
        class: current ? 'picker-row picker-row-current' : 'picker-row'
      },
      el(
        'button',
        {
          type: 'button',
          class: 'picker-row-main picker-row-open',
          onclick: () => onOpen(run.id)
        },
        el('span', {
          class: 'picker-row-label picker-row-calendar',
          text: `${run.calendar} · ${windowText(run.window)}`
        }),
        el('span', {
          class: 'picker-row-meta muted micro',
          text: `${moment(run.collectedAt, run.window.timezone)}`
            + ` · ${counted(events, 'event')}`
        })
      ),
      info,
      el('span', {
        class: run.sentAt ? 'tag tag-neutral' : 'tag tag-outline',
        text: phrase('runStatus', run.status)
      })
    ),
    callout
  );
}

/** Return one revision's line in the revision picker.
 *
 * The line names what each revision is and how much was done while it
 * was current, which is what a reader needs to tell them apart.
 *
 * **The current revision is offered no revert.** The service would
 * take one -- going back to where you already are is a legal request
 * -- and it would spend a revision to arrive at the revision it
 * started from. So the row that is current says so instead.
 *
 * @param {Object} revision A revision, as the contract lists it.
 * @param {Object} run The run, for the count on the current one.
 * @param {boolean} busy Whether a call is already in the air.
 * @param {Function} onRevert What going back to it does.
 * @returns {HTMLElement} The line.
 */
function revisionLine(revision, run, busy, onRevert) {
  /* The published count for a sealed revision, which is final, and
   * the log for the one being edited, which is not: an edit does not
   * read the revisions again, so the number the service last gave
   * for the current one describes a moment that has passed. */
  const changes = revision.current ? changesNow(run) : revision.changes;

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
        /* The two kinds a collection fills name no revision, and
         * their wording holds no placeholder to put one in. */
        text: `Revision ${revision.number} · `
          + filled('revision', revision.kind, {
            number: revision.sourceRevision
          })
      }),
      el('span', {
        class: 'picker-row-meta muted micro',
        text: `${changes} change${changes === 1 ? '' : 's'} made while `
          + 'it was current'
      })
    ),
    revision.current
      ? el('span', { class: 'tag tag-outline', text: 'Current' })
      : el(
        'button',
        {
          type: 'button',
          class: 'btn btn-ghost picker-row-action',
          disabled: busy,
          onclick: () => onRevert(revision.number)
        },
        icon('arrow-counter-clockwise'),
        REVERT
      )
  );
}

/** Return the entry that starts a fresh run.
 *
 * Here rather than beside "Collect again", which is about the run on
 * screen: this popover is where *which run* lives.
 *
 * It is also the only way to a second run.  Every other route into
 * the drawer carries the run being looked at, and a run that has sent
 * shifts refuses to be replaced.
 *
 * @param {Function} onCollectNew What pressing it does.
 * @returns {HTMLElement} The entry.
 */
function newRunLine(onCollectNew) {
  return el(
    'button',
    {
      type: 'button',
      class: 'picker-row picker-row-new',
      onclick: onCollectNew
    },
    icon('calendar-plus'),
    NEW_RUN
  );
}

/** Return the run picker.
 *
 * @param {Object} state What the screen is showing.
 * @param {Function} onOpenRun What choosing a run does.
 * @param {Function} onCollectNew What asking for a fresh one does.
 * @returns {HTMLElement} The picker.
 */
function runPicker(state, onOpenRun, onCollectNew) {
  const { run, runs } = state;
  const trigger = el(
    'button',
    { type: 'button', class: 'run-picker' },
    `${run.calendar} · ${windowText(run.window)}`,
    icon('caret-down')
  );

  return new Popover({
    trigger,
    width: 380,
    contents: () => [
      el('span', { class: 'popover-heading muted', text: 'Runs' }),
      runs.map((each) => {
        const current = each.id === run.id;

        return runLine(
          each,
          current,
          onOpenRun,
          current ? run.events.length : each.counts.events
        );
      }),
      el('div', { class: 'popover-rule' }),
      newRunLine(onCollectNew)
    ]
  }).element;
}

/** Return the revision picker.
 *
 * @param {Object} state What the screen is showing.
 * @param {Object} handlers What its two actions do.
 * @param {Function} handlers.onSeal Fix what the run holds now.
 * @param {Function} handlers.onRevert Go back to one revision.
 * @returns {HTMLElement} The picker.
 */
function revisionPicker(state, handlers) {
  const { run, revisions, busy } = state;
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
      revisions.map(
        (revision) => revisionLine(
          revision,
          run,
          busy,
          handlers.onRevert
        )
      ),
      el('div', { class: 'popover-rule' }),
      el(
        'button',
        {
          type: 'button',
          class: 'picker-row picker-row-new',
          /* A run that has collected nothing has no revision to
           * seal, which the service refuses. There is nothing to
           * offer rather than nothing to say. */
          disabled: busy || revisions.length === 0,
          onclick: handlers.onSeal
        },
        icon('bookmark-simple'),
        SEAL
      ),
      el('p', {
        class: 'popover-note muted micro',
        text: ABOUT_REVISIONS
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
        runPicker(state, handlers.onOpenRun, handlers.onCollectNew),
        run.sentAt
          ? el('span', {
            class: 'tag tag-accent',
            text: phrase('runStatus', run.status)
          })
          : null,
        tabs(state, handlers.onView)
      ),
      el('p', { class: 'run-meta muted meta', text: metaText(run) }),
      revisionPicker(state, handlers)
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
