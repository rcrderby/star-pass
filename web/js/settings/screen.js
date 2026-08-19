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
  'What this service resolved at start up, and where its state lives.'
);

/* Said of everything above the appearance section: it is the
 * service's, and this screen only reports it. */
const READ_ONLY = 'read only';

/* Said of the appearance section, which is the one thing on this
 * screen that is not the service's. */
const THIS_BROWSER = 'this browser';

const CREDENTIALS_HEADING = 'Credentials';
const CREDENTIALS_NOTE = (
  'The Amplify credential comes from the environment this service was '
  + 'started in. Replacing one is done there and takes effect on '
  + 'restart — this screen cannot write a credential, and nothing can '
  + 'read one back. What it can do is ask Amplify whether the one this '
  + 'service is running on still works, and show the last four '
  + 'characters so two can be told apart.'
);

const CONFIGURATION_HEADING = 'Configuration';
const CONFIGURATION_NOTE = (
  'These come from the environment this service was started in. Change '
  + 'one there and restart; this screen reports what was resolved, so '
  + 'a surprising collection can be explained without reading a file.'
);

const STATE_HEADING = 'Where state lives';
const STATE_NOTE = (
  'How long what a run leaves behind is kept. Three windows rather '
  + 'than one, because "is this still worth keeping" has three '
  + 'different answers, and each is a setting rather than something '
  + 'fixed in the code.'
);

const APPEARANCE_HEADING = 'Appearance';
const APPEARANCE_NOTE = (
  'How much the page moves, and the theme control in the bar at the '
  + 'top, are remembered in this browser and nowhere else. Asking your '
  + 'operating system for reduced motion turns movement off whatever '
  + 'is chosen here.'
);
const MOTION_LABEL = 'Motion';

/* What the credential card says about itself.  The label names the
 * service it is for rather than the variable it is set in: which
 * variable that is is a fact about the deployment, and no field
 * publishes it. */
const CREDENTIAL_LABEL = 'Amplify credential';
const CREDENTIAL_NEED = (
  'Read for a preview as well as a send: the preview asks Amplify for '
  + 'each opportunity and what it already holds.'
);
const TEST_NOTE = (
  'A test makes one real call to Amplify, so it may only be asked for '
  + 'a few times a minute.'
);

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
const TOO_OFTEN = 'It has been asked for too often, and nothing was sent '
  + 'to Amplify.';
const COME_BACK = 'Try again in {seconds} seconds.';
const COME_BACK_SOON = 'Try again shortly.';

/* Where the version is shown, and what it is called. */
const VERSION_LABEL = 'Running star-pass';

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
function refusalLine(refusal) {
  const wait = refusal.retryAfter > 0
    ? COME_BACK.replace('{seconds}', String(refusal.retryAfter))
    : COME_BACK_SOON;
  const said = refusal.isTooOften
    ? `${TOO_OFTEN} ${wait}`
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
      el(
        'button',
        {
          type: 'button',
          class: state.testing
            ? 'btn btn-secondary settings-test settings-checking'
            : 'btn btn-secondary settings-test',
          disabled: state.testing,
          onclick: onTest
        },
        icon(state.testing ? 'circle-notch' : 'plugs-connected'),
        state.testing ? TESTING : TEST
      )
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
    state.refusal === null ? null : refusalLine(state.refusal)
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
      refusal: null
    };

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
    this.draw();

    try {
      this.state.credential = await testCredential();
    } catch (error) {
      this.state.refusal = this.asApiError(error);
      this.state.credential = null;
    } finally {
      this.state.testing = false;
      this.draw();
    }
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
        el('span', { class: 'muted meta', text: LEDE })
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
      el(
        'p',
        { class: 'settings-version muted micro' },
        `${VERSION_LABEL} `,
        el('span', { class: 'mono', text: this.state.version })
      )
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
