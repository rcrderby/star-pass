/* Settings: what this service is running on, and what it will not do.
 *
 * Read only, and that is the screen rather than a limitation of it.
 * **There is no way to write a credential** (D8): an endpoint able to
 * overwrite the service's own production credential would be the
 * highest-value target in the system for the least benefit, so none
 * exists and nothing here asks for one.  Rotation is changing the
 * secret and restarting, which this screen says out loud -- a screen
 * that showed a credential and offered nothing to do about it would
 * read as one whose button had been forgotten.
 *
 * **The credential is not read when the screen opens.**  The only
 * thing published about it is what a test answered, and a test is a
 * real request to Amplify, rate-limited for that reason.  A screen
 * that tested on open would spend somebody else's service on every
 * visit and hand a reader four characters they did not ask about.  So
 * the card says it has not been checked until it has been, and the
 * last four characters arrive with the answer.
 *
 * **The motion setting lives here.**  There are three levels, the
 * theme control in the bar at the top is the other half of the same
 * choice, and both are kept in this browser and nowhere else -- there
 * is no account to hang them on and the service stores nothing about
 * whoever is looking.
 *
 * The rules the other screens established hold: one call in flight at
 * a time, the answer is what the screen redraws from, and a refused
 * call is a line beside what it was about rather than a screen-wide
 * failure. The exception is the read this screen is made of -- there
 * is nothing else to look at when it fails, so that one is the whole
 * screen.
 */

import {
  ApiError,
  getConfig,
  getVersion,
  testCredential
} from '../api.js';
import { el, fill, icon } from '../dom.js';
import { failureState } from '../screens.js';
import { resolvedSettings, stateRows } from './configuration.js';

/* The three levels the page moves at, in the order they escalate. */
const MOTIONS = [
  { key: 'off', word: 'Off' },
  { key: 'subtle', word: 'Subtle' },
  { key: 'smooth', word: 'Smooth' }
];

/* What is said when the screen itself could not be read. */
const UNREADABLE = 'These settings could not be read';

/* The heading and the line under it. */
const TITLE = 'Settings';
const LEDE = (
  'Service configuration at startup and state configuration.'
);

/* Said of everything above the appearance section: it is the
 * service's, and this screen only reports it. */
const READ_ONLY = 'read only';

/* Said of the appearance section, which is the one thing on this
 * screen that is not the service's. */
const THIS_BROWSER = 'this browser';

const CREDENTIALS_HEADING = 'Credentials';
const CREDENTIALS_NOTE = (
  'The Amplify credential comes from the environment configuration at '
  + 'startup. Credential changes take effect after restarting the '
  + 'application services.'
);

const CONFIGURATION_HEADING = 'Configuration';
const CONFIGURATION_NOTE = (
  'These values come from the environment configuration at startup. '
  + 'Configuration changes take effect after restarting the '
  + 'application services.'
);

const STATE_HEADING = 'State configuration';
const STATE_NOTE = 'Retention periods for data collected for runs.';

const APPEARANCE_HEADING = 'Appearance';
const APPEARANCE_NOTE = (
  'Motion and theme settings for this browser. Operating system '
  + 'settings override browser settings.'
);
const MOTION_LABEL = 'Motion';

/* What the credential card says about itself.  The label names the
 * service it is for rather than the variable it is set in: which
 * variable that is is a fact about the deployment, and no field
 * publishes it. */
const CREDENTIAL_LABEL = 'Amplify credential';
const CREDENTIAL_NEED = (
  'Click the Test button to make a live call to Amplify.'
);
const TEST_NOTE = 'Allows a limited number of tests per minute.';

/* What the four published characters are shown as.  Said as an ending
 * rather than printed alone, so nobody reads them as the credential. */
const MASK = '••••••••••••••••••••';

/* The three things the card can say about the credential, and the
 * fourth it says before anything has been asked. */
const UNCHECKED = 'Not checked yet';
const CHECKING = 'Checking now';
const WORKING = 'Working';
const NOT_WORKING = 'Not working';

const TEST = 'Test';
const TESTING = 'Checking';

/* Said above the reason when the test itself was refused, rather than
 * answered.  A different thing from a credential Amplify would not
 * take: nothing reached Amplify at all. */
const REFUSED = 'The credential could not be tested.';

/* And what is said instead of the reason when the refusal was for
 * asking too often.  The service's reason can only name the limit and
 * the header carrying the answer, which is a sentence for a program;
 * the answer itself arrives as a number of seconds, and this is the
 * screen that has it. */
const TOO_OFTEN = 'It has been requested too often, and nothing was sent '
  + 'to Amplify.';

/* Said only where there is no number to count down from.  When there
 * is one, the wait is on the button instead: a sentence and a control
 * counting the same seconds down together are two things to read, and
 * the one worth watching is the one that becomes usable. */
const COME_BACK_SOON = 'Try again shortly.';

/* What the button says while it is waiting, in place of 'Test'. */
const COME_BACK = 'Try again in {seconds}s';

/* Where the version is shown, and what it is called. */
const VERSION_LABEL = 'Running star-pass';

/** Return how many whole seconds the caller still has to wait.
 *
 * Worked out from a deadline each time it is asked rather than
 * decremented on a tick: a background tab has its timers throttled,
 * and a counter that lost ticks would still be counting down when the
 * service had long since stopped refusing.
 *
 * @param {Object} state What the screen is showing.
 * @returns {number} Seconds left, and never below zero.
 */
function secondsLeft(state) {
  if (state.waitUntil === 0) {
    return 0;
  }

  return Math.max(0, Math.ceil((state.waitUntil - Date.now()) / 1000));
}

/** Return one section of the screen.
 *
 * @param {Object} options What it is.
 * @param {string} options.heading What it is called.
 * @param {string} [options.tag] The pill beside the heading.
 * @param {string} options.note The line under the heading.
 * @param {...(Node|Array|null)} contents What it holds.
 * @returns {HTMLElement} The section.
 */
function section({ heading, tag = '', note }, ...contents) {
  return el(
    'section',
    { class: 'settings-section' },
    el(
      'div',
      { class: 'settings-head' },
      el('h2', { text: heading }),
      tag ? el('span', { class: 'tag tag-neutral', text: tag }) : null
    ),
    el('p', { class: 'settings-note muted meta', text: note }),
    contents
  );
}

/** Return what the card says the credential is.
 *
 * @param {Object} state What the screen is showing.
 * @returns {Object} The words and the icon beside them.
 */
function credentialStatus(state) {
  if (state.testing) {
    return { words: CHECKING, glyph: 'circle-notch', alert: false };
  }

  if (state.credential === null) {
    return { words: UNCHECKED, glyph: 'circle-dashed', alert: false };
  }

  if (state.credential.working) {
    return { words: WORKING, glyph: 'check-circle', alert: false };
  }

  return { words: NOT_WORKING, glyph: 'warning-circle', alert: true };
}

/** Return what the status line is drawn as.
 *
 * @param {Object} state What the screen is showing.
 * @param {Object} status What the line says.
 * @returns {string} Its classes.
 */
function statusClass(state, status) {
  const classes = ['settings-status', 'note'];

  if (status.alert) {
    classes.push('settings-status-alert');
  }

  if (state.testing) {
    classes.push('settings-checking');
  }

  return classes.join(' ');
}

/** Return the line naming the last four characters, where there are
 * any to name.
 *
 * Absent until a test has answered, because the four characters are
 * part of that answer and nothing else publishes them.
 *
 * @param {Object} state What the screen is showing.
 * @returns {HTMLElement|null} The line, or nothing to show yet.
 */
function maskedValue(state) {
  if (state.credential === null || !state.credential.lastFour) {
    return null;
  }

  return el('span', {
    class: 'mono muted meta settings-masked',
    text: `${MASK} ends ${state.credential.lastFour}`
  });
}

/** Return why nothing was asked of Amplify.
 *
 * Asked too often is the one refusal this screen words itself: what a
 * reader can do about it is wait, the answer arrived as a number of
 * seconds, and the reason can only point at the header carrying it.
 * Every other refusal is shown as the service worded it.
 *
 * @param {ApiError} refusal What came back instead of an answer.
 * @returns {HTMLElement} The line.
 */
function refusalLine(refusal, waiting) {
  /* A refusal with seconds on it has them on the button, which is
   * counting them down.  One without still has to say that waiting is
   * what to do about it. */
  const said = refusal.isTooOften
    ? `${TOO_OFTEN}${waiting ? '' : ` ${COME_BACK_SOON}`}`
    : refusal.detail;

  return el(
    'p',
    { class: 'settings-reason note', role: 'alert' },
    el('span', { text: `${REFUSED} ${said}` }),
    refusal.reference
      ? el(
        'span',
        { class: 'muted micro failure-reference' },
        'Reference ',
        el('span', { class: 'mono', text: refusal.reference })
      )
      : null
  );
}

/** Return the button that asks, and says why it cannot be pressed.
 *
 * Disabled while a test is in the air and again while the service is
 * still refusing, because a control that can be pressed to be told
 * "not yet" is one that teaches a reader to press it and wait.
 *
 * @param {Object} state What the screen is showing.
 * @param {Function} onTest What pressing it does.
 * @returns {HTMLElement} The button.
 */
function testButton(state, onTest) {
  const waiting = secondsLeft(state);
  const classes = ['btn', 'btn-secondary', 'settings-test'];

  if (state.testing) {
    classes.push('settings-checking');
  }

  if (state.testing) {
    return el(
      'button',
      {
        type: 'button',
        class: classes.join(' '),
        disabled: true,
        onclick: onTest
      },
      icon('circle-notch'),
      TESTING
    );
  }

  if (waiting > 0) {
    return el(
      'button',
      {
        type: 'button',
        class: classes.join(' '),
        disabled: true,
        onclick: onTest
      },
      icon('clock'),
      COME_BACK.replace('{seconds}', String(waiting))
    );
  }

  return el(
    'button',
    {
      type: 'button',
      class: classes.join(' '),
      disabled: false,
      onclick: onTest
    },
    icon('plugs-connected'),
    TEST
  );
}

/** Return the credential card.
 *
 * @param {Object} state What the screen is showing.
 * @param {Function} onTest What the button does.
 * @returns {HTMLElement} The card.
 */
function credentialCard(state, onTest) {
  const status = credentialStatus(state);

  return el(
    'div',
    { class: 'card elev-sm settings-credential' },
    el(
      'div',
      { class: 'settings-credential-line' },
      el('span', { class: 'settings-credential-label', text: CREDENTIAL_LABEL }),
      maskedValue(state),
      el(
        'span',
        { class: statusClass(state, status), role: 'status' },
        icon(status.glyph),
        el('span', { text: status.words })
      ),
      testButton(state, onTest)
    ),
    el('span', { class: 'muted note', text: CREDENTIAL_NEED }),
    el('span', { class: 'muted micro', text: TEST_NOTE }),
    /* Why Amplify would not take it, which is an answer rather than a
     * failure and is written for a person. */
    state.credential === null || state.credential.reason === null
      ? null
      : el('p', {
        class: 'settings-reason note',
        role: 'alert',
        text: state.credential.reason
      }),
    /* Nothing reached Amplify at all: too many attempts, or the
     * service could not answer. A 4xx carries the reason, and at 500
     * and above only the reference is real. */
    state.refusal === null
      ? null
      : refusalLine(state.refusal, secondsLeft(state) > 0)
  );
}

/** Return the control that sets how much the page moves.
 *
 * @param {Appearance} appearance The page's settings.
 * @param {Function} onChoose What choosing one does.
 * @returns {HTMLElement} The row.
 */
function motionControl(appearance, onChoose) {
  return el(
    'div',
    { class: 'settings-motion' },
    el('span', { class: 'settings-motion-label', text: MOTION_LABEL }),
    el(
      'div',
      { class: 'seg', role: 'group', 'aria-label': MOTION_LABEL },
      MOTIONS.map((motion) => el(
        'button',
        {
          type: 'button',
          class: 'seg-opt',
          'aria-pressed': String(appearance.motion === motion.key),
          onclick: () => onChoose(motion.key)
        },
        motion.word
      ))
    )
  );
}

/**
 * What the service was configured with, and what it will not do.
 */
export class SettingsScreen {
  /** Prepare the screen, and read what it is made of.
   *
   * @param {Object} what What it is drawn from.
   * @param {Appearance} what.appearance The page's theme and motion.
   * @param {Object} handlers Where the screen's exits go.
   * @param {Function} handlers.onBack Return to what was showing.
   */
  constructor({ appearance }, handlers) {
    this.appearance = appearance;
    this.handlers = handlers;

    this.state = {
      config: null,
      version: '',
      failure: null,
      credential: null,
      testing: false,
      refusal: null,
      /* When the service will take another test, as a timestamp.
       * Zero when nothing is waiting. */
      waitUntil: 0
    };

    /* The tick that redraws the countdown, and nothing while there is
     * no countdown to redraw. */
    this.ticking = null;

    this.element = el('div', { class: 'screen settings' });
    this.draw();
    this.read();
  }

  /** Read the settings and the version, and draw them.
   *
   * Asked for together rather than one after another: neither is
   * worth a screen of its own, and two sequential reads would draw a
   * screen assembled from two moments.
   *
   * @returns {Promise<void>} When it is on screen.
   */
  async read() {
    try {
      const [config, version] = await Promise.all([
        getConfig(),
        getVersion()
      ]);

      this.state.config = config;
      this.state.version = version.version;
    } catch (error) {
      this.state.failure = this.asApiError(error);
    }

    this.draw();
  }

  /** Return an error as a screen can show one.
   *
   * @param {Error} error What went wrong.
   * @returns {ApiError} The failure, shaped for a screen.
   */
  asApiError(error) {
    if (error instanceof ApiError) {
      return error;
    }

    console.error(error);

    return new ApiError({
      status: 0,
      detail: String(error.message || error)
    });
  }

  /** Ask Amplify whether the credential works.
   *
   * The answer replaces whatever the card said before it, including
   * the reason a previous attempt gave: a card showing this answer
   * beside the last one's complaint would be showing two.
   *
   * @returns {Promise<void>} When the card says what it found.
   */
  async test() {
    this.state.testing = true;
    this.state.refusal = null;
    this.stopTicking();
    this.state.waitUntil = 0;
    this.draw();

    try {
      this.state.credential = await testCredential();
    } catch (error) {
      const refusal = this.asApiError(error);

      this.state.refusal = refusal;
      this.state.credential = null;

      if (refusal.isTooOften && refusal.retryAfter > 0) {
        this.state.waitUntil = Date.now() + (refusal.retryAfter * 1000);
        this.startTicking();
      }
    } finally {
      this.state.testing = false;
      this.draw();
    }
  }

  /** Redraw once a second until there is nothing left to wait for.
   *
   * @returns {void}
   */
  startTicking() {
    this.stopTicking();

    this.ticking = setInterval(
      () => {
        /* The last tick is the one that puts the button back, so the
         * timer is let go of before the draw rather than after: a
         * draw that threw would otherwise leave it running against a
         * screen nothing is redrawing. */
        if (secondsLeft(this.state) === 0) {
          this.stopTicking();

          /* And the refusal goes with the wait it was counting. What
           * it said was that the test had been asked for too often,
           * which stopped being true at this tick; leaving it up
           * would append "Try again shortly" at the moment trying
           * again became possible, which is advice about a state
           * that has just ended. The card goes back to saying the
           * credential has not been checked, which is what happened.
           *
           * Only ever the too-often refusal: nothing else sets a
           * deadline, and the button is disabled for its whole
           * length, so no other refusal can arrive while it runs. */
          this.state.refusal = null;
          this.state.waitUntil = 0;
        }

        this.draw();
      },
      1000
    );
  }

  /** Let go of the tick.
   *
   * @returns {void}
   */
  stopTicking() {
    if (this.ticking !== null) {
      clearInterval(this.ticking);
      this.ticking = null;
    }
  }

  /** Let go of anything still running when the screen goes.
   *
   * Called by the shell as it puts another screen on.  Without it a
   * countdown left behind would go on redrawing an element no longer
   * in the page, once a second, for as long as the tab is open.
   *
   * @returns {void}
   */
  release() {
    this.stopTicking();
  }

  /** Set how much the page moves, and show which is chosen.
   *
   * @param {string} motion One of the three levels.
   * @returns {void}
   */
  moveBy(motion) {
    this.appearance.moveBy(motion);
    this.draw();
  }

  /** Return the head, which is on screen before anything is read.
   *
   * @returns {HTMLElement} The heading, its line, and the way back.
   */
  head() {
    return el(
      'div',
      { class: 'settings-top' },
      el(
        'button',
        {
          type: 'button',
          class: 'btn btn-secondary btn-icon',
          'aria-label': 'Back',
          title: 'Back',
          onclick: () => this.handlers.onBack()
        },
        icon('arrow-left')
      ),
      el(
        'div',
        {},
        el('h1', { class: 'screen-title', text: TITLE }),
        el('span', { class: 'muted meta', text: LEDE }),

        /* Under the lede rather than at the foot of the page.  This
         * is the screen somebody opens to ask what the deployment is,
         * and the version is the shortest answer to it -- read once,
         * from a standing start, by somebody who will not scroll to
         * the bottom of a settings page to find it.
         *
         * Drawn only once there is one: the head is on screen before
         * the read that fetches it lands, and 'draw' refills the head
         * as well as the body, so an empty line here would be a line
         * of nothing until it arrives. */
        this.state.version === ''
          ? null
          : el(
            'span',
            { class: 'settings-version muted micro' },
            `${VERSION_LABEL} `,
            el('span', { class: 'mono', text: this.state.version })
          )
      )
    );
  }

  /** Return the sections, once there is something to draw them from.
   *
   * @returns {Array<Node>} What the screen holds.
   */
  sections() {
    const { config } = this.state;

    return [
      section(
        {
          heading: CREDENTIALS_HEADING,
          tag: READ_ONLY,
          note: CREDENTIALS_NOTE
        },
        credentialCard(this.state, () => this.test())
      ),
      section(
        {
          heading: CONFIGURATION_HEADING,
          tag: READ_ONLY,
          note: CONFIGURATION_NOTE
        },
        resolvedSettings(config)
      ),
      section(
        { heading: STATE_HEADING, tag: READ_ONLY, note: STATE_NOTE },
        stateRows(config.retention)
      ),
      section(
        {
          heading: APPEARANCE_HEADING,
          tag: THIS_BROWSER,
          note: APPEARANCE_NOTE
        },
        motionControl(this.appearance, (motion) => this.moveBy(motion))
      ),
    ];
  }

  /** Return what goes under the head: the sections, the failure that
   * replaced them, or nothing while the read is in the air.
   *
   * @returns {Array<Node>|Node|null} The body.
   */
  body() {
    if (this.state.failure !== null) {
      return failureState(this.state.failure, UNREADABLE);
    }

    if (this.state.config === null) {
      return null;
    }

    return this.sections();
  }

  /** Draw the screen.
   *
   * @returns {void}
   */
  draw() {
    fill(this.element, this.head(), this.body());
  }
}
