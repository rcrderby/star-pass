/* Starting the page.
 *
 * Read what was remembered about the theme, read the wordings, ask the
 * service what runs it holds, and draw whichever screen that answer
 * calls for.  Nothing is drawn before the answer arrives: a page that
 * showed the empty state and then replaced it would be telling
 * somebody they have no runs while it finds out.
 */

import { ApiError, listRuns } from './api.js';
import { fill } from './dom.js';
import { loadPhrases } from './phrases.js';
import { emptyState, failureState, runList } from './screens.js';
import { shell } from './shell.js';
import { Appearance } from './theme.js';

/* What the collect drawer and the settings screen do until they
 * exist. Said out loud rather than left as a dead button, because a
 * control that does nothing at all reads as a bug. */
const NOT_YET = 'That screen is not built yet.';

/** Draw the page.
 *
 * @returns {Promise<void>} When it is on screen.
 */
async function start() {
  const appearance = new Appearance();
  const root = document.getElementById('app');
  const main = document.createElement('main');

  main.className = 'main';
  fill(root, shell(appearance, () => alert(NOT_YET)), main);

  try {
    await loadPhrases();

    const runs = await listRuns();

    fill(
      main,
      runs.length === 0 ? emptyState(() => alert(NOT_YET)) : runList(runs)
    );
  } catch (error) {
    /* Anything that is not the service refusing is this page being
     * broken, and is worth the log as well as the screen. */
    if (!(error instanceof ApiError)) {
      console.error(error);
    }

    fill(main, failureState(
      error instanceof ApiError
        ? error
        : new ApiError({ status: 0, detail: String(error.message || error) })
    ));
  }
}

start();
