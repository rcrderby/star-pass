/* The five things a collection does, and how far it has got.
 *
 * **Five steps.**  Reading
 * the calendar and reading the Amplify opportunities are two upstream
 * services and either can fail on its own, so which of them stopped a
 * collection is exactly what this screen exists to say; and the
 * design's fourth step was "write the CSV", which describes an
 * artefact the tool stopped producing.  The order here is the order
 * the core reports them in, which is the order they happen.
 *
 * The words are `phrases.json`'s, not this module's, because the
 * contract publishes an identifier per step and every client words it
 * -- the same rule that keeps a blocker or a run's status out of the
 * answer as English.
 *
 * **A step never reports its own failure.**  `step_failed` exists on
 * the reporter and nothing in the core calls it, so there is no frame
 * that says a step went wrong.  What there is instead is the job
 * ending badly, and the step that was running when it did is the step
 * that failed -- the collection stops at the first thing that raises,
 * so there is never more than one.  That is exactly as accurate as a
 * frame would be.
 */

import { el, icon } from '../dom.js';
import { phrase } from '../phrases.js';

/* The steps a collection reports, in order. `read_opportunity` is not
 * among them: it belongs to a send, which is a different screen. */
export const COLLECT_STEPS = [
  'read_calendar',
  'filter_events',
  'match_events',
  'read_opportunities',
  'store_events'
];

/* Where a step can be. `pending` is the absence of news about it,
 * which is what every step is until the job reaches it. */
export const PENDING = 'pending';
export const RUNNING = 'running';
export const DONE = 'done';
export const FAILED = 'failed';

/* And the state a step is left in when the service stopped while it
 * was working. Not `failed`: nothing refused anything, and the step
 * neither finished nor failed -- it was in hand when the process
 * holding it went away. */
export const STOPPED = 'stopped';

/* What each state is drawn as, and what it says beside the step. The
 * running one spins, which is the design's `omSpin`. */
const STATES = {
  [PENDING]: { words: '', glyph: 'circle-dashed' },
  [RUNNING]: { words: 'Working', glyph: 'circle-notch' },
  [DONE]: { words: 'Done', glyph: 'check-circle' },
  [FAILED]: { words: 'Failed', glyph: 'warning-circle' },
  [STOPPED]: { words: 'Stopped', glyph: 'info' }
};

/** Return every step as pending.
 *
 * @returns {Array<Object>} One per step, in the order they happen.
 */
export function freshSteps() {
  return COLLECT_STEPS.map((step) => ({ step, state: PENDING }));
}

/** Return the list of steps, drawn.
 *
 * @param {Array<Object>} steps Each step and where it is.
 * @returns {HTMLElement} The list.
 */
export function stepList(steps) {
  return el(
    'div',
    { class: 'collect-steps' },
    steps.map(({ step, state }) => el(
      'div',
      { class: `row-card collect-step collect-step-${state}` },
      icon(STATES[state].glyph),
      el('span', {
        class: 'collect-step-words',
        text: phrase('step', step)
      }),
      el('span', {
        class: 'muted micro collect-step-state',
        text: STATES[state].words
      })
    ))
  );
}
