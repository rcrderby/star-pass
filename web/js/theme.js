/* Which theme the page is in, and how much it moves.
 *
 * Three choices, not two: Day, Night, and Auto, which follows the
 * operating system and keeps following it.  Auto is the default and is
 * a standing choice rather than a one-off reading -- somebody whose
 * machine turns dark at sunset gets a page that turns with it, which
 * is why the media query is listened to rather than sampled at boot.
 *
 * Both settings live in this browser and nowhere else.  There is no
 * account to hang them on and the service stores nothing about whoever
 * is looking, so `localStorage` is the whole of it.  A browser with it
 * blocked gets the defaults and no error, because a theme that could
 * not be remembered is not a reason to fail to draw a page.
 */

const THEME_KEY = 'star-pass:theme';
const MOTION_KEY = 'star-pass:motion';

export const AUTO = 'auto';
export const DAY = 'day';
export const NIGHT = 'night';

/* What Night resolves to on the root element.  Night is the default
 * theme and therefore the absence of an override, so it is spelled as
 * itself here and as nothing in the stylesheet. */
const RESOLVED = { [DAY]: 'day', [NIGHT]: 'night' };

const CHOICES = [AUTO, DAY, NIGHT];
const MOTIONS = ['off', 'subtle', 'smooth'];

const DEFAULT_MOTION = 'subtle';

/* How long the crossfade runs for.  Matched to the 300ms transition
 * the stylesheet applies while `data-theming` is set; the attribute is
 * cleared afterwards so hovering does not pay for it all day. */
const CROSSFADE_MS = 300;

const DARK_QUERY = '(prefers-color-scheme: dark)';

/** Return what was remembered, or a fallback.
 *
 * @param {string} key Where it was kept.
 * @param {Array<string>} allowed What may come back.
 * @param {string} fallback What to answer with otherwise.
 * @returns {string} The remembered value, or the fallback.
 */
function remembered(key, allowed, fallback) {
  try {
    const kept = localStorage.getItem(key);

    return allowed.includes(kept) ? kept : fallback;
  } catch {
    return fallback;
  }
}

/** Remember something, if this browser allows it.
 *
 * @param {string} key Where to keep it.
 * @param {string} value What to keep.
 * @returns {void}
 */
function remember(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* Private browsing, or storage turned off. The page works; it just
     * opens in Auto next time. */
  }
}

/**
 * The page's theme and how much it moves.
 *
 * One object because the two settings are set the same way, are kept
 * the same way, and are both written onto the same root element.
 */
export class Appearance {
  /** Read what was remembered and put it on the page.
   *
   * @param {HTMLElement} [root] What carries the attributes. The root
   *     element, so that the background behind a scrolled page is the
   *     theme's rather than the browser's.
   */
  constructor(root = document.documentElement) {
    this.root = root;
    this.choice = remembered(THEME_KEY, CHOICES, AUTO);
    this.motion = remembered(MOTION_KEY, MOTIONS, DEFAULT_MOTION);
    this.dark = matchMedia(DARK_QUERY);
    this.listeners = new Set();

    /* Auto means what the machine says now, not what it said when the
     * tab was opened. */
    this.dark.addEventListener('change', () => {
      if (this.choice === AUTO) {
        this.apply();
      }
    });

    this.apply();
  }

  /** Return which theme is actually showing.
   *
   * @returns {string} `day` or `night`, never `auto`.
   */
  get resolved() {
    if (this.choice === AUTO) {
      return this.dark.matches ? NIGHT : DAY;
    }

    return this.choice;
  }

  /** Write the current settings onto the root element.
   *
   * @returns {void}
   */
  apply() {
    this.root.dataset.theme = RESOLVED[this.resolved];
    this.root.dataset.motion = this.motion;

    for (const listener of this.listeners) {
      listener(this);
    }
  }

  /** Choose a theme, crossfading to it.
   *
   * @param {string} choice One of `auto`, `day` or `night`.
   * @returns {void}
   */
  choose(choice) {
    if (!CHOICES.includes(choice) || choice === this.choice) {
      return;
    }

    this.choice = choice;
    remember(THEME_KEY, choice);

    /* Set around the change and cleared after it, so the 300ms
     * transition applies to this and to nothing else. A reader who
     * asked for reduced motion gets the switch with no fade, which the
     * stylesheet decides rather than this. */
    this.root.dataset.theming = '1';
    this.apply();

    clearTimeout(this.crossfade);
    this.crossfade = setTimeout(() => {
      delete this.root.dataset.theming;
    }, CROSSFADE_MS);
  }

  /** Set how much the page moves.
   *
   * @param {string} motion One of `off`, `subtle` or `smooth`.
   * @returns {void}
   */
  moveBy(motion) {
    if (!MOTIONS.includes(motion)) {
      return;
    }

    this.motion = motion;
    remember(MOTION_KEY, motion);
    this.apply();
  }

  /** Be told when either setting changes.
   *
   * @param {Function} listener Called with this object.
   * @returns {void}
   */
  onChange(listener) {
    this.listeners.add(listener);
  }
}
