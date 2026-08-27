/* The way a run is asked for: a calendar, a window, and what that
 * window will and will not pick up.
 *
 * **Nothing about the window is worked out in the browser's own
 * zone.**  D16 names a preset computed in the visitor's zone as a
 * live bug in the design this replaces, so "this month" means the
 * month it is where the service is, and the zone is shown rather than
 * assumed.  `format.today` is the only place the current moment
 * becomes a day, and it is given the zone the configuration
 * publishes.
 *
 * The one conversion this screen does make is the other direction:
 * the field says "Last day" because that is how a person means a
 * window, and the request carries the day after it, because no
 * request takes an inclusive day.  The panel shows both, so what is
 * about to be asked for is on screen rather than implied.
 *
 * What the search does and does not collect is read, never written
 * here: the query strings belong to a calendar and the excluded terms
 * to the deployment, and both are published for exactly this.
 *
 * **Collecting again offers no window and no calendar.**  A run is one
 * calendar over one set of days, and `POST /runs/{id}/recollect`
 * carries neither: it reads the same calendar over the same days and
 * the run keeps its own window.  So the controls are shown holding
 * what the run already has and refused, the way the calendar control
 * already was -- a field a person can type into and a summary
 * restating what it says would both be describing a request that does
 * not exist.
 *
 * **A double-clicked button is this screen's problem.**  Collect and
 * recollect take no `Idempotency-Key`, so nothing behind this makes a
 * second arrival of the same request safe -- two would be two runs,
 * or two jobs on one run.  Every control is disabled from the moment
 * one is in the air, which is the rule the review screen already
 * keeps for a different reason.
 */

import { el, fill, icon } from '../dom.js';
import {
  dayAfter,
  longDay,
  monthWindow,
  spanDays
} from '../format.js';
import { Modal } from '../modal.js';

/* The presets, and how far ahead each one looks. `custom` is not a
 * month and is what any hand-typed date falls back to. */
const THIS_MONTH = 'this';
const NEXT_MONTH = 'next';
const CUSTOM = 'custom';

const PRESETS = [
  { key: THIS_MONTH, words: 'This month', ahead: 0 },
  { key: NEXT_MONTH, words: 'Next month', ahead: 1 },
  { key: CUSTOM, words: 'Custom', ahead: null }
];

const TITLE = 'Collect from Google Calendar';
const LEDE = 'Builds a fresh list to review. Nothing is sent to Amplify.';

/* Under the calendar control. A run is one calendar's, which is why
 * the control is a choice rather than a set of checkboxes. */
const ONE_CALENDAR = 'One calendar per collection.';

/* Said when the two dates are the wrong way round, which is the only
 * thing this screen refuses on its own -- and it refuses by
 * disabling, because there is nothing to send. */
const BACKWARDS = 'The last day cannot come before the first day.';

/* Under the resolved window. Says why the panel shows a day nobody
 * typed. */
const HOW_THE_WINDOW_IS_READ = (
  'The service reads these dates in the zone above, so a late evening '
  + 'event lands on the day you expect. The day after your last day is '
  + 'what gets sent, which is how the last day is included.'
);

/* Said instead, when the window is the run's rather than one being
 * asked for. Nothing is converted and nothing is sent, so the
 * sentence above would be explaining a request nobody is making. */
const THE_RUNS_OWN_WINDOW = (
  'Collecting again reads the same calendar over the same days, and '
  + 'the run keeps this window. A different window is a different '
  + 'run.'
);

/* Under the window control, where the calendar control has its own. */
const WINDOW_IS_FIXED = 'Set when the run was collected.';

/** Return what to call the zone note.
 *
 * The zone is the service's and is named rather than described: a
 * sentence saying "league time" tells somebody in another zone
 * nothing they can check.
 *
 * @param {string} timezone The zone the configuration reports.
 * @returns {string} The note.
 */
function zoneNote(timezone) {
  return (
    `These are league dates, read in ${timezone} — not this device's `
    + 'time zone. The service resolves them the same way the command '
    + 'line does.'
  );
}

/** Return what the window's search will and will not pick up.
 *
 * @param {Object} calendar The chosen calendar, as the configuration
 *     describes it.
 * @param {Array<string>} excluded Terms the deployment never
 *     collects.
 * @returns {Array<Array>} An icon name and a sentence, per note.
 */
function windowNotes(calendar, excluded) {
  /* An empty query string searches for nothing in particular, which
   * is how a calendar says it collects everything on it. A calendar
   * with one is not also searched for its other terms in any way a
   * reader needs to know about. */
  const searchesEverything = calendar.searchTerms.includes('');
  const terms = calendar.searchTerms
    .filter((term) => term !== '')
    .map((term) => `"${term}"`)
    .join(', ');

  return [
    [
      'funnel',
      searchesEverything || terms === ''
        ? `Every event on the ${calendar.key} calendar is collected.`
        : `Only events found by ${terms} are collected from the `
          + `${calendar.key} calendar.`
    ],
    [
      'prohibit',
      `Titles containing ${excluded.join(', ')} are never collected, `
      + 'and neither are all-day or untitled events. They are listed '
      + 'after the collection, under Not collected.'
    ]
  ];
}

/** Return the warning shown when collecting again replaces a run.
 *
 * Shown for every recollection and not only for one with edits to
 * lose. A run with nothing edited is still replaced, and its earlier
 * revisions still go; a warning that appeared only once somebody had
 * changed something would be silent on exactly the press that reads
 * most like collecting something new.
 *
 * @param {number} changes How many changes the current revision
 *     holds.
 * @returns {string} What it says.
 */
function replaceWarning(changes) {
  if (changes === 0) {
    return (
      'Collecting again replaces this run with what the calendar has '
      + 'now. The revisions before it are deleted.'
    );
  }

  return (
    'Collecting again replaces this run. '
    + `${changes} change${changes === 1 ? '' : 's'} you have made will `
    + 'be deleted, along with earlier revisions.'
  );
}

/**
 * The drawer, and the window it is being used to describe.
 */
export class CollectDrawer {
  /** Prepare to ask for a collection.
   *
   * @param {Object} what What it is being opened over.
   * @param {Object} what.config The deployment's configuration, which
   *     names the calendars and the authoritative zone.
   * @param {Object} [what.run] The run being replaced, when this is a
   *     recollection rather than a fresh one. Its calendar is the one
   *     offered and the entries against its current revision are what the warning counts.
   * @param {Object} handlers What leaving it does.
   * @param {Function} handlers.onStarted Called with the job that is
   *     doing the work, and the calendar it is reading.
   */
  constructor({ config, run = null }, handlers) {
    this.config = config;
    this.run = run;
    this.handlers = handlers;

    /* The window a recollection shows is the run's own, because that
     * is the one it will read. `lastDay` is taken as published and
     * never worked out from `end` here: every client that shows a
     * window has to say it the inclusive way, and a subtraction
     * written once per client is a client that can disagree with the
     * server about which days a run covers (D16). */
    const start = run === null
      ? monthWindow(config.timezone, 0)
      : { first: run.window.start, last: run.window.lastDay };

    this.state = {
      /* A recollection replaces one run, and a run is one calendar's
       * over one set of days, so there is nothing to choose and no
       * preset is lit -- this window is neither of the months on
       * offer nor one somebody typed. */
      calendar: run === null ? config.calendars[0].key : run.calendar,
      preset: run === null ? THIS_MONTH : null,
      first: start.first,
      last: start.last,
      busy: false,
      failure: null
    };

    this.panel = el('div', {
      class: 'drawer',
      role: 'dialog',
      'aria-modal': 'true',
      'aria-label': TITLE
    });

    this.modal = new Modal(this.panel, {
      scrimClass: 'scrim',
      onClose: () => this.leave()
    });

    this.draw();
  }

  /** Put the drawer on screen.
   *
   * @param {Node} parent Where it goes.
   * @returns {void}
   */
  open(parent) {
    this.modal.open(parent);
  }

  /** Close it, unless a request is in the air.
   *
   * A collection that has been asked for cannot be called back, and
   * the screen it leads to is where its failure would be reported.
   * Closing over the top of one would drop that on the floor.
   *
   * @returns {void}
   */
  leave() {
    if (this.state.busy) {
      this.draw();

      return;
    }

    this.modal.dismiss();
  }

  /** Return how many changes collecting again would discard.
   *
   * The current revision's entries, which is what the count on the
   * review screen means and what the service checks the request
   * against.
   *
   * @returns {number} The count, and zero when this is a fresh
   *     collection.
   */
  changes() {
    if (this.run === null) {
      return 0;
    }

    return this.run.log.filter(
      (entry) => entry.revision === this.run.currentRevision
    ).length;
  }

  /** Return whether the window is one that can be asked for.
   *
   * @returns {boolean} Whether the last day is not before the first.
   */
  valid() {
    return spanDays(this.state.first, this.state.last) > 0;
  }

  /** Choose a calendar.
   *
   * @param {string} key Which one.
   * @returns {void}
   */
  chooseCalendar(key) {
    this.state.calendar = key;
    this.draw();
  }

  /** Choose a window preset, or move to a custom window.
   *
   * @param {Object} preset The preset chosen.
   * @returns {void}
   */
  choosePreset(preset) {
    this.state.preset = preset.key;

    if (preset.ahead !== null) {
      const window = monthWindow(this.config.timezone, preset.ahead);

      this.state.first = window.first;
      this.state.last = window.last;
    }

    this.draw();
  }

  /** Take a typed date.
   *
   * Typing one is choosing a custom window, whichever preset was lit
   * a moment ago: a preset still showing would be describing a window
   * that is no longer the one in the fields.
   *
   * A first day set past the last carries the last with it, rather
   * than leaving the panel refusing a window nobody meant to ask for
   * -- picking a month by its first day is the ordinary way in, and
   * the last day still holding the previous month's is not a mistake
   * worth a refusal.  **Only the first day moves the other.** A last
   * day set before the first is a reader naming the day they want the
   * window to end on, and moving the first to suit it would discard
   * what they just typed.
   *
   * **An emptied field is not a day to count from.** A date input
   * reports an empty string for a cleared or half-typed value, and
   * 'dayAfter' of one is an invalid date that throws rather than
   * returning a day.  So the window is left as the reader has it, the
   * panel refuses as it already did, and nothing is worked out from a
   * date that is not there.
   *
   * @param {string} which `first` or `last`.
   * @param {string} value The date typed.
   * @returns {void}
   */
  setDay(which, value) {
    this.state[which] = value;
    this.state.preset = CUSTOM;

    if (which === 'first' && value !== '' && !this.valid()) {
      this.state.last = dayAfter(this.state.first);
    }

    this.draw();
  }

  /** Ask for the collection, and hand over the job doing it.
   *
   * @returns {Promise<void>} When the job exists, or the refusal is
   *     on screen.
   */
  async start() {
    this.state.busy = true;
    this.state.failure = null;
    this.draw();

    const asked = {
      calendar: this.state.calendar,
      expectedChangeCount: this.changes()
    };

    /* A recollection carries no window at all, which is why the
     * fields above are showing the run's rather than offering one.
     * Assembling one here and leaving the caller to drop it is how a
     * screen comes to describe a request nobody sends. */
    if (this.run === null) {
      asked.window = {
        start: this.state.first,
        end: dayAfter(this.state.last)
      };
    }

    try {
      const job = await this.handlers.onCollect(asked);

      this.modal.dismiss();
      this.handlers.onStarted(job, this.state.calendar);
    } catch (error) {
      /* Refused before a job existed, so nothing is collecting and
       * this is still the screen to be on. Said here rather than
       * behind the drawer, because the window that was refused is in
       * front of somebody who can change it. */
      this.state.busy = false;
      this.state.failure = error;

      /* A recollection refused reads the run again, so that the count
       * this drawer shows -- and the one it would send next -- is
       * what the run holds now.  Without it the refusal is one a
       * reader cannot act on: it says the run has been edited since
       * the number was read, and pressing the button again sends the
       * same stale number and is refused identically, for as long as
       * anybody keeps pressing.
       *
       * Read, not retried.  What is discarded has to be what somebody
       * was shown and agreed to, so the corrected number is put in
       * front of them and the second press is theirs. */
      await this.reread();

      this.draw();
    }
  }

  /** Read the run again, where there is one and a way to.
   *
   * Failure is left alone deliberately: the refusal already on screen
   * is the more useful of the two, and a drawer reporting that it
   * could not re-read would be answering a question nobody asked.
   *
   * @returns {Promise<void>} When it has been read, or has not.
   */
  async reread() {
    if (this.run === null || this.handlers.onReread === undefined) {
      return;
    }

    try {
      this.run = await this.handlers.onReread();
    } catch (error) {
      console.error(error);
    }
  }

  /** Return the calendar control.
   *
   * @returns {HTMLElement} The field.
   */
  calendarField() {
    const { calendars } = this.config;

    return el(
      'div',
      { class: 'field' },
      el('label', { class: 'field-label', text: 'Calendar' }),
      el(
        'div',
        { class: 'seg', role: 'group', 'aria-label': 'Calendar' },
        calendars.map((calendar) => el(
          'button',
          {
            type: 'button',
            class: 'seg-opt drawer-seg-opt',
            'aria-pressed': String(this.state.calendar === calendar.key),
            /* A recollection is a re-reading of the run's own
             * calendar, so the others are shown and refused rather
             * than hidden -- which says why there is no choice. */
            disabled: this.state.busy || this.run !== null,
            onclick: () => this.chooseCalendar(calendar.key)
          },
          calendar.key
        ))
      ),
      el('span', { class: 'field-note muted micro', text: ONE_CALENDAR })
    );
  }

  /** Return the window presets.
   *
   * @returns {HTMLElement} The field.
   */
  presetField() {
    return el(
      'div',
      { class: 'field' },
      el('label', { class: 'field-label', text: 'Window' }),
      el(
        'div',
        { class: 'seg', role: 'group', 'aria-label': 'Window' },
        PRESETS.map((preset) => el(
          'button',
          {
            type: 'button',
            class: 'seg-opt drawer-seg-opt',
            'aria-pressed': String(this.state.preset === preset.key),
            /* Refused for a recollection, like the calendars: the
             * run keeps its window, and a preset that could be
             * pressed would move fields the request cannot carry. */
            disabled: this.state.busy || this.run !== null,
            onclick: () => this.choosePreset(preset)
          },
          preset.words
        ))
      ),
      this.run === null
        ? null
        : el('span', {
          class: 'field-note muted micro',
          text: WINDOW_IS_FIXED
        })
    );
  }

  /** Return one of the two date fields.
   *
   * @param {string} which `first` or `last`.
   * @param {string} words What its label says.
   * @returns {HTMLElement} The field.
   */
  dayField(which, words) {
    return el(
      'div',
      { class: 'field' },
      el('label', { class: 'field-label', for: `day-${which}`, text: words }),
      el('input', {
        id: `day-${which}`,
        class: 'input mono',
        type: 'date',
        value: this.state[which],
        disabled: this.state.busy || this.run !== null,
        onchange: (event) => this.setDay(which, event.target.value)
      })
    );
  }

  /** Return the panel restating the window.
   *
   * For a fresh collection that is the window about to be asked for,
   * and the exclusive end is shown beside the days a reader means
   * because that is the pair the request carries. **A recollection
   * carries no window**, so neither the sent pair nor the sentence
   * explaining the conversion belongs to it: what it shows is the
   * window the run already has, and why it cannot be changed here.
   *
   * @returns {HTMLElement} The panel.
   */
  summary() {
    const { first, last } = this.state;
    const days = spanDays(first, last);
    const replacing = this.run !== null;

    return el(
      'div',
      { class: 'drawer-summary' },
      this.valid()
        ? null
        : el(
          'span',
          { class: 'drawer-bad', role: 'alert' },
          icon('warning-circle'),
          el('span', { text: BACKWARDS })
        ),
      this.valid()
        ? el(
          'span',
          { class: 'drawer-summary-window' },
          icon('calendar-check'),
          el('span', {
            text: `${longDay(first)} to ${longDay(last)} · ${days} `
              + `day${days === 1 ? '' : 's'}, last day included`
          })
        )
        : null,
      this.valid() && !replacing
        ? el('span', {
          class: 'mono muted drawer-summary-sent',
          text: `start=${first}  end=${dayAfter(last)}`
        })
        : null,
      el('span', {
        class: 'muted micro drawer-summary-note',
        text: replacing ? THE_RUNS_OWN_WINDOW : HOW_THE_WINDOW_IS_READ
      })
    );
  }

  /** Return the notes about what the search picks up.
   *
   * @returns {HTMLElement} The notes.
   */
  notes() {
    const calendar = this.config.calendars.find(
      (each) => each.key === this.state.calendar
    );

    if (calendar === undefined) {
      return el('div', { class: 'drawer-notes' });
    }

    return el(
      'div',
      { class: 'drawer-notes' },
      windowNotes(calendar, this.config.excludedTitleTerms).map(
        ([glyph, words]) => el(
          'span',
          { class: 'drawer-note' },
          icon(glyph),
          el('span', { class: 'muted', text: words })
        )
      )
    );
  }

  /** Return the two buttons.
   *
   * @returns {HTMLElement} The actions.
   */
  actions() {
    return el(
      'div',
      { class: 'drawer-actions' },
      el(
        'button',
        {
          type: 'button',
          class: 'btn btn-primary drawer-collect',
          /* The whole of what stands between a double click and two
           * runs. Nothing behind this makes a second one safe. */
          disabled: this.state.busy || !this.valid(),
          onclick: () => this.start()
        },
        icon(this.state.busy ? 'circle-notch' : 'download-simple'),
        this.run === null ? 'Collect events' : 'Replace and collect'
      ),
      el(
        'button',
        {
          type: 'button',
          class: 'btn btn-secondary',
          disabled: this.state.busy,
          onclick: () => this.leave()
        },
        'Cancel'
      )
    );
  }

  /** Draw the whole drawer.
   *
   * @returns {void}
   */
  draw() {
    const changes = this.changes();
    const { failure } = this.state;

    /* `fill` rather than `replaceChildren`, which turns a null child
     * into the word "null" on screen -- and half of what this draws
     * is conditional. */
    fill(
      this.panel,
      el(
        'div',
        { class: 'drawer-head' },
        el(
          'div',
          { class: 'drawer-head-words' },
          el('h2', { class: 'drawer-title', text: TITLE }),
          el('span', { class: 'muted meta', text: LEDE })
        ),
        el(
          'button',
          {
            type: 'button',
            class: 'btn btn-ghost btn-icon',
            'aria-label': 'Close',
            disabled: this.state.busy,
            onclick: () => this.leave()
          },
          icon('x')
        )
      ),
      this.calendarField(),
      this.presetField(),
      el(
        'div',
        { class: 'drawer-days' },
        this.dayField('first', 'First day'),
        this.dayField('last', 'Last day')
      ),
      el(
        'span',
        { class: 'drawer-zone' },
        icon('globe-hemisphere-west'),
        el('span', {
          class: 'muted',
          text: zoneNote(this.config.timezone)
        })
      ),
      this.summary(),
      this.notes(),
      this.run === null
        ? null
        : el(
          'div',
          { class: 'drawer-replace' },
          icon('warning-circle'),
          el('span', { text: replaceWarning(changes) })
        ),
      failure === null
        ? null
        : el(
          'div',
          { class: 'drawer-failure', role: 'alert' },
          icon('warning-circle'),
          el(
            'span',
            {},
            el('span', { text: failure.detail }),
            failure.reference
              ? el(
                'span',
                { class: 'drawer-failure-reference muted micro' },
                'Reference ',
                el('span', { class: 'mono', text: failure.reference })
              )
              : null
          )
        ),
      this.actions()
    );
  }
}
