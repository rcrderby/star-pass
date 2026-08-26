/* A send as it happens, and as it is picked back up.
 *
 * **Leaving is allowed, and that shapes everything here.**  The send
 * runs in the service, not in this page: the request answers with a
 * job as soon as one exists, and the job goes on whether or not
 * anybody is watching.  So nothing on this screen is remembered
 * between frames that could not be rebuilt from the job's own event
 * log, which a browser opening the stream fresh is given from the
 * first frame.  Close the tab, come back, and the same screen is
 * drawn from the same events.
 *
 * That is why the total comes from `sending_started` rather than from
 * the preview.  A reload has no preview, and reading one during a
 * send would be asking Amplify about the opportunities the send is
 * writing to.
 *
 * A row reaches this screen twice: once by identity, when the send
 * says which opportunity it is reading, and once with its result.
 * Rows the send has not reached yet are drawn from the preview when
 * there is one, so somebody who stayed sees the whole list waiting
 * rather than an empty screen filling up -- and a reattaching browser
 * sees what has happened plus a count of what has not.
 */

import { el, icon } from '../dom.js';
import { counted } from '../format.js';

/* Where a row can be. `waiting` is the absence of news about it,
 * which is why a reattached screen can show one without ever having
 * been told anything. */
const WAITING = 'waiting';
const SENDING = 'sending';
const DONE = 'done';
const FAILED = 'failed';
const UNKNOWN = 'unknown';

/* What each state is called and drawn as. `done` says how many rows
 * arrived rather than the word, because that is the answer somebody
 * is watching for.
 *
 * `unknown` is the one an interrupted send leaves, and it is **not**
 * `failed`: a failure is Amplify refusing, which the service saw and
 * recorded, while an interruption is the service stopping with a
 * request in the air. The batch may have arrived or may not have, and
 * the only thing that knows is Amplify -- which is what the next send
 * asks. Drawing it as failed would be this page making a claim the
 * service does not. */
const STATES = {
  [WAITING]: { words: 'Waiting', glyph: 'circle-dashed' },
  [SENDING]: { words: 'Sending', glyph: 'circle-notch' },
  [DONE]: { words: '', glyph: 'check-circle' },
  [FAILED]: { words: 'Failed', glyph: 'warning-circle' },
  [UNKNOWN]: { words: 'Unknown', glyph: 'info' }
};

/* Said while it runs, under the heading. */
const RUNNING = (
  'One request per opportunity. Leaving this page will not stop it, '
  + 'and the run remembers what is left.'
);

/* Said beside the buttons while it runs, because the buttons are
 * never disabled and somebody has to be told that is deliberate. */
const LEAVING_IS_SAFE = (
  'Leaving is safe. The send keeps going and this page picks it back '
  + 'up.'
);

/* Said under the rows when the screen knows there are more
 * opportunities than it has rows for. A browser that joined a send in
 * progress learns an opportunity's identity from the send working on
 * it, so the ones not reached yet have no row -- and a send that
 * stopped at a failure never reached the rest at all. The count is
 * the total either way, so the difference is stated rather than left
 * as a bar that does not match the list. */
const NOT_REACHED = (
  '{n} of the {total} opportunities are not listed above: the send '
  + 'had not reached them.'
);

/* What a retry says while it is reading the preview again. Its own
 * line because that read is a request per opportunity and takes
 * seconds: without it, the button does nothing visible and then a
 * dialog appears. */
const RECHECKING = 'Checking Amplify before sending again';

/* And when that read could not be made. The retry stops here rather
 * than sending a number nobody could work out.  What stopped it is
 * the service's own sentence, for the reason the preview screen
 * states beside its own lead. */
const RECHECK_FAILED = (
  'The check for shifts that already exist could not be made, so '
  + 'sending again is held back.'
);

/* When the connection dropped. Not a failure of the send: the browser
 * reconnects on its own and is given what it missed. */
const RECONNECTING = (
  'Lost touch with the service for a moment. Reconnecting; the send '
  + 'itself is unaffected.'
);

/* What an interrupted send says, in place of the outcome. The
 * unfinished opportunity is the whole of the uncertainty: everything
 * before it was recorded and everything after it was never reached. */
const INTERRUPTED_LEDE = (
  'The service stopped while this send was running. The opportunity it '
  + 'was working on may or may not have been created — Amplify is what '
  + 'knows, and resuming asks it. Every opportunity is read again '
  + 'immediately before it is written to, so resuming creates only '
  + 'what is missing and nothing can arrive twice.'
);

/* On the button that asks for it. */
const RESUME = 'Resume the send';

/** Return what the heading says.
 *
 * @param {Object} state What the screen is showing.
 * @returns {string} The heading.
 */
export function heading(state) {
  if (state.running) {
    return 'Sending to Amplify';
  }

  if (state.interrupted) {
    return 'Send interrupted';
  }

  return state.rows.some((row) => row.state === FAILED)
    ? 'Partly sent'
    : 'Everything sent';
}

/** Return what the pill beside the heading says.
 *
 * @param {Object} state What the screen is showing.
 * @returns {string} The pill.
 */
export function statusText(state) {
  if (state.running) {
    return 'Sending';
  }

  if (state.interrupted) {
    return 'Interrupted';
  }

  const done = state.rows.filter((row) => row.state === DONE).length;

  return done === state.total && state.total > 0
    ? 'Sent'
    : `${done} of ${state.total} sent`;
}

/** Return the sentence under the heading once it is over.
 *
 * @param {Object} state What the screen is showing.
 * @returns {string} What happened.
 */
export function outcomeText(state) {
  if (state.interrupted) {
    return INTERRUPTED_LEDE;
  }

  const failed = state.rows.filter((row) => row.state === FAILED).length;
  const created = state.rows.reduce(
    (total, row) => total + row.created,
    0
  );

  if (failed === 0) {
    return `${counted(created, 'shift')} created. Amplify has every `
      + 'shift this run asked for.';
  }

  return `${counted(created, 'shift')} created. `
    + `${counted(failed, 'opportunity', 'opportunities')} failed and `
    + 'created nothing. Sending again covers only what is missing, so '
    + 'nothing can be created twice.';
}

/** Return the progress bar and the count beside it.
 *
 * The width goes through a custom property rather than an inline
 * style: the Content Security Policy is `default-src 'self'` with no
 * `unsafe-inline`, so setting a `style` attribute is refused by the
 * browser. Setting one property on `element.style` is not.
 *
 * @param {Object} state What the screen is showing.
 * @returns {HTMLElement} The bar.
 */
export function progressBar(state) {
  const done = state.rows.filter(
    (row) => row.state === DONE || row.state === FAILED
  ).length;
  const fill = el('div', { class: 'progress-fill' });
  const share = state.total === 0 ? 0 : Math.round((done / state.total) * 100);

  fill.style.setProperty('--progress', `${share}%`);

  return el(
    'div',
    { class: 'progress' },
    el(
      'div',
      {
        class: 'progress-track',
        role: 'progressbar',
        'aria-valuenow': String(done),
        'aria-valuemin': '0',
        'aria-valuemax': String(state.total),
        'aria-label': 'Opportunities sent'
      },
      fill
    ),
    el('span', {
      class: 'progress-count mono muted micro',
      text: `${done} of ${counted(state.total, 'opportunity', 'opportunities')}`
    })
  );
}

/** Return one opportunity's row.
 *
 * The reference on a failed row is the **job's** identifier. That is
 * what connects what somebody saw to what the service logged: a job
 * that failed for a reason not written for a caller records a fixed
 * sentence and puts the reason in the log against this identifier.
 *
 * @param {Object} row One opportunity's progress.
 * @param {string} jobId The job doing the send.
 * @param {Function} onCopy What copying the reference does.
 * @param {string} copied Which reference was just copied.
 * @returns {HTMLElement} The row.
 */
function sendRow(row, jobId, onCopy, copied) {
  const shown = STATES[row.state];
  const words = row.state === DONE
    ? `${counted(row.created, 'shift')} created`
    : shown.words;

  return el(
    'div',
    { class: `row-card send-row send-row-${row.state}` },
    icon(shown.glyph),
    el(
      'span',
      { class: 'send-row-main' },
      el('span', { class: 'send-row-title', text: row.title }),
      row.skipped === 0
        ? null
        : el('span', {
          class: 'muted note',
          text: `${row.skipped} already in Amplify, skipped`
        }),
      row.detail === ''
        ? null
        : el(
          'span',
          { class: 'send-row-error note' },
          el('span', { text: row.detail }),
          el(
            'button',
            {
              type: 'button',
              class: 'btn btn-ghost micro',
              onclick: () => onCopy(jobId)
            },
            icon('copy'),
            copied === jobId ? 'Copied' : jobId
          )
        )
    ),
    el('span', { class: 'send-row-status meta', text: words })
  );
}

/** Return what a retry has to say before it opens the confirmation.
 *
 * The three things the preview screen says about the same read, said
 * here because a retry makes that read from this screen: it is
 * happening, it could not be made, or it found nothing left to do.
 * Without them the button reads as broken -- nothing moves for
 * several seconds, and a read that failed moves nothing at all.
 *
 * @param {Object} state What the screen is showing.
 * @returns {Array<HTMLElement|null>} What to show, if anything.
 */
function retryStatus(state) {
  return [
    state.reading
      ? el(
        'p',
        { class: 'sending-checking muted meta', role: 'status' },
        icon('circle-notch'),
        el('span', { text: RECHECKING })
      )
      : null,
    state.failure === null
      ? null
      : el(
        'p',
        { class: 'sending-failed meta', role: 'alert' },
        icon('warning-circle'),
        el(
          'span',
          { class: 'failed-words' },
          el('span', {
            text: `${RECHECK_FAILED} ${state.failure.detail}`
          }),
          state.failure.reference
            ? el(
              'span',
              { class: 'muted micro failure-reference' },
              'Reference ',
              el('span', { class: 'mono', text: state.failure.reference })
            )
            : null
        )
      ),
    state.notice === ''
      ? null
      : el(
        'p',
        { class: 'sending-notice meta', role: 'status' },
        icon('info'),
        el('span', { text: state.notice })
      )
  ];
}

/** Return the whole sending screen.
 *
 * @param {Object} state What the screen is showing.
 * @param {Object} handlers What its controls do.
 * @returns {HTMLElement} The screen.
 */
export function sendingScreen(state, handlers) {
  const failed = state.rows.filter((row) => row.state === FAILED).length;

  /* Offered only once the send has stopped. While one is running the
   * question has an answer on the way, and a button asking to start
   * it again would be asking for a second worker. */
  const resumable = state.interrupted && !state.running;

  return el(
    'div',
    { class: 'sending' },
    el(
      'div',
      { class: 'sending-head' },
      el('h1', { class: 'screen-title', text: heading(state) }),
      el('span', {
        class: state.running || failed ? 'tag tag-alert' : 'tag tag-accent',
        text: statusText(state)
      })
    ),
    el('p', {
      class: 'muted meta sending-subline',
      text: state.running ? RUNNING : outcomeText(state)
    }),
    state.lost
      ? el(
        'p',
        { class: 'sending-lost meta', role: 'status' },
        icon('warning-circle'),
        el('span', { text: RECONNECTING })
      )
      : null,
    progressBar(state),
    el(
      'div',
      { class: 'send-rows' },
      state.rows.map(
        (row) => sendRow(row, state.jobId, handlers.onCopy, state.copied)
      )
    ),
    state.rows.length >= state.total
      ? null
      : el('p', {
        class: 'muted note sending-unreached',
        text: NOT_REACHED
          .replace('{n}', String(state.total - state.rows.length))
          .replace('{total}', String(state.total))
      }),
    retryStatus(state),
    el(
      'div',
      { class: 'sending-actions' },
      /* One button, whichever way this send stopped. A run cannot be
       * both interrupted and holding a refusal: an interruption is
       * the job's own ending, so the frames that would have said an
       * opportunity failed were never written. */
      failed === 0 && !resumable
        ? null
        : el(
          'button',
          {
            type: 'button',
            class: 'btn btn-primary',
            /* Not disabled while the send runs: walking away and
             * coming back is the point, and a control unavailable for
             * minutes reads as one that is broken. Disabled only
             * while this button's own read is out, because a second
             * click would start a second one. */
            disabled: state.reading,
            onclick: handlers.onRetry
          },
          icon('arrows-clockwise'),
          resumable ? RESUME : `Retry the ${failed} that failed`
        ),
      el(
        'button',
        {
          type: 'button',
          class: 'btn btn-secondary',
          onclick: handlers.onBack
        },
        'Back to the run'
      ),
      state.running
        ? el('span', { class: 'muted meta', text: LEAVING_IS_SAFE })
        : null
    )
  );
}

export { WAITING, SENDING, DONE, FAILED, UNKNOWN };
