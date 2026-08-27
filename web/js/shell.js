/* The bar across the top of every screen.
 *
 * The brand, where you are, the theme control and the way into
 * Settings.  It is drawn once and redrawn only when the theme changes,
 * which is what the three buttons need to show which one is chosen.
 */

import { el, icon, plainClick } from './dom.js';
import { AUTO, DAY, NIGHT } from './theme.js';

/* What each theme button is: its value, its icon, the word beside it
 * where there is one, and what a screen reader is told.  A table
 * rather than three near-identical builders, because the difference
 * between them is data. */
const THEME_BUTTONS = [
  { choice: AUTO, glyph: 'circle-half-tilt', word: 'Auto', label: 'Match the system theme' },
  { choice: DAY, glyph: 'sun', word: '', label: 'Day' },
  { choice: NIGHT, glyph: 'moon', word: '', label: 'Night' }
];

/** Return the theme control.
 *
 * `aria-pressed` says which is chosen, rather than a class the
 * stylesheet reads: it is the same fact, and stated this way the
 * control is understood by something that cannot see it.
 *
 * @param {Appearance} appearance The page's theme setting.
 * @returns {HTMLElement} The segmented control.
 */
function themeControl(appearance) {
  return el(
    'div',
    { class: 'seg', role: 'group', 'aria-label': 'Theme' },
    THEME_BUTTONS.map(({ choice, glyph, word, label }) => el(
      'button',
      {
        type: 'button',
        class: 'seg-opt',
        'aria-pressed': String(appearance.choice === choice),
        'aria-label': word ? null : label,
        title: label,
        onclick: () => appearance.choose(choice)
      },
      icon(glyph),
      word || null
    ))
  );
}

/** Return the top bar, and keep its theme control current.
 *
 * @param {Appearance} appearance The page's theme setting.
 * @param {Object} handlers Where the bar leads.
 * @param {Function} handlers.onSettings What opening Settings does.
 * @param {string} handlers.homePath The address of the runs list,
 *     which is home. Real, so the brand can be opened in a tab and
 *     read by the browser as somewhere to go.
 * @param {Function} handlers.onHome What going home does in the page.
 * @returns {HTMLElement} The bar.
 */
export function shell(appearance, { onSettings, homePath, onHome }) {
  const bar = el(
    'header',
    { class: 'nav' },
    el(
      'a',
      {
        class: 'nav-brand',
        href: homePath,
        title: 'The runs list',
        onclick: (event) => {
          if (!plainClick(event)) {
            return;
          }

          event.preventDefault();
          onHome();
        }
      },
      icon('asterisk'),
      'Star Pass',
      el('span', { class: 'nav-brand-where muted', text: '/ Create Shifts' })
    ),
    themeControl(appearance),
    el(
      'button',
      {
        type: 'button',
        class: 'btn btn-secondary btn-icon',
        'aria-label': 'Settings',
        title: 'Settings',
        onclick: onSettings
      },
      icon('gear')
    )
  );

  /* Redrawn on a change rather than each button toggling itself,
   * because Auto changing with the system is a change nothing on this
   * page clicked. */
  appearance.onChange(() => {
    bar.replaceChild(themeControl(appearance), bar.children[1]);
  });

  return bar;
}
