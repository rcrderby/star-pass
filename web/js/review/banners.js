/* What is worth saying about the whole run before the table says it
 * row by row.
 *
 * Stacked in a fixed order, and each is absent when it has nothing to
 * report -- a banner reading "0 events" is a banner nobody needs.
 * Two of them carry a filter, because the useful next move after
 * being told four events want a look is to see only those four.
 */

import { el, icon } from '../dom.js';

/* What each banner is drawn in. The alert one is the only thing on
 * this screen allowed the alert colour, which is what makes it read
 * as the one thing stopping the send. */
const ACCENT = 'banner banner-accent';
const SECONDARY = 'banner banner-secondary';
const ALERT = 'banner banner-alert';

/* Statuses the run publishes that each get their own banner. The
 * first two mean shifts reached Amplify. 'RUN_FAILED' is exported
 * because the table's empty line keys on it too: a run whose
 * collection failed is accounted for here, and saying it a second
 * time down there in different words reads as two problems. */
const PARTLY_SENT = 'partly_sent';
const SENT = 'sent';
export const RUN_FAILED = 'failed';

/** Return one banner.
 *
 * @param {Object} options What it says and how it looks.
 * @param {string} options.tone Which class it carries.
 * @param {string} options.glyph Icon beside the words.
 * @param {string} options.words What it says.
 * @param {HTMLElement} [options.action] A control at its right.
 * @returns {HTMLElement} The banner.
 */
function banner({ tone, glyph, words, action = null }) {
  return el(
    'div',
    { class: tone },
    icon(glyph),
    el('span', { class: 'banner-words meta', text: words }),
    action
  );
}

/** Return the toggle that narrows the table to what a banner counted.
 *
 * @param {boolean} on Whether it is showing only those.
 * @param {Function} onToggle What pressing it does.
 * @returns {HTMLElement} The toggle.
 */
function showOnlyThese(on, onToggle) {
  return el(
    'button',
    {
      type: 'button',
      class: on ? 'btn btn-primary' : 'btn btn-secondary',
      'aria-pressed': String(on),
      onclick: onToggle
    },
    icon('funnel'),
    on ? 'Showing only these' : 'Show only these'
  );
}

/** Return the control that opens the job a run was left with.
 *
 * @param {Function} onSee What pressing it does.
 * @returns {HTMLElement} The control.
 */
function seeWhatHappened(onSee) {
  return el(
    'button',
    { type: 'button', class: 'btn btn-primary', onclick: onSee },
    icon('arrow-right'),
    'See what happened'
  );
}

/** Return the banners this run wants, in order.
 *
 * @param {Object} state What the screen is showing.
 * @param {Object} handlers What the filters do.
 * @param {Function} handlers.onSeeInterrupted Open the job the
 *     service stopped in the middle of.
 * @returns {Array<HTMLElement>} The banners.
 */
export function reviewBanners(state, handlers) {
  const { run, events, filters } = state;
  const blocking = events.filter((event) => event.blocking);
  const fuzzy = events.filter(
    (event) => event.match !== null && event.match.kind === 'fuzzy'
  );
  const repeated = events.filter((event) => event.duplicateOf !== null);
  const banners = [];

  /* First, and in the alert colour, because it is the one thing here
   * that is not a fact about the run but a question left open about
   * it: a write to Amplify stopped in the middle, and how far it got
   * is not something this service knows (D10).
   *
   * A banner rather than a screen of its own to open on. An
   * interrupted job stays interrupted until somebody acts on it, so a
   * run that opened on it would be a run whose "Back to the run"
   * came straight back -- unlike a job still running, which finishes
   * and stops being the run's. */
  if (run.interruptedJobId !== null) {
    banners.push(banner({
      tone: ALERT,
      glyph: 'warning-circle',
      words: 'The service stopped while this run had work in hand. '
        + 'What it had done by then is worth looking at before '
        + 'anything else is asked of the run.',
      action: seeWhatHappened(handlers.onSeeInterrupted)
    }));
  }

  /* A run whose first collection failed holds no revision, so the
   * table below is empty and says so in the words of a search that
   * found nothing.  Without this the screen gives no account of
   * itself at all: the status is drawn in the run picker and nowhere
   * on the run.  What such a run wants is to be collected again, or
   * deleted (D31). */
  if (run.status === RUN_FAILED) {
    banners.push(banner({
      tone: ALERT,
      glyph: 'warning-circle',
      words: 'This run holds nothing: its collection stopped before it '
        + 'stored anything. Collect its window again to try once more.'
    }));
  }

  /* Keyed on the status and not on `sent_at`, which `mark_sent`
   * writes for both of the statuses that mean shifts reached Amplify.
   * A partly sent run told "This run has been sent" is a run
   * contradicting the tag one line above it, and the two states are
   * not the same news: one is a run that is done, the other a run
   * with work still in it. */
  if (run.status === PARTLY_SENT) {
    banners.push(banner({
      tone: ACCENT,
      glyph: 'circle-half-tilt',
      words: 'Part of this run reached Amplify before the send '
        + 'stopped. Sending again creates only what Amplify does not '
        + 'already have.'
    }));
  }

  if (run.status === SENT) {
    banners.push(banner({
      tone: ACCENT,
      glyph: 'check-circle',
      words: 'This run has been sent. Sending again creates only what '
        + 'Amplify does not already have.'
    }));
  }

  if (repeated.length > 0) {
    banners.push(banner({
      tone: SECONDARY,
      glyph: 'copy',
      words: `${repeated.length} of these shifts would repeat another `
        + 'row in this run. They will be created once.'
    }));
  }

  if (blocking.length > 0) {
    banners.push(banner({
      tone: ALERT,
      glyph: 'warning-circle',
      words: `${blocking.length} event`
        + `${blocking.length === 1 ? ' has' : 's have'} no opportunity `
        + 'to create a shift under, which stops the run being sent.',
      action: showOnlyThese(filters.blocking, handlers.onToggleBlocking)
    }));
  }

  if (fuzzy.length > 0) {
    banners.push(banner({
      tone: SECONDARY,
      glyph: 'magic-wand',
      words: `${fuzzy.length} event`
        + `${fuzzy.length === 1 ? ' was' : 's were'} matched by wording `
        + 'rather than a keyword',
      action: showOnlyThese(filters.fuzzy, handlers.onToggleFuzzy)
    }));
  }

  return banners;
}
