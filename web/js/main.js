/* Starting the page, and which screen it is on.
 *
 * Read what was remembered about the theme, read the wordings, and
 * draw whatever the address names.  Nothing is drawn before the
 * answers arrive: a page that showed the empty state and then
 * replaced it would be telling somebody they have no runs while it
 * finds out.
 *
 * **The address decides the screen (D28).**  Every screen with a path
 * is reached by going to that path and drawing what it names, whether
 * somebody pressed a control, pressed Back, reloaded, or typed the
 * address in a new tab.  One drawing for all four is what makes the
 * last three work at all: a control that showed a screen itself would
 * be a screen no address could reach.
 *
 * Moving between screens re-reads the run rather than keeping what
 * was read before.  A send changes the run -- its status, when its
 * shifts reached Amplify -- and coming back to a copy from before it
 * would be coming back to a run that had not been sent.  Moving
 * between the two **tabs** of one run does not: they are one screen
 * with two addresses, and re-reading would throw away the search, the
 * filters and the selection somebody is in the middle of using.
 *
 * **A run that is being worked on opens on the work.**  A run carries
 * the job still working on it, which is what makes one somebody
 * walked away from reattachable: opening it goes to the screen for
 * that job rather than to a review screen with no sign anything is
 * happening.  A job has no address of its own -- it is what the run's
 * own path draws while there is one.
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
import {
  HOME,
  RUN,
  RUN_PREVIEW,
  RUN_UNCOLLECTED,
  RUNS,
  Router,
  SETTINGS,
  pathFor
} from './router.js';
import { RunsScreen } from './runs/screen.js';
import { failureState } from './screens.js';
import {
  ReviewScreen,
  SHIFTS_VIEW,
  UNCOLLECTED_VIEW
} from './review/screen.js';
import { SEND_JOB, SendingScreen } from './sending/screen.js';
import { SettingsScreen } from './settings/screen.js';
import { shell } from './shell.js';
import { Appearance } from './theme.js';

/* Which tab each of a run's two addresses draws. */
const VIEW_OF = {
  [RUN]: SHIFTS_VIEW,
  [RUN_UNCOLLECTED]: UNCOLLECTED_VIEW
};

/** Draw the page.
 *
 * @returns {Promise<void>} When it is on screen.
 */
async function start() {
  const appearance = new Appearance();
  const root = document.getElementById('app');
  const main = document.createElement('main');

  main.className = 'main';
  fill(root, shell(appearance, {
    onSettings: () => router.go(pathFor(SETTINGS)),
    homePath: pathFor(RUNS),
    onHome: () => router.go(pathFor(RUNS))
  }), main);

  /* The screen currently drawn, so that leaving one lets go of
   * whatever it was holding open. Only the sending screen has
   * anything: a job's event stream, which the service keeps open. */
  let showing = null;

  /* Which run the screen on the page is over. Read to know that a
   * route is the same run seen a different way, so that switching tab
   * keeps the screen rather than reading the run again. Empty while
   * the screen is over no run. */
  let opened = '';

  /* The address Settings was reached from, so that leaving it comes
   * back to the screen it was opened over rather than to the run's
   * first tab. Settings belongs to no run and is reached from the bar
   * above every screen, so what it goes back to is where the reader
   * was, which is now a thing a path can say. Home until somebody has
   * been anywhere, which is what a page opened straight on '/settings'
   * gets. */
  let cameFrom = pathFor(RUNS);

  /** Put a screen on, letting go of the one before it.
   *
   * @param {Object} screen The screen to show.
   * @param {string} [runId] The run it is over, where it is over one.
   * @returns {void}
   */
  function show(screen, runId = '') {
    if (showing !== null && showing.release !== undefined) {
      showing.release();
    }

    showing = screen;
    opened = runId;
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

    showing = null;

    fill(main, failureState(
      error instanceof ApiError
        ? error
        : new ApiError({ status: 0, detail: String(error.message || error) })
    ));
  }

  /** Return the job working on a run, when one is.
   *
   * **Only a job still in hand.** A run whose last job the service
   * stopped in the middle of names it too, and that one is a banner
   * on the review screen rather than a screen to open on: an
   * interrupted job stays interrupted until somebody acts on it, so a
   * run that opened on one would be a run whose way back came
   * straight here again. A job still running finishes and stops being
   * the run's, which is what makes opening on it safe.
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

  /** Show the job the service stopped in the middle of (D10).
   *
   * Whichever screen that job's kind belongs to, which is the same
   * screen it would have been watched on: how far a send got is a
   * reading of what it reported, and so is how far a collection got.
   * The resume lives there, behind the send confirmation.
   *
   * Drawn where it stands rather than pushed as an address: the run's
   * path is where the interrupted job is, and a reload finds it again
   * from the banner it was reached by.
   *
   * @param {Object} run The run, which names the job.
   * @param {Object} config What the deployment was configured with.
   * @returns {Promise<void>} When it is on screen.
   */
  async function seeInterrupted(run, config) {
    try {
      const job = await getJob(run.interruptedJobId);

      if (job.kind === SEND_JOB) {
        show(
          new SendingScreen(
            { run, job },
            { onBack: () => router.go(pathFor(RUN, run.id)) }
          ),
          run.id
        );

        return;
      }

      watchCollection(job, config, run.calendar);
    } catch (error) {
      failed(error);
    }
  }

  /** Show a collection, and open the run when it finishes.
   *
   * The address becomes the run's as soon as the job names it, so a
   * reload in the middle of a collection comes back to the run being
   * collected -- which draws this screen again, the run carrying the
   * job. Said rather than pushed: nobody pressed anything to arrive
   * here, so there is nothing to go back to.
   *
   * @param {Object} job The job doing it.
   * @param {Object} config What the deployment was configured with.
   * @param {string} [calendar] Which calendar it reads, when known.
   * @returns {void}
   */
  function watchCollection(job, config, calendar = '') {
    router.say(pathFor(RUN, job.runId));

    show(
      new CollectingScreen(
        { job, config, calendar },
        {
          onOpenRun: (runId) => router.go(pathFor(RUN, runId)),
          onLeave: () => router.go(pathFor(RUNS))
        }
      ),
      job.runId
    );
  }

  /** Open the drawer over whatever is on screen.
   *
   * **A recollection reads the run first, by identifier.** What the
   * drawer says a recollection would discard, and the number it sends
   * to prove it, both come from the run's change log -- so a run
   * captured when the screen was drawn describes the run as it was
   * before every edit and revert made since.  The service refuses
   * that number, correctly, and the operator is told to read the run
   * again by a screen with no way to do it.
   *
   * Read here rather than at the moment of sending, which would defeat
   * the guard: 'expectedChangeCount' exists so that what is discarded
   * is what somebody was shown and agreed to, and a number gathered
   * as the request left would always agree with itself.
   *
   * @param {Object} config What the deployment was configured with.
   * @param {string} [runId] The run being replaced, for a
   *     recollection.
   * @returns {Promise<void>} When the drawer is on screen.
   */
  async function collect(config, runId = '') {
    let run = null;

    if (runId !== '') {
      try {
        run = await getRun(runId);
      } catch (error) {
        failed(error);

        return;
      }
    }

    const drawer = new CollectDrawer(
      { config, run },
      {
        onCollect: (asked) => (
          run === null
            ? collectRun(asked.calendar, asked.window)
            : recollectRun(run.id, asked.expectedChangeCount)
        ),
        onReread: () => getRun(runId),
        onStarted: (job, calendar) => watchCollection(job, config, calendar)
      }
    );

    drawer.open(root);
  }

  /** Draw one run, reading everything the screen needs.
   *
   * @param {Array<Object>} runs Every run the service holds.
   * @param {string} runId Which one to open.
   * @param {string} name Which of the run's addresses was asked for.
   * @returns {Promise<void>} When it is on screen.
   */
  async function openRun(runs, runId, name) {
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
      show(
        new SendingScreen(
          { run, job },
          { onBack: () => router.go(pathFor(RUN, runId)) }
        ),
        runId
      );

      return;
    }

    if (job !== null && COLLECT_JOBS.includes(job.kind)) {
      watchCollection(job, config, run.calendar);

      return;
    }

    if (name === RUN_PREVIEW) {
      show(
        new SendingScreen(
          { run },
          { onBack: () => router.go(pathFor(RUN, runId)) }
        ),
        runId
      );

      return;
    }

    show(
      new ReviewScreen(
        { runs, run, revisions, config, view: VIEW_OF[name] },
        {
          onOpenRun: (chosen) => router.go(pathFor(RUN, chosen)),
          onView: (view) => router.go(pathFor(
            view === UNCOLLECTED_VIEW ? RUN_UNCOLLECTED : RUN,
            runId
          )),
          onSeeInterrupted: () => seeInterrupted(run, config),
          onCollectNew: () => collect(config),
          onCollectAgain: () => collect(config, run.id),
          onPreview: () => router.go(pathFor(RUN_PREVIEW, runId))
        }
      ),
      runId
    );
  }

  /** Draw the runs list.
   *
   * Home, and the one screen that is a reading of every run rather
   * than of one. The empty state is drawn inside it rather than in
   * place of it: a page with no runs is still on the runs list, and
   * the address should say so.
   *
   * @param {Array<Object>} runs Every run the service holds.
   * @param {boolean} [missing] Whether an address named a run the
   *     service does not hold.
   * @returns {Promise<void>} When it is on screen.
   */
  async function showList(runs, missing = false) {
    /* Read here rather than inside the drawer: the drawer is opened
     * from three places and a screen that fetched on open would be
     * one that appears empty and then fills in. */
    const config = await getConfig();

    show(new RunsScreen(
      { runs, missing },
      {
        onOpenRun: (runId) => router.go(pathFor(RUN, runId)),
        onCollectNew: () => collect(config),
        onChanged: () => router.go(pathFor(RUNS)),
        pathForRun: (runId) => pathFor(RUN, runId)
      }
    ));
  }

  /** Draw the run a path named, or the list when it named none.
   *
   * The run list is read every time rather than kept: a send changes
   * the run's status, and both the list and the picker on the review
   * screen show that status for every run.
   *
   * An address naming a run the service does not hold is refused on
   * the list rather than answered with a different run: a bookmark to
   * a deleted run is a question, and the answer is that it is gone.
   *
   * @param {string} name Which address was asked for.
   * @param {string} [runId] The run it named, where it named one.
   * @returns {Promise<void>} When it is on screen.
   */
  async function showRuns(name, runId = '') {
    const runs = await listRuns();

    if (name === HOME) {
      await openHome(runs);

      return;
    }

    /* Every other address is over a run, and there are none. The
     * list says so, at its own address rather than at the one that
     * named a run that cannot exist -- and it refuses the run that
     * was asked for, because "there is no run with that identifier"
     * is the answer to that question whether or not there are others
     * to show underneath it. */
    if (name === RUNS || runs.length === 0) {
      if (name !== RUNS) {
        router.say(pathFor(RUNS));
      }

      await showList(runs, name !== RUNS);

      return;
    }

    if (runs.some((run) => run.id === runId)) {
      await openRun(runs, runId, name);

      return;
    }

    router.say(pathFor(RUNS));
    await showList(runs, true);
  }

  /** Draw what the root resolves to.
   *
   * The list, unless something is working on a run -- in which case
   * that run, because a run being worked on opens on the work and a
   * job somebody walked away from is the thing they came back for.
   * The newest such run, so that the answer does not depend on the
   * order two of them started in.
   *
   * @param {Array<Object>} runs Every run the service holds.
   * @returns {Promise<void>} When it is on screen.
   */
  async function openHome(runs) {
    const working = runs.find((run) => run.activeJobId !== null);

    if (working === undefined) {
      router.say(pathFor(RUNS));
      await showList(runs);

      return;
    }

    router.say(pathFor(RUN, working.id));
    await openRun(runs, working.id, RUN);
  }

  /** Show the settings, over whatever was being looked at.
   *
   * Reached from the bar above every screen, and belonging to no run,
   * so leaving it goes back to the run that was open rather than
   * anywhere in particular. Read again on the way back rather than
   * kept: a send may have finished while somebody was reading what
   * the service is configured with.
   *
   * @returns {void}
   */
  function showSettings() {
    show(new SettingsScreen(
      { appearance },
      { onBack: () => router.go(cameFrom) }
    ));
  }

  /** Draw what an address names.
   *
   * @param {Object|null} route The screen and the run it is over.
   * @returns {Promise<void>} When it is on screen.
   */
  async function draw(route) {
    if (route === null) {
      /* The service answers the page's own paths and refuses the
       * rest, so arriving here means the page pushed something its
       * own table does not know. Draw home and say so, rather than
       * leaving an address nothing can return to. */
      router.say(pathFor(RUNS));
      await showRuns(RUNS);

      return;
    }

    if (route.name === SETTINGS) {
      showSettings();

      return;
    }

    /* Every other screen is one Settings can be opened over, and the
     * address is already this one by the time this runs. */
    cameFrom = window.location.pathname;

    /* One run's two tabs are one screen. Told to change rather than
     * built again, so that Back and Forward between them keep the
     * search, the filters and the selection -- and so that the second
     * tab is read once rather than on every visit to it. */
    if (
      showing instanceof ReviewScreen
      && route.runId === opened
      && route.name in VIEW_OF
    ) {
      showing.setView(VIEW_OF[route.name]);

      return;
    }

    await showRuns(route.name, route.runId);
  }

  const router = new Router((route) => draw(route).catch(failed));

  try {
    await loadPhrases();
    router.draw();
  } catch (error) {
    failed(error);
  }
}

start();
