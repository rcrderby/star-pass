/* The two screens that are not a reading of one run.
 *
 * The empty state, which is a specified screen, and what a page that
 * could not reach the service says instead of it -- a frontend that
 * reached nothing and drew the empty state would be telling somebody
 * they have no runs when what happened is that nobody could be asked.
 */

import { el, icon } from './dom.js';

/* The three things collecting does, in the order somebody does them.
 * Copy from the design handoff, which is the specification for it. */
const STEPS = [
  [
    'number-circle-one',
    'Choose a calendar and a date range, and start a run.'
  ],
  [
    'number-circle-two',
    'The application reads event data and prepares shifts.'
  ],
  [
    'number-circle-three',
    'Review the shifts, make edits, and send them to Amplify.'
  ]
];

/* What the page says when the read it starts with did not answer.
 * The default, because listing the runs is what every visit begins
 * with. */
const NO_RUNS = 'This page could not load your runs';

const LEDE = (
  'A run is data collected from events in the League Calendar '
  + 'converted to volunteer shifts that you can review and send to '
  + 'Amplify.'
);

/** Return the screen shown when no run has been collected yet.
 *
 * @param {Function} onCollect What the button does.
 * @returns {HTMLElement} The screen.
 */
export function emptyState(onCollect) {
  return el(
    'div',
    { class: 'empty' },
    el(
      'div',
      { class: 'empty-inner' },
      icon('calendar-plus'),
      el('h1', { text: 'No runs yet' }),
      el('p', { class: 'empty-lede muted meta', text: LEDE }),
      el(
        'div',
        { class: 'steps card elev-sm' },
        STEPS.map(([glyph, words]) => el(
          'span',
          { class: 'step' },
          icon(glyph),
          el('span', { class: 'muted', text: words })
        ))
      ),
      el(
        'button',
        {
          type: 'button',
          class: 'btn btn-primary self-start',
          onclick: onCollect
        },
        icon('download-simple'),
        'Start a new run'
      )
    )
  );
}

/** Return what a page that could not read what it is made of says.
 *
 * The reference is shown whenever there is one, and is the only thing
 * worth showing at 500 and above: the reason is in the service's log
 * under it, deliberately not in the answer.
 *
 * The heading is the caller's, because what could not be read is: a
 * page that could not list the runs and a settings screen that could
 * not read the settings are the same shape and not the same sentence.
 *
 * A caller that can ask again passes what asking again does, and gets
 * a control for it. Without one this screen is the end of the road:
 * a page whose first read failed has nothing else on it, so the only
 * way on was a reload.
 *
 * @param {ApiError} error What went wrong.
 * @param {string} [heading] What could not be read.
 * @param {Function} [onRetry] What asking again does, when the caller
 *     can ask again.
 * @returns {HTMLElement} The screen.
 */
export function failureState(error, heading = NO_RUNS, onRetry = null) {
  return el(
    'section',
    { class: 'failure', role: 'alert' },
    el('h2', { text: heading }),
    el('p', { class: 'meta', text: error.detail }),
    error.reference
      ? el(
        'p',
        { class: 'failure-reference muted' },
        'Reference ',
        el('span', { class: 'mono', text: error.reference })
      )
      : null,
    onRetry === null
      ? null
      : el(
        'button',
        {
          type: 'button',
          class: 'btn btn-primary self-start',
          onclick: onRetry
        },
        icon('arrow-clockwise'),
        'Try again'
      )
  );
}
