/* Starting the page.
 *
 * Read what was remembered about the theme, read the wordings, ask the
 * service what runs it holds, and draw whichever screen that answer
 * calls for.  Nothing is drawn before the answer arrives: a page that
 * showed the empty state and then replaced it would be telling
 * somebody they have no runs while it finds out.
 */

import { ApiError, getConfig, getRun, listRevisions, listRuns }
  from './api.js';
import { fill } from './dom.js';
import { loadPhrases } from './phrases.js';
import { emptyState, failureState } from './screens.js';
import { ReviewScreen } from './review/screen.js';
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

  /** Draw one run, reading everything the screen needs.
   *
   * @param {Array<Object>} runs Every run the service holds.
   * @param {string} runId Which one to open.
   * @returns {Promise<void>} When it is on screen.
   */
  async function openRun(runs, runId) {
    /* Asked for together rather than one after another: three
     * sequential reads would draw a screen assembled from three
     * different moments, and the run is the slowest of them. */
    const [run, revisions, config] = await Promise.all([
      getRun(runId),
      listRevisions(runId),
      getConfig()
    ]);

    fill(main, new ReviewScreen(
      { runs, run, revisions, config },
      { onOpenRun: (chosen) => openRun(runs, chosen).catch(failed) }
    ).element);
  }

  /** Put a failure on screen in place of whatever was being drawn.
   *
   * @param {Error} error What went wrong.
   * @returns {void}
   */
  function failed(error) {
    if (!(error instanceof ApiError)) {
      console.error(error);
    }

    fill(main, failureState(
      error instanceof ApiError
        ? error
        : new ApiError({ status: 0, detail: String(error.message || error) })
    ));
  }

  try {
    await loadPhrases();

    const runs = await listRuns();

    if (runs.length === 0) {
      fill(main, emptyState(() => alert(NOT_YET)));

      return;
    }

    await openRun(runs, runs[0].id);
  } catch (error) {
    failed(error);
  }
}

start();
