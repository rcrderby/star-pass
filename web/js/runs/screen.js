/* The runs list, which is where the page opens.
 *
 * Every run the service holds, newest first: what each one collected,
 * what it holds now, where it is, and the two things you can do to
 * one from outside it -- open it, or delete it.
 *
 * **A run is opened by its own address**, so a row is a link to a
 * path rather than a control that swaps the screen underneath. That
 * is what makes the middle-click, the bookmark and the second tab
 * work, and it is why the row is an `<a>` and not a `<button>`.
 *
 * **The delete control is drawn from the run's own answer.** A run
 * says whether it may be deleted (`mayDelete`), and a run that may
 * not is offered nothing rather than offered something that fails: a
 * run that has sent is kept for ever, and a run something is working
 * on becomes deletable when the work finishes (D24). Nothing here
 * works that rule out -- a second opinion about what the operation
 * will accept is one that agrees until the rule changes.
 *
 * A refusal is the service's own sentence. The one thing a screen
 * must never do with a failure is invent a reason for it, which is
 * what the preview did until #297.
 */

import { counted } from '../format.js';
import { deleteRun, listRuns } from '../api.js';
import { deleteDialog } from './confirm.js';
import { el, fill, icon, plainClick } from '../dom.js';
import { runIdCallout } from '../runid.js';
import { emptyState } from '../screens.js';
import { refusalNotice } from '../refusal.js';
import { collectedAt, runLabel, runStatusTag } from './summary.js';

/* The heading, and what the list is. */
const TITLE = 'Runs';
const LEDE = (
  'One run is one collection, from one calendar, over one window of '
  + 'league dates. Open one to review it; nothing reaches Amplify '
  + 'until it is sent.'
);

/* What the button above the list says. */
const COLLECT = 'Collect a new run';

/* Said above the list when an address named a run that is not there.
 * A refusal rather than the newest run drawn quietly in its place:
 * a bookmark to a deleted run is a question with an answer, and the
 * answer is that it is gone. */
const NO_SUCH_RUN = 'There is no run with that identifier. It may have been deleted.';

/* What a deletion that was refused is introduced by. The reason
 * itself is the service's. */
const NOT_DELETED = 'That run was not deleted.';

/* What a row's delete control says to something that cannot see it.
 * The label names the run, because a list of controls all saying
 * "Delete" is a list nothing can tell apart. */
const DELETE_LABEL = 'Delete';

/** Return the line under a run's name.
 *
 * The counts are what tell two runs apart when their windows do not:
 * a run holding a reviewed month and a run holding nothing read the
 * same way in a calendar and a date range alone.
 *
 * @param {Object} run A run, as the contract lists it.
 * @returns {string} What it says.
 */
function metaText(run) {
  const { counts } = run;
  const parts = [
    `Collected ${collectedAt(run)}`,
    counted(counts.events, 'event'),
    counted(counts.shifts, 'shift')
  ];

  if (counts.uncollected > 0) {
    parts.push(`${counts.uncollected} not collected`);
  }

  return parts.join(' · ');
}

/**
 * The list, and what it is in the middle of doing.
 */
export class RunsScreen {
  /** Hold the runs and draw them.
   *
   * @param {Object} answers What the service said.
   * @param {Array<Object>} answers.runs Every run, newest first.
   * @param {boolean} [answers.missing] Whether the address named a
   *     run the service does not hold.
   * @param {Object} handlers What the screen's exits do.
   * @param {Function} handlers.onOpenRun Open one, by its path.
   * @param {Function} handlers.onCollectNew Open the collect drawer.
   * @param {Function} handlers.onChanged Read the runs again, after
   *     one of them has gone.
   * @param {Function} handlers.pathForRun Where a run lives, so a row
   *     can be a link to it rather than a control that swaps screens.
   */
  constructor({ runs, missing = false }, handlers) {
    this.state = {
      runs,
      missing,
      busy: false,
      refusal: null
    };

    this.handlers = handlers;
    this.element = el('div', { class: 'runs' });

    this.draw();
  }

  /** Draw the whole screen.
   *
   * @returns {void}
   */
  draw() {
    const { runs, missing, refusal } = this.state;

    /* The empty state says what a run is, at length and with the
     * three steps. Saying it above as well would be saying it twice
     * on the one screen where there is nothing else to read. */
    const empty = runs.length === 0;

    fill(
      this.element,
      el(
        'div',
        { class: 'runs-head' },
        el(
          'div',
          {},
          el('h1', { class: 'runs-title', text: TITLE }),
          empty
            ? null
            : el('p', { class: 'muted meta runs-lede', text: LEDE })
        ),
        empty
          ? null
          : el(
            'button',
            {
              type: 'button',
              class: 'btn btn-primary',
              onclick: () => this.handlers.onCollectNew()
            },
            icon('download-simple'),
            COLLECT
          )
      ),
      missing
        ? el(
          'div',
          { class: 'banner banner-alert', role: 'alert' },
          icon('warning-circle'),
          el('span', { class: 'banner-words meta', text: NO_SUCH_RUN })
        )
        : null,
      refusal === null
        ? null
        : refusalNotice({ said: NOT_DELETED, failure: refusal }),
      empty
        ? emptyState(() => this.handlers.onCollectNew())
        : el(
          'div',
          { class: 'runs-list' },
          runs.map((run) => this.row(run))
        )
    );
  }

  /** Return one run's row.
   *
   * @param {Object} run A run, as the contract lists it.
   * @returns {HTMLElement} The row.
   */
  row(run) {
    const { info, callout } = runIdCallout(run, runLabel(run));

    /* A group holding the row and what opens under it, the way the
     * run picker's rows are built: the callout wants the width of
     * the whole row rather than the corner its control sits in. */
    return el(
      'div',
      { class: 'runs-row-group' },
      el(
        'div',
        { class: 'row-card runs-row' },
        el(
          'a',
          {
            class: 'runs-row-open',
            href: this.handlers.pathForRun(run.id),
            onclick: (event) => {
              if (!plainClick(event)) {
                return;
              }

              event.preventDefault();
              this.handlers.onOpenRun(run.id);
            }
          },
          el('span', { class: 'runs-row-label', text: runLabel(run) }),
          el('span', {
            class: 'runs-row-meta muted micro',
            text: metaText(run)
          })
        ),
        el(
          'span',
          { class: 'runs-row-side' },
          info,
          runStatusTag(run),
          run.mayDelete
            ? el(
              'button',
              {
                type: 'button',
                class: 'btn btn-icon btn-ghost',
                disabled: this.state.busy,
                'aria-label': `${DELETE_LABEL} ${runLabel(run)}`,
                title: DELETE_LABEL,
                onclick: () => this.confirmDelete(run)
              },
              icon('trash')
            )
            : null
        )
      ),
      callout
    );
  }

  /** Ask whether to delete a run (D11).
   *
   * @param {Object} run The run the control was pressed on.
   * @returns {void}
   */
  confirmDelete(run) {
    const dialog = deleteDialog(
      { run },
      {
        onConfirm: () => this.remove(run),
        onCancel: () => undefined
      }
    );

    dialog.open(document.body);
  }

  /** Delete a run and read the list again.
   *
   * The list is re-read rather than having the row taken out of it:
   * what else changed while somebody was reading this screen is the
   * service's answer, not an edit to a copy of it.
   *
   * **A refusal re-reads it too.** Both reasons a deletion is refused
   * are things that happened to the run after this screen was drawn
   * -- it was sent, or something started working on it -- so the
   * refusal is itself evidence that the row it came from is out of
   * date. Leaving it would be leaving a control that will refuse
   * again beside a status that is now wrong.
   *
   * @param {Object} run The run to delete.
   * @returns {Promise<void>} When it has gone, or been refused.
   */
  async remove(run) {
    this.state.busy = true;
    this.state.refusal = null;
    this.draw();

    try {
      await deleteRun(run.id);

      this.handlers.onChanged();

      return;
    } catch (error) {
      this.state.refusal = error;
    }

    try {
      this.state.runs = await listRuns();
    } catch {
      /* The rows on screen are the ones that were true a moment ago,
       * and a second failure is no reason to throw them away: what
       * this screen has to say is the refusal above them. */
    }

    this.state.busy = false;
    this.draw();
  }
}
