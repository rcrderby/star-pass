/* Settings: what this service is running on, and what it will not do.
 *
 * Read only.  **There is no way to write a credential**, so nothing
 * here asks for one; rotation is changing the secret and restarting,
 * which this screen says out loud.
 *
 * **No credential is read when the screen opens.**  A test is a real
 * request to Amplify or the League Calendar, rate-limited for that
 * reason, so each card says it has not been checked until it has been
 * and the last four characters arrive with the answer.
 *
 * **The motion setting lives here**, in three levels, with the theme
 * control in the top bar as the other half of the same choice.  Both
 * are kept in this browser and nowhere else.
 *
 * One call in flight at a time for each credential, the answer is what
 * the screen redraws from, and a refused call is a line beside what it was about.  The
 * read this screen is made of is the exception: there is nothing else
 * to look at when it fails.
 */

import {
  ApiError,
  getConfig,
  getVersion,
  testCalendarCredential,
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
  'Service and state configuration'
);

/* Said of everything above the appearance section: it is the
 * service's, and this screen only reports it. */
const READ_ONLY = 'read only';

/* Said of the appearance section, which is the one thing on this
 * screen that is not the service's. */
const THIS_BROWSER = 'this browser';

const CREDENTIALS_HEADING = 'Credentials';
const CREDENTIALS_NOTE = (
  'This application loads Amplify and League Calendar credentials from '
  + 'environment variables during startup. Credential changes require '
  + 'an application restart.'
);

const CONFIGURATION_HEADING = 'Configuration';
const CONFIGURATION_NOTE = (
  'This application loads these values from environment variables '
  + 'during startup. Configuration changes require an application '
  + 'restart.'
);

const STATE_HEADING = 'State Configuration';
const STATE_NOTE = 'Retention periods for run data';

const APPEARANCE_HEADING = 'Appearance';
const APPEARANCE_NOTE = (
  'Motion and theme settings for this browser. Operating system '
  + 'settings override browser settings.'
);
const MOTION_LABEL = 'Motion';

/* What each credential card says about itself, and the call that
 * tests it.  The label names the service it is for rather than the
 * variable it is set in: which variable that is is a fact about the
 * deployment, and no field publishes it. */
const CREDENTIALS = [
  {
    key: 'amplify',
    label: 'Amplify Credential',
    need: 'Click the Test button to make a live call to Amplify.',
    test: testCredential
  },
  {
    key: 'calendar',
    label: 'League Calendar Credential',
    need: (
      'Click the Test button to make a live call to the League '
      + 'Calendar.'
    ),
    test: testCalendarCredential
  }
];

/* How each calendar is named under the League Calendar card. */
const CALENDAR_LABEL = '{calendar} calendar';

/* How often each credential may be tested, from the service's
 * configuration. */
const TEST_NOTE = 'Allows {attempts} {tests} per {window}.';

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

/* Said only where there is no number to count down from.  When there
 * is one, the wait is on the button instead: a sentence and a control
 * counting the same seconds down together are two things to read, and
 * the one worth watching is the one that becomes usable. */
const COME_BACK_SOON = 'Try again shortly.';

/* What the button says while it is waiting, in place of 'Test'. */
const COME_BACK = 'Try again in {seconds}s';

/* Where the version is shown, and what it is called. */
const VERSION_LABEL = 'Running star-pass';

/** Return what a credential's card holds before it has been tested.
 *
 * @returns {Object} No answer, nothing in the air, nothing refused.
 */
function untested() {
  return {
    answer: null,
    testing: false,
    refusal: null,
    /* When the service will take another test, as a timestamp.
     * Zero when nothing is waiting. */
    waitUntil: 0
  };
}

/** Return how many whole seconds the caller still has to wait.
 *
 * Worked out from a deadline each time it is asked rather than
 * decremented on a tick: a background tab has its timers throttled,
 * and a counter that lost ticks would still be counting down when the
 * service had long since stopped refusing.
 *
 * @param {Object} test One credential's test, as its card shows it.
 * @returns {number} Seconds left, and never below zero.
 */
function secondsLeft(test) {
  if (test.waitUntil === 0) {
    return 0;
  }

  return Math.max(0, Math.ceil((test.waitUntil - Date.now()) / 1000));
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

/** Return the words and icon for an answer that came back.
 *
 * @param {boolean} working Whether it worked.
 * @returns {Object} The words and the icon beside them.
 */
function answeredStatus(working) {
  return working
    ? { words: WORKING, glyph: 'check-circle', alert: false }
    : { words: NOT_WORKING, glyph: 'warning-circle', alert: true };
}

/** Return what the card says the credential is.
 *
 * @param {Object} test One credential's test, as its card shows it.
 * @returns {Object} The words and the icon beside them.
 */
function credentialStatus(test) {
  if (test.testing) {
    return { words: CHECKING, glyph: 'circle-notch', alert: false };
  }

  if (test.answer === null) {
    return { words: UNCHECKED, glyph: 'circle-dashed', alert: false };
  }

  return answeredStatus(test.answer.working);
}

/** Return what a status line is drawn as.
 *
 * @param {Object} status What the line says.
 * @param {boolean} [checking] Whether a test is in the air.
 * @returns {string} Its classes.
 */
function statusClass(status, checking = false) {
  const classes = ['settings-status', 'note'];

  if (status.alert) {
    classes.push('settings-status-alert');
  }

  if (checking) {
    classes.push('settings-checking');
  }

  return classes.join(' ');
}

/** Return a status line: an icon and the words beside it.
 *
 * @param {Object} status What the line says.
 * @param {boolean} [checking] Whether a test is in the air.
 * @returns {HTMLElement} The line.
 */
function statusLine(status, checking = false) {
  return el(
    'span',
    { class: statusClass(status, checking), role: 'status' },
    icon(status.glyph),
    el('span', { text: status.words })
  );
}

/** Return the line naming the last four characters, where there are
 * any to name.
 *
 * Absent until a test has answered, because the four characters are
 * part of that answer and nothing else publishes them.
 *
 * @param {Object} test One credential's test, as its card shows it.
 * @returns {HTMLElement|null} The line, or nothing to show yet.
 */
function maskedValue(test) {
  if (test.answer === null || !test.answer.lastFour) {
    return null;
  }

  return el('span', {
    class: 'mono muted meta settings-masked',
    text: `${MASK} ends ${test.answer.lastFour}`
  });
}

/** Return why nothing was asked of the service a credential is for.
 *
 * Asked too often is shown as the service worded it, which states the
 * limit.  Every other refusal follows the sentence saying the
 * credential could not be tested.
 *
 * @param {ApiError} refusal What came back instead of an answer.
 * @param {boolean} waiting Whether the button is counting down.
 * @returns {HTMLElement} The line.
 */
function refusalLine(refusal, waiting) {
  /* A refusal with seconds on it has them on the button, which is
   * counting them down.  One without still has to say that waiting is
   * what to do about it. */
  const said = refusal.isTooOften
    ? `${refusal.detail}${waiting ? '' : ` ${COME_BACK_SOON}`}`
    : `${REFUSED} ${refusal.detail}`;

  return el(
    'p',
    { class: 'settings-reason note', role: 'alert' },
    el('span', { text: said }),
    refusal.reference
      ? el(
        'span',
        { class: 'muted micro failure-reference' },
        'Reference ID ',
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
 * @param {Object} test One credential's test, as its card shows it.
 * @param {Function} onTest What pressing it does.
 * @returns {HTMLElement} The button.
 */
function testButton(test, onTest) {
  const waiting = secondsLeft(test);
  const classes = ['btn', 'btn-secondary', 'settings-test'];

  if (test.testing) {
    classes.push('settings-checking');
  }

  if (test.testing) {
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

/** Return what each calendar answered, under the League Calendar card.
 *
 * Absent until a test has answered, and for a credential whose answer
 * has no calendars in it.
 *
 * @param {Object} test One credential's test, as its card shows it.
 * @returns {HTMLElement|null} The list, or nothing to show.
 */
function calendarList(test) {
  if (test.answer === null || !test.answer.calendars?.length) {
    return null;
  }

  return el(
    'ul',
    { class: 'settings-calendars' },
    test.answer.calendars.map((access) => el(
      'li',
      { class: 'settings-calendar' },
      el(
        'div',
        { class: 'settings-credential-line' },
        el('span', {
          class: 'settings-credential-label',
          text: CALENDAR_LABEL.replace('{calendar}', access.calendar)
        }),
        statusLine(answeredStatus(access.working))
      ),
      access.reason === null
        ? null
        : el('p', {
          class: 'settings-reason note',
          role: 'alert',
          text: access.reason
        })
    ))
  );
}

/** Return a rate limit's window, worded to follow "per".
 *
 * @param {number} seconds The window's length.
 * @returns {string} Such as 'minute' or '30 seconds'.
 */
function perWindow(seconds) {
  if (seconds === 60) {
    return 'minute';
  }

  if (seconds % 60 === 0) {
    return `${seconds / 60} minutes`;
  }

  return `${seconds} seconds`;
}

/** Return how often each credential may be tested.
 *
 * @param {Object|null} limit The service's 'credentialTestLimit'.
 * @returns {string|null} The note, or nothing when there is no limit.
 */
function testNote(limit) {
  if (!limit) {
    return null;
  }

  return TEST_NOTE
    .replace('{attempts}', String(limit.attempts))
    .replace('{tests}', limit.attempts === 1 ? 'test' : 'tests')
    .replace('{window}', perWindow(limit.windowSeconds));
}

/** Return one credential's card.
 *
 * @param {Object} credential Which credential, from 'CREDENTIALS'.
 * @param {Object} test Its test, as the card shows it.
 * @param {string|null} note How often it may be tested.
 * @param {Function} onTest What the button does.
 * @returns {HTMLElement} The card.
 */
function credentialCard(credential, test, note, onTest) {
  return el(
    'div',
    { class: 'card elev-sm settings-credential' },
    el(
      'div',
      { class: 'settings-credential-line' },
      el('span', {
        class: 'settings-credential-label',
        text: credential.label
      }),
      maskedValue(test),
      statusLine(credentialStatus(test), test.testing),
      testButton(test, onTest)
    ),
    el('span', { class: 'muted note', text: credential.need }),
    note === null ? null : el('span', { class: 'muted micro', text: note }),
    /* Why the service would not take it, which is an answer rather
     * than a failure and is written for a person. */
    test.answer === null || test.answer.reason === null
      ? null
      : el('p', {
        class: 'settings-reason note',
        role: 'alert',
        text: test.answer.reason
      }),
    calendarList(test),
    /* Nothing reached the service at all: too many attempts, or this
     * service could not answer. A 4xx carries the reason, and at 500
     * and above only the reference is real. */
    test.refusal === null
      ? null
      : refusalLine(test.refusal, secondsLeft(test) > 0)
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
      /* Each credential's test, by its key in 'CREDENTIALS'. */
      tests: Object.fromEntries(
        CREDENTIALS.map((credential) => [credential.key, untested()])
      )
    };

    /* The tick that redraws the countdowns, and nothing while there is
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

  /** Ask the service a credential is for whether it works.
   *
   * The answer replaces whatever the card said before it, including
   * the reason a previous attempt gave: a card showing this answer
   * beside the last one's complaint would be showing two.
   *
   * @param {Object} credential Which credential, from 'CREDENTIALS'.
   * @returns {Promise<void>} When the card says what it found.
   */
  async test(credential) {
    const test = this.state.tests[credential.key];

    test.testing = true;
    test.refusal = null;
    test.waitUntil = 0;
    this.draw();

    try {
      test.answer = await credential.test();
    } catch (error) {
      const refusal = this.asApiError(error);

      test.refusal = refusal;
      test.answer = null;

      if (refusal.isTooOften && refusal.retryAfter > 0) {
        test.waitUntil = Date.now() + (refusal.retryAfter * 1000);
        this.startTicking();
      }
    } finally {
      test.testing = false;
      this.draw();
    }
  }

  /** Redraw once a second until no card has anything left to wait for.
   *
   * @returns {void}
   */
  startTicking() {
    if (this.ticking !== null) {
      return;
    }

    this.ticking = setInterval(
      () => {
        const tests = Object.values(this.state.tests);

        /* The refusal goes with the wait it was counting: it said
         * the test had been asked for too often, which stops being
         * true at this tick.  The card goes back to saying the
         * credential has not been checked.
         *
         * Only ever the too-often refusal: nothing else sets a
         * deadline, and the button is disabled for its whole
         * length. */
        tests
          .filter((test) => test.waitUntil !== 0 && secondsLeft(test) === 0)
          .forEach((test) => {
            test.refusal = null;
            test.waitUntil = 0;
          });

        /* The last tick is the one that puts the buttons back, so the
         * timer is let go of before the draw rather than after: a
         * draw that threw would otherwise leave it running against a
         * screen nothing is redrawing. */
        if (tests.every((test) => test.waitUntil === 0)) {
          this.stopTicking();
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
        CREDENTIALS.map((credential) => credentialCard(
          credential,
          this.state.tests[credential.key],
          testNote(config.credentialTestLimit),
          () => this.test(credential)
        ))
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
