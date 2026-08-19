/* A collection as it happens, and as it is picked back up.
 *
 * The same shape as the send: the request answers with a job, the job
 * runs in the service, and this screen is a reading of what that job
 * reports.  Nothing here is remembered between frames that could not
 * be rebuilt from the job's own event log, which a browser opening the
 * stream fresh is given from the first frame -- so leaving and coming
 * back draws the same screen.
 *
 * **Nothing reaches Amplify from here**, which is why leaving is
 * offered plainly and why there is no confirmation in front of it.
 * The collection reads a calendar, reads opportunity titles, and
 * writes to this service's own database.
 *
 * **There is no Cancel.**  The design draws one, saying that
 * cancelling leaves no trace because nothing has been written yet;
 * neither half survives contact with the API.  The run is minted by
 * the request and is in the list from the moment it answers, and the
 * contract publishes no way to stop a job.  A button that could only
 * stop watching is what "Leave this running" already is, and offering
 * it twice under two names -- one of them promising a rollback that
 * does not happen -- would be worse than not offering it.
 *
 * A failed collection leaves the run it minted, empty.  So "Try
 * again" is a *recollection* of that run rather than a second
 * collection: a fresh one would leave a stranded empty run behind
 * every failure, and replacing what this run holds is precisely what
 * the attempt was trying to do.
 */

import { ApiError, getRun, recollectRun } from '../api.js';
import { el, fill, icon } from '../dom.js';
import { moment } from '../format.js';
import { watchJob } from '../watching.js';
import {
  DONE,
  FAILED,
  RUNNING,
  STOPPED,
  freshSteps,
  stepList
} from './steps.js';

/* The kinds of job this screen follows. A run's active job may be a
 * send, which is a different screen. */
export const COLLECT_JOB = 'collect';
export const RECOLLECT_JOB = 'recollect';
export const COLLECT_JOBS = [COLLECT_JOB, RECOLLECT_JOB];

/* What the job says when it ended well, and what it says when the
 * service stopped while it was in hand (D10). */
const SUCCEEDED = 'succeeded';
const INTERRUPTED = 'interrupted';

/* Under the heading, while it works and afterwards. Says the two
 * things somebody watching needs: that nothing is being sent, and
 * that they may go away. */
const LEDE = (
  'Nothing is sent to Amplify by a collection. You can leave this '
  + 'page and come back to it, and when it finishes the new run opens '
  + 'for review.'
);

/* Beside the run identifier. The identifier is the service's, which
 * is the point of showing it. */
const MINTED = 'the service assigned this id, and it stays with the run';

/* Said beside the buttons while it runs. */
const LEAVING_IS_SAFE = (
  'Leaving does not stop it. The collection is listed under Runs '
  + 'while it works, and opening it comes back here.'
);

/* Said under a failure. A collection writes its events in one
 * transaction at the end, so a run whose collection failed holds
 * nothing rather than holding half a window. */
const NOTHING_STORED = (
  'Nothing was stored, so no run of yours has changed. Trying again '
  + 'reads the calendar into this same run.'
);

/* And what a collection the service stopped in the middle of says
 * instead of a reason, because there is none: nothing refused
 * anything and the job carries no detail. It is the same sentence
 * about consequences either way -- one transaction at the end means
 * an interrupted collection stored nothing, which is why this screen
 * offers the ordinary "Try again" rather than a resume. A resumed
 * collection would read the same calendar into the same run, which is
 * what trying again does, and it would do it under the identifier of
 * the attempt that stopped. */
const INTERRUPTED_STOPPED = (
  'The service stopped while this collection was running. Nothing '
  + 'reaches Amplify from a collection, so nothing was left half-done '
  + 'anywhere but here.'
);

/* When the connection dropped. Not a failure of the collection: the
 * browser reconnects on its own and is given what it missed. */
const RECONNECTING = (
  'Lost touch with the service for a moment. Reconnecting; the '
  + 'collection itself is unaffected.'
);

/** Return what to show for something that went wrong.
 *
 * @param {Error} error What went wrong.
 * @returns {string} What to put on screen. Already safe to display
 *     when it came from the service: the reason is replaced with a
 *     fixed sentence on the statuses where it is not the caller's to
 *     see.
 */
function asDetail(error) {
  if (error instanceof ApiError) {
    return error.detail;
  }

  console.error(error);

  return String(error.message || error);
}

/** Return what the heading says.
 *
 * @param {Object} state What the screen is showing.
 * @returns {string} The heading.
 */
function heading(state) {
  if (state.running) {
    return `Collecting from the ${state.calendar} calendar`;
  }

  if (state.failure === null) {
    return `Collected from the ${state.calendar} calendar`;
  }

  return state.interrupted
    ? 'The collection was interrupted'
    : 'The collection stopped';
}

/**
 * A collection, followed until it is over.
 */
export class CollectingScreen {
  /** Watch one collection.
   *
   * @param {Object} what What is being collected.
   * @param {Object} what.job The job doing it.
   * @param {Object} what.config The deployment's configuration, whose
   *     zone the job's times are shown in.
   * @param {string} [what.calendar] Which calendar is being read,
   *     when this screen started the collection and therefore knows.
   *     A screen picking a job up reads it from the run.
   * @param {Object} handlers Where the screen's exits go.
   * @param {Function} handlers.onOpenRun Called with the run to open,
   *     when the collection is over or somebody leaves it running.
   */
  constructor({ job, config, calendar = '' }, handlers) {
    this.handlers = handlers;
    this.config = config;

    this.state = {
      job,
      calendar,
      steps: freshSteps(),
      running: true,
      interrupted: false,
      failure: null,
      busy: false,
      lost: false,
      copied: ''
    };

    this.element = el('div', { class: 'screen' });

    this.follow(job);

    if (calendar === '') {
      this.readCalendarName(job.runId);
    }
  }

  /** Read which calendar the run being collected is reading.
   *
   * Only for a screen that did not start this collection: one that
   * did was told, and a run being collected again already says.
   *
   * @param {string} runId Which run.
   * @returns {Promise<void>} When the heading can say.
   */
  async readCalendarName(runId) {
    try {
      const run = await getRun(runId);

      this.state.calendar = run.calendar;
    } catch (error) {
      /* The heading loses a word; the collection is what matters and
       * is still being followed. */
      console.error(error);
    }

    this.draw();
  }

  /** Follow one job until it is over.
   *
   * @param {Object} job The job doing the collection.
   * @returns {void}
   */
  follow(job) {
    this.state.job = job;
    this.state.lost = false;
    this.state.running = true;

    this.source = watchJob(job, this);

    this.draw();
  }

  /** Say that the connection dropped.
   *
   * Not a failure of the collection: the browser reconnects on its
   * own and is given what it missed.
   *
   * @returns {void}
   */
  lost() {
    this.state.lost = true;
    this.draw();
  }

  /** Return the entry for one step.
   *
   * @param {string} step Which one.
   * @returns {Object|undefined} Its entry, when it is one of the
   *     five. A step this screen does not draw is one belonging to
   *     another kind of job.
   */
  stepFor(step) {
    return this.state.steps.find((each) => each.step === step);
  }

  /** Take in one thing the job reported.
   *
   * @param {string} kind What happened.
   * @param {Object} payload What it carried.
   * @returns {void}
   */
  reported(kind, payload) {
    this.state.lost = false;

    if (kind === 'step_started') {
      const entry = this.stepFor(payload.step);

      if (entry !== undefined) {
        entry.state = RUNNING;
      }
    }

    if (kind === 'step_finished' || kind === 'step_failed') {
      /* Neither frame names its step: they close whichever one was
       * last started, which is the only one that can be running. */
      const running = this.state.steps.find(
        (each) => each.state === RUNNING
      );

      if (running !== undefined) {
        running.state = kind === 'step_finished' ? DONE : FAILED;
      }
    }

    this.draw();
  }

  /** Take in the job's last frame.
   *
   * A collection stops at the first thing that raises, so a failed
   * job leaves exactly one step unfinished -- the one it was working
   * on. That step is what failed, and the ones after it were never
   * reached and stay pending, which is what they are.
   *
   * @param {Object} ending The job's identifier, status and detail.
   * @returns {void}
   */
  finished(ending) {
    this.state.running = false;
    this.state.lost = false;
    this.state.interrupted = ending.status === INTERRUPTED;

    if (ending.status === SUCCEEDED) {
      this.handlers.onOpenRun(this.state.job.runId);

      return;
    }

    const reached = this.state.steps.find(
      (each) => each.state === RUNNING
    );

    if (reached !== undefined) {
      reached.state = this.state.interrupted ? STOPPED : FAILED;
    }

    this.state.failure = ending;
    this.draw();
  }

  /** Read the calendar into this run again.
   *
   * @returns {Promise<void>} When the new job is being followed, or
   *     the refusal is on screen.
   */
  async again() {
    this.state.busy = true;
    this.draw();

    try {
      const run = await getRun(this.state.job.runId);
      const changes = run.log.filter(
        (entry) => entry.revision === run.currentRevision
      ).length;
      const job = await recollectRun(run.id, changes);

      this.state.steps = freshSteps();
      this.state.failure = null;
      this.state.interrupted = false;
      this.state.busy = false;
      this.follow(job);
    } catch (error) {
      this.state.busy = false;
      this.state.failure = { detail: asDetail(error) };
      this.draw();
    }
  }

  /** Put a reference on the clipboard.
   *
   * @param {string} reference What to copy.
   * @returns {Promise<void>} When it has been copied.
   */
  async copy(reference) {
    try {
      await navigator.clipboard.writeText(reference);
      this.state.copied = reference;
    } catch (error) {
      /* Refused, which a browser is allowed to do. The reference is
       * on screen either way, which is what it is for. */
      console.error(error);
    }

    this.draw();
  }

  /** Stop following, without stopping the collection.
   *
   * @returns {void}
   */
  release() {
    if (this.source !== undefined && this.source !== null) {
      this.source.close();
      this.source = null;
    }
  }

  /** Return the strip naming the run.
   *
   * @returns {HTMLElement} The strip.
   */
  runStrip() {
    const { job } = this.state;
    const started = job.startedAt || job.createdAt;

    return el(
      'div',
      { class: 'collect-run' },
      el('span', { class: 'muted collect-run-label', text: 'Run' }),
      el('span', { class: 'mono collect-run-id', text: job.runId }),
      el('span', {
        class: 'muted micro',
        text: `Started ${moment(started, this.config.timezone)} · ${MINTED}`
      })
    );
  }

  /** Return what a failed collection offers.
   *
   * @returns {HTMLElement} The failure.
   */
  failureCard() {
    const { failure, busy, copied } = this.state;

    return el(
      'div',
      { class: 'collect-failure', role: 'alert' },
      el(
        'span',
        { class: 'collect-failure-words' },
        icon('warning-circle'),
        el('span', {
          text: failure.detail
            || (this.state.interrupted
              ? INTERRUPTED_STOPPED
              : 'The collection failed.')
        })
      ),
      el(
        'div',
        { class: 'collect-failure-actions' },
        el(
          'button',
          {
            type: 'button',
            class: 'btn btn-primary',
            disabled: busy,
            onclick: () => this.again()
          },
          icon('arrow-clockwise'),
          'Try again'
        ),
        el(
          'button',
          {
            type: 'button',
            class: 'btn btn-secondary',
            disabled: busy,
            onclick: () => this.handlers.onOpenRun(this.state.job.runId)
          },
          'Back to the run'
        ),
        /* The job's own identifier is the reference. A job that failed
         * carries no reference of its own, because that is what the
         * service logged the reason against. */
        el(
          'button',
          {
            type: 'button',
            class: 'btn btn-ghost',
            onclick: () => this.copy(this.state.job.id)
          },
          icon('copy'),
          copied === this.state.job.id ? 'Copied' : this.state.job.id
        )
      ),
      el('span', { class: 'muted micro', text: NOTHING_STORED })
    );
  }

  /** Return what a running collection offers.
   *
   * @returns {HTMLElement} The actions.
   */
  runningActions() {
    return el(
      'div',
      { class: 'collect-actions' },
      el(
        'button',
        {
          type: 'button',
          class: 'btn btn-secondary',
          onclick: () => this.handlers.onOpenRun(this.state.job.runId)
        },
        'Leave this running'
      ),
      el('span', { class: 'muted meta', text: LEAVING_IS_SAFE })
    );
  }

  /** Draw the screen.
   *
   * @returns {void}
   */
  draw() {
    const { running, failure, lost, steps } = this.state;

    fill(
      this.element,
      el('h1', { class: 'screen-title', text: heading(this.state) }),
      el('p', { class: 'muted collect-lede', text: LEDE }),
      this.runStrip(),
      lost
        ? el(
          'div',
          { class: 'collect-lost' },
          icon('warning-circle'),
          el('span', { text: RECONNECTING })
        )
        : null,
      stepList(steps),
      failure === null ? null : this.failureCard(),
      running ? this.runningActions() : null
    );
  }
}
