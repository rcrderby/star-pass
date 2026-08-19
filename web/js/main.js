/* Starting the page, and which screen it is on.
 *
 * Read what was remembered about the theme, read the wordings, ask the
 * service what runs it holds, and draw whichever screen that answer
 * calls for.  Nothing is drawn before the answer arrives: a page that
 * showed the empty state and then replaced it would be telling
 * somebody they have no runs while it finds out.
 *
 * There are two screens over a run now, and moving between them
 * re-reads it rather than keeping what was read before.  A send
 * changes the run -- its status, when its shifts reached Amplify --
 * and coming back to a copy from before it would be coming back to a
 * run that had not been sent.
 *
 * **A run that is being worked on opens on the work.**  A run carries
 * the job still working on it, which is what makes one somebody
 * walked away from reattachable: opening it goes to the screen for
 * that job rather than to a review screen with no sign anything is
 * happening.
 */

import {
  ApiError,
  collectRun,
  getConfig,
  getJob,
  getRun,
  listRevisions,
  listRuns,
  recollectRun
} from './api.js';
import { CollectDrawer } from './collect/drawer.js';
import { COLLECT_JOBS, CollectingScreen } from './collect/screen.js';
import { fill } from './dom.js';
import { loadPhrases } from './phrases.js';
import { emptyState, failureState } from './screens.js';
import { ReviewScreen } from './review/screen.js';
import { SEND_JOB, SendingScreen } from './sending/screen.js';
import { shell } from './shell.js';
import { Appearance } from './theme.js';

/* What the settings screen does until it exists. Said out loud rather
 * than left as a dead button, because a control that does nothing at
 * all reads as a bug. */
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

  /* The screen currently drawn, so that leaving one lets go of
   * whatever it was holding open. Only the sending screen has
   * anything: a job's event stream, which the service keeps open. */
  let showing = null;

  /** Put a screen on, letting go of the one before it.
   *
   * @param {Object} screen The screen to show.
   * @returns {void}
   */
  function show(screen) {
    if (showing !== null && showing.release !== undefined) {
      showing.release();
    }

    showing = screen;
    fill(main, screen.element);
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

  /** Return the job working on a run, when one is.
   *
   * @param {Object} run The run, which names its active job.
   * @returns {Promise<Object|null>} The job, or null.
   */
  async function activeJob(run) {
    if (run.activeJobId === null) {
      return null;
    }

    return getJob(run.activeJobId);
  }

  /** Show a collection, and open the run when it finishes.
   *
   * @param {Object} job The job doing it.
   * @param {Object} config What the deployment was configured with.
   * @param {string} [calendar] Which calendar it reads, when known.
   * @returns {void}
   */
  function watchCollection(job, config, calendar = '') {
    show(new CollectingScreen(
      { job, config, calendar },
      { onOpenRun: (runId) => reopen(runId) }
    ));
  }

  /** Open the drawer over whatever is on screen.
   *
   * @param {Object} config What the deployment was configured with.
   * @param {Object} [run] The run being replaced, for a recollection.
   * @returns {void}
   */
  function collect(config, run = null) {
    const drawer = new CollectDrawer(
      { config, run },
      {
        onCollect: (asked) => (
          run === null
            ? collectRun(asked.calendar, asked.window)
            : recollectRun(run.id, asked.expectedChangeCount)
        ),
        onStarted: (job, calendar) => watchCollection(job, config, calendar)
      }
    );

    drawer.open(root);
  }

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

    const job = await activeJob(run);

    /* A run being worked on opens on the work. Which screen that is
     * depends on what the job is doing: a send and a collection are
     * different screens over the same kind of stream. */
    if (job !== null && job.kind === SEND_JOB) {
      show(new SendingScreen(
        { run, job },
        { onBack: () => reopen(runId) }
      ));

      return;
    }

    if (job !== null && COLLECT_JOBS.includes(job.kind)) {
      watchCollection(job, config, run.calendar);

      return;
    }

    show(new ReviewScreen(
      { runs, run, revisions, config },
      {
        onOpenRun: (chosen) => openRun(runs, chosen).catch(failed),
        onCollectAgain: () => collect(config, run),
        onPreview: () => show(new SendingScreen(
          { run },
          { onBack: () => reopen(runId) }
        ))
      }
    ));
  }

  /** Read a run again and draw it.
   *
   * The run list is read again with it: a send changes the run's
   * status, and the picker on the review screen shows that status
   * for every run it lists.
   *
   * @param {string} runId Which run.
   * @returns {Promise<void>} When it is on screen.
   */
  async function reopen(runId) {
    try {
      await openRun(await listRuns(), runId);
    } catch (error) {
      failed(error);
    }
  }

  try {
    await loadPhrases();

    const runs = await listRuns();

    if (runs.length === 0) {
      /* Read here rather than inside the drawer: the drawer is opened
       * from three places and a screen that fetched on open would be
       * one that appears empty and then fills in. */
      const config = await getConfig();

      fill(main, emptyState(() => collect(config)));

      return;
    }

    await openRun(runs, runs[0].id);
  } catch (error) {
    failed(error);
  }
}

start();
