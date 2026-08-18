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
    'Pick a calendar and a window. The service reads the dates in '
    + 'league time.'
  ],
  [
    'number-circle-two',
    'Review what was collected, and what was set aside and why.'
  ],
  [
    'number-circle-three',
    'Preview the shifts, then send. Amplify is checked first, so '
    + 'nothing is created twice.'
  ]
];

const LEDE = (
  'A run is one collection, from one calendar, over one window of '
  + 'league dates. Collecting reads the calendar and builds a list of '
  + 'shifts for you to review — nothing reaches Amplify until you '
  + 'send it.'
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
        'Collect from Google Calendar'
      )
    )
  );
}

/** Return what a page that could not start says.
 *
 * The reference is shown whenever there is one, and is the only thing
 * worth showing at 500 and above: the reason is in the service's log
 * under it, deliberately not in the answer.
 *
 * @param {ApiError} error What went wrong.
 * @returns {HTMLElement} The screen.
 */
export function failureState(error) {
  return el(
    'section',
    { class: 'failure', role: 'alert' },
    el('h2', { text: 'This page could not load your runs' }),
    el('p', { class: 'meta', text: error.detail }),
    error.reference
      ? el(
        'p',
        { class: 'failure-reference muted' },
        'Reference ',
        el('span', { class: 'mono', text: error.reference })
      )
      : null
  );
}
