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

/** Return the banners this run wants, in order.
 *
 * @param {Object} state What the screen is showing.
 * @param {Object} handlers What the filters do.
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

  if (run.sentAt) {
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
