/* Preview, confirm, send: the three screens the run leaves by.
 *
 * One screen object rather than three, because they are one movement
 * and share one thing between them -- what the preview said.  The
 * confirmation restates it, the request carries its `willCreate` as
 * `expectedShiftCount`, and the sending screen starts from its rows.
 * Split apart, each would have to be handed the same answer anyway.
 *
 * **The client decides nothing.**  What would be created, what
 * Amplify already holds, what blocks the run and how far the send has
 * got are all read.  The rules the review screen established hold
 * here too: an action is one call, its answer is what the screen
 * redraws from, and a refusal is a notice rather than a screen-wide
 * failure -- what was being looked at is still worth looking at.
 *
 * The exception is the send itself, which is not one call but a call
 * and a stream.  The call answers with a job; the stream says what
 * the job is doing.  Nothing waits for the send: the browser is not
 * what holds it open, and this screen can be closed and reopened
 * against the same job.
 *
 * **Both ways to the send go through the confirmation** (D11), which
 * is why the retry reads the preview again before it opens one: the
 * count it restates has to be the count the request carries, and
 * after a partial send that is no longer the number anybody agreed
 * to.
 */

import {
  ApiError,
  getPreview,
  idempotencyKey,
  sendRun
} from '../api.js';
import { el, icon } from '../dom.js';
import { phrase } from '../phrases.js';
import { watchJob } from '../watching.js';
import { ConfirmDialog } from './confirm.js';
import {
  checksCard,
  previewActions,
  previewTable,
  summaryLine
} from './preview.js';
import {
  DONE,
  FAILED,
  SENDING,
  WAITING,
  sendingScreen
} from './progress.js';

/* The kind of job this screen follows. A run's active job may be a
 * collection, which is a different screen. */
export const SEND_JOB = 'send';

/* What the job says when it ended well. */
const SUCCEEDED = 'succeeded';

/* The step whose subject names the opportunity being worked on. The
 * send reports it immediately before writing to that opportunity, so
 * it is what moves a row from waiting to sending. */
const READ_OPPORTUNITY = 'read_opportunity';

/* What the preview says while it has not arrived. Its own line rather
 * than an empty screen: the request reads every opportunity from
 * Amplify, so it is the slowest thing either screen does. */
const READING = 'Reading what a send would create, and asking Amplify '
  + 'what it already has.';

/* Said on the preview screen when a retry found nothing left to do. */
const RETRY_NOTHING = (
  'Nothing was left to send: Amplify already holds every shift this '
  + 'run asks for.'
);

/** Return a row of the sending screen, before anything is known.
 *
 * @param {string} needId The opportunity.
 * @param {string} title What it is called.
 * @returns {Object} The row.
 */
function waitingRow(needId, title) {
  return {
    needId,
    title,
    state: WAITING,
    created: 0,
    skipped: 0,
    detail: ''
  };
}

/**
 * The preview, the confirmation and the send, in that order.
 */
export class SendingScreen {
  /** Prepare to show what a send would do.
   *
   * @param {Object} what What is being sent.
   * @param {Object} what.run The run, in full.
   * @param {Object} [what.job] A send already under way, when this
   *     screen is picking one up rather than starting it.
   * @param {Object} handlers Where the screen's exits go.
   * @param {Function} handlers.onBack Return to the run.
   */
  constructor({ run, job = null }, handlers) {
    this.handlers = handlers;

    /* What each opportunity is called, from the run rather than from
     * the stream. A run stores the titles its collection resolved, so
     * a browser that picks up a send it did not start can name a row
     * before the send has finished with it -- which is the difference
     * between a reattached screen showing "Junior Games: Skating
     * Officials" and showing 905198. */
    this.titles = new Map(
      run.opportunities.map((each) => [each.needId, each.title])
    );

    this.state = {
      run,
      preview: null,
      reading: false,
      failure: null,
      notice: '',
      jobId: null,
      total: 0,
      rows: [],
      running: false,
      lost: false,
      copied: ''
    };

    this.element = el('div', { class: 'screen' });

    if (job === null) {
      this.read();
    } else {
      this.attach(job);
    }
  }

  /** Read the preview, and draw whatever that answers.
   *
   * @returns {Promise<void>} When it is on screen.
   */
  async read() {
    this.state.reading = true;
    this.state.failure = null;
    this.draw();

    try {
      this.state.preview = await getPreview(this.state.run.id);
    } catch (error) {
      this.state.failure = this.asApiError(error);
    } finally {
      this.state.reading = false;
      this.draw();
    }
  }

  /** Return an error as a screen can show one.
   *
   * @param {Error} error What went wrong.
   * @returns {ApiError} The failure, shaped for a screen.
   */
  asApiError(error) {
    if (error instanceof ApiError) {
      return error;
    }

    console.error(error);

    return new ApiError({
      status: 0,
      detail: String(error.message || error)
    });
  }

  /** Open the confirmation over the preview.
   *
   * @returns {void}
   */
  confirm() {
    const dialog = new ConfirmDialog(
      { run: this.state.run, preview: this.state.preview },
      {
        onSend: () => this.send(this.state.preview.totals.willCreate),
        onCancel: () => {}
      }
    );

    dialog.open(this.element);
  }

  /** Ask for the shifts to be created, and follow the job that does.
   *
   * The key names this attempt. A retry of *this* request sends it
   * again and is answered with the first answer rather than sending
   * twice; asking again after a partial send is a different action
   * and takes a new one.
   *
   * @param {number} expected What the operator was shown.
   * @returns {Promise<void>} When the job is being followed.
   */
  async send(expected) {
    this.state.notice = '';
    this.state.rows = this.state.preview.rows.map(
      (row) => waitingRow(row.needId, row.title === null
        ? row.needId
        : row.title)
    );
    this.state.total = this.state.rows.length;
    this.state.running = true;
    this.draw();

    try {
      const job = await sendRun(
        this.state.run.id,
        expected,
        idempotencyKey()
      );

      this.follow(job);
    } catch (error) {
      /* Refused before a job existed, so nothing was written and the
       * preview is what to go back to -- most often because what was
       * shown no longer matches what a send would create, which is
       * the case the count exists to catch. */
      this.state.running = false;
      this.state.failure = this.asApiError(error);
      this.state.rows = [];
      this.draw();
      this.read();
    }
  }

  /** Show a send that was already running when this screen opened.
   *
   * Everything drawn comes from the job's own event log, which the
   * stream replays from its first frame for a client that is not
   * resuming. So a reload during a send is answered with what it
   * missed, and there is nothing to read from Amplify to catch up.
   *
   * @param {Object} job The job, as the service reports it.
   * @returns {void}
   */
  attach(job) {
    this.state.running = true;
    this.follow(job);
    this.draw();
  }

  /** Follow one job until it is over.
   *
   * @param {Object} job The job doing the send.
   * @returns {void}
   */
  follow(job) {
    this.state.jobId = job.id;
    this.state.lost = false;

    this.source = watchJob(job, this);

    this.draw();
  }

  /** Say that the connection dropped.
   *
   * Not a failure of the send: the browser reconnects on its own and
   * is given what it missed.
   *
   * @returns {void}
   */
  lost() {
    this.state.lost = true;
    this.draw();
  }

  /** Return the row for one opportunity, adding it when it is new.
   *
   * A reattached screen has no preview, so the first it hears of an
   * opportunity is the send working on it.
   *
   * @param {string} needId Which opportunity.
   * @param {string} [title] What it is called, when the event said.
   * @returns {Object} The row.
   */
  rowFor(needId, title = '') {
    let row = this.state.rows.find((each) => each.needId === needId);

    if (row === undefined) {
      row = waitingRow(
        needId,
        title || this.titles.get(needId) || needId
      );
      this.state.rows.push(row);
    }

    if (title) {
      row.title = title;
    }

    return row;
  }

  /** Take in one thing the job reported.
   *
   * @param {string} kind What happened.
   * @param {Object} payload What it carried.
   * @returns {void}
   */
  reported(kind, payload) {
    this.state.lost = false;

    if (kind === 'sending_started') {
      /* The total, and the only place it is published. A screen that
       * counted its own rows would be counting what it had been told
       * about so far. */
      this.state.total = payload.opportunities;
    }

    if (kind === 'step_started' && payload.step === READ_OPPORTUNITY) {
      this.rowFor(payload.subject).state = SENDING;
    }

    if (kind === 'opportunity_sent') {
      const row = this.rowFor(payload.needId, payload.title);

      row.state = DONE;
      row.created = payload.shifts.length;
      row.skipped = payload.skipped;
    }

    this.draw();
  }

  /** Take in the job's last frame.
   *
   * A send stops at the first opportunity Amplify refuses rather than
   * carrying on, so a failed job leaves exactly one row unfinished --
   * the one it was working on. That row is what failed; the ones
   * after it were never reached and stay waiting, which is what they
   * are.
   *
   * @param {Object} ending The job's identifier, status and detail.
   * @returns {void}
   */
  finished(ending) {
    this.state.running = false;
    this.state.lost = false;

    if (ending.status !== SUCCEEDED) {
      const reached = this.state.rows.find(
        (row) => row.state === SENDING
      );

      if (reached !== undefined) {
        reached.state = FAILED;
        reached.detail = ending.detail || '';
      }
    }

    this.draw();
  }

  /** Read the preview again, and confirm what is left to send.
   *
   * **Read again, because the count has moved.** Some of what the
   * first attempt was confirmed against is now in Amplify, so the
   * number that request carried describes a moment that has passed
   * and a second one carrying it would be refused, rightly.
   *
   * **Confirmed again, because a retry is a send.** D11 gates the
   * write and does not distinguish the first from the second; the
   * design draws this as a plain button because the prototype it was
   * drawn against could not have its count move underneath it. And
   * the guard that protects the first send stops guarding here
   * otherwise: `expectedShiftCount` is what somebody read and agreed
   * to, but a retry that read the preview and handed the same number
   * straight back satisfies that check by construction. It could
   * never refuse, and nobody would have seen the number. A run edited
   * in another tab between the failure and this click would then
   * create shifts nobody previewed -- not duplicates, which the live
   * read per opportunity prevents whatever happens, but rows that
   * reached Amplify unreviewed.
   *
   * @returns {Promise<void>} When the confirmation is on screen, or
   *     when there was nothing to confirm.
   */
  async retry() {
    this.state.notice = '';
    await this.read();

    if (this.state.failure !== null) {
      return;
    }

    if (this.state.preview.totals.willCreate === 0) {
      /* The rows stay. They are the record of what failed, and
       * somebody reading this notice is reading it about them. */
      this.state.notice = RETRY_NOTHING;
      this.draw();

      return;
    }

    this.confirm();
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

  /** Return the preview screen.
   *
   * @returns {Array<Node>} What it holds.
   */
  previewScreen() {
    const { preview } = this.state;
    const handlers = {
      onConfirm: () => this.confirm(),
      onBack: () => this.handlers.onBack(),
      onReread: () => this.read()
    };

    return [
      el(
        'div',
        { class: 'preview-main' },
        el(
          'div',
          { class: 'preview-head' },
          el('h1', { class: 'screen-title', text: 'Preview' }),
          /* What the run's own status says, not a fixed sentence. A
           * run that has been sent once is previewed again -- to see
           * what a second send would add, or that nothing is left --
           * and telling that reader nothing has been sent yet would
           * be telling them something untrue about the shifts they
           * are looking at. */
          this.state.run.sentAt === null
            ? el('span', {
              class: 'tag tag-outline',
              text: 'Nothing sent yet'
            })
            : el('span', {
              class: 'tag tag-accent',
              text: phrase('runStatus', this.state.run.status)
            })
        ),
        /* The line saying what is being read is for while it is
         * being read. Left up after the read failed, it would sit
         * above a failure notice claiming the thing is still
         * happening. */
        preview === null && !this.state.reading
          ? null
          : el('p', {
            class: 'muted meta preview-line',
            text: preview === null ? READING : summaryLine(preview)
          }),
        this.state.notice === ''
          ? null
          : el(
            'p',
            { class: 'preview-notice meta', role: 'status' },
            icon('info'),
            el('span', { text: this.state.notice })
          ),
        preview === null ? null : previewTable(preview),
        previewActions(this.state, handlers)
      ),
      preview === null
        ? null
        : el(
          'div',
          { class: 'preview-side' },
          checksCard(preview, this.state.run)
        )
    ];
  }

  /** Draw whichever of the two screens is the current one.
   *
   * The send replaces the preview rather than sitting beside it: what
   * would happen and what is happening are the same subject, and a
   * screen showing both would be showing one of them as history.
   *
   * @returns {void}
   */
  draw() {
    /* The dialog is appended to this element, so it has to survive a
     * redraw of everything else under it. */
    const dialog = this.element.querySelector('.scrim');
    const showing = this.state.jobId === null
      ? el('div', { class: 'preview' }, this.previewScreen())
      : sendingScreen(this.state, {
        onBack: () => this.handlers.onBack(),
        onRetry: () => this.retry(),
        onCopy: (reference) => this.copy(reference)
      });

    this.element.replaceChildren(showing);

    if (dialog !== null) {
      this.element.append(dialog);
    }
  }

  /** Stop following the job, without stopping the job.
   *
   * Called when the screen is left. The send goes on; this is the
   * page letting go of it, which is the whole of what leaving means.
   *
   * @returns {void}
   */
  release() {
    if (this.source !== undefined) {
      this.source.close();
    }
  }
}
