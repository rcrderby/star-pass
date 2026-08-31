/* Where the page is, said as a path (D28).
 *
 * Every screen was drawn into one `<main>` and none of them had an
 * address: a reload came back to whatever `listRuns()` implied, Back
 * left the application, and the two screens over one run could not be
 * told apart from outside the page.
 *
 * The History API rather than a fragment, so the path reaches the
 * service and the frontend can answer it with the page.  What the
 * frontend answers that way is **enumerated**, and the list below is
 * the page's half of it: `tests/test_web_routes.py` holds the two
 * together, because a path this table routes and the service refuses
 * is a screen that works until somebody reloads it.
 *
 * A route names a screen and, where it has one, the run it is over.
 * Nothing else is carried: the search text, the filters and which day
 * groups are collapsed are how a screen is being read rather than
 * which screen it is, and a path that carried them would be one a
 * person cannot type.
 */

// Imports - Local
import { remember, restore } from './scroll.js';

/* What each route is called, so that nothing matches on a spelling.
 */
export const HOME = 'home';
export const RUNS = 'runs';
export const RUN = 'run';
export const RUN_UNCOLLECTED = 'runUncollected';
export const RUN_PREVIEW = 'runPreview';
export const SETTINGS = 'settings';

/* The screens that have an address.
 *
 * Ordered from the most specific: '/runs/{runId}' matches
 * '/runs/1/preview' if it is asked first, because a run identifier is
 * matched as a segment and the tail would be thrown away rather than
 * refused.
 *
 * A job has no address of its own. A run being worked on opens on the
 * work, so the job is reached at the run's own path and stays
 * reachable across a reload, which is what an address is for here.
 */
export const ROUTES = [
  { name: HOME, path: '/' },
  { name: RUNS, path: '/runs' },
  { name: RUN_UNCOLLECTED, path: '/runs/{runId}/uncollected' },
  { name: RUN_PREVIEW, path: '/runs/{runId}/preview' },
  { name: RUN, path: '/runs/{runId}' },
  { name: SETTINGS, path: '/settings' }
];

/* One segment, which is what a run identifier is. Anything with a
 * slash in it is a different path rather than a run with an odd
 * name. */
const SEGMENT = '([^/]+)';

/* The placeholder in the table above, wherever it appears. */
const PLACEHOLDER = /\{[^}]+\}/gu;

/** Return the pattern a route matches paths with.
 *
 * @param {string} path The route's path, with its placeholder.
 * @returns {RegExp} What it matches.
 */
function pattern(path) {
  return new RegExp(`^${path.replace(PLACEHOLDER, SEGMENT)}$`, 'u');
}

/** Return a path with nothing on it that changes what it means.
 *
 * A trailing slash and an empty path are the same screen as the path
 * without one; the root is left alone, being nothing but the slash.
 *
 * @param {string} path What the address bar holds.
 * @returns {string} The path to match on.
 */
function tidied(path) {
  if (path === '' || path === '/') {
    return '/';
  }

  return path.endsWith('/') ? path.slice(0, -1) : path;
}

/** Return the screen a path names, and the run it is over.
 *
 * @param {string} path What the address bar holds.
 * @returns {Object|null} The route and its run, or null when the path
 *     names no screen.
 */
export function match(path) {
  const asked = tidied(path);

  for (const route of ROUTES) {
    const found = pattern(route.path).exec(asked);

    if (found !== null) {
      return { name: route.name, runId: found[1] || '' };
    }
  }

  return null;
}

/** Return the path for a screen.
 *
 * @param {string} name Which screen, from the names above.
 * @param {string} [runId] The run it is over, where it has one.
 * @returns {string} The path.
 */
export function pathFor(name, runId = '') {
  const route = ROUTES.find((each) => each.name === name);

  if (route === undefined) {
    throw new Error(`No route named ${name}`);
  }

  return route.path.replace(PLACEHOLDER, runId);
}

/** The address, and what it draws.
 *
 * Held here rather than in the screens: a screen that pushed its own
 * address would be a screen that has to know it was reached by Back,
 * and the same drawing has to answer both.
 */
export class Router {
  /** Start routing.
   *
   * @param {Function} onRoute What draws a route. Given the match, or
   *     null when the path names no screen.
   */
  constructor(onRoute) {
    this.onRoute = onRoute;

    /* Which address the page is showing, so that leaving it can be
     * told from redrawing it.  Read from here rather than from
     * 'location' when a place is put away, because by the time a
     * press is being drawn the address has already moved. */
    this.at = tidied(window.location.pathname);

    /* Back and Forward are the same drawing as a press, and the
     * address has already moved by the time this runs -- so it reads
     * the address rather than what it was given. */
    window.addEventListener('popstate', () => this.draw());
  }

  /** Draw whatever the address currently names.
   *
   * Where the reader was is put away against the address being left
   * and asked for again against the one being entered, both here
   * because this is the one place a press, Back and a redraw all
   * pass through, kept under the names the addresses give them.
   *
   * A redraw of the address already showing keeps its place: the
   * retry on a failed screen draws again, and starting the reader at
   * the top of what they were already reading would be the change,
   * not the fix.
   *
   * @returns {void}
   */
  draw() {
    const entering = tidied(window.location.pathname);
    const moving = entering !== this.at;

    if (moving) {
      remember(this.at);
    }

    this.at = entering;
    this.onRoute(match(window.location.pathname));

    if (moving) {
      restore(entering);
    }
  }

  /** Go to a path, adding it to the history.
   *
   * A press that lands somewhere is a place to come back to, so it is
   * pushed. Going to where the page already is draws again without
   * adding an entry nobody asked for: Back would otherwise return to
   * the screen it was pressed on.
   *
   * @param {string} path Where to go.
   * @returns {void}
   */
  go(path) {
    if (tidied(path) === tidied(window.location.pathname)) {
      this.draw();

      return;
    }

    window.history.pushState(null, '', path);
    this.draw();
  }

  /** Say where the page is without adding to the history.
   *
   * For an address that follows what was drawn rather than causing
   * it: opening the newest run at the root, or a collection naming
   * the run it started. Pushing those would put a screen nobody chose
   * behind the Back button.
   *
   * @param {string} path Where the page turned out to be.
   * @returns {void}
   */
  say(path) {
    window.history.replaceState(null, '', path);
  }
}
