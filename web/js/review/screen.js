/* The review screen: what a run holds, and what is worth saying about
 * it before somebody sends it.
 *
 * The state here is the client-only half the design lists -- which
 * view, the search text, the two filters, which day groups are
 * collapsed, the selection, whether the change log is showing.
 * Everything else belongs to the server and arrives with the run.
 *
 * A change to any of it redraws the body and leaves the header alone,
 * which is what keeps an open popover open while a filter is applied.
 *
 * **An edit is one call, and its answer is what the screen redraws
 * from.**  The service applies an action whole or not at all and
 * hands back the revision it produced, so nothing here has to work
 * out what an edit did -- which is what keeps the row a reader is
 * looking at the row the service is holding.  One at a time: while a
 * call is in flight every control is disabled, because two edits in
 * the air would each be applied to a revision the other had already
 * changed.
 */

import {
  addEvent,
  ApiError,
  editEvents,
  idempotencyKey,
  listRevisions,
  listUncollected,
  listUnmatchedTitles,
  recordUnmatchedTitle,
  revertRevision,
  sealRevision
} from '../api.js';
import { el, fill, icon } from '../dom.js';
import { anyPopoverOpen, closeAnyPopover } from '../popover.js';
import { changeLogPanel, changesNow } from './changelog.js';
import { refusalNotice, reviewBanners } from './banners.js';
import { reviewHeader } from './header.js';
import { reviewTable } from './table.js';
import { selectionToolbar } from './selection.js';
import { notedKey, uncollectedView } from './uncollected.js';

/* What the hint above the table says. Which one depends on whether
 * any opportunity moves its shift off the calendar times: with no
 * offsets anywhere, the second sentence would describe notes that are
 * not there. */
const TIMES_MATCH = (
  'Shift times match the RCR Calendar times. Edit any time directly; '
  + 'changes save as you make them.'
);
const TIMES_OFFSET = (
  'Shift times are set deliberately earlier or later than the RCR '
  + 'Calendar times, by the amount each opportunity calls for. The '
  + 'note under each time says what that opportunity\'s setting is, '
  + 'and it stays put when you edit a time. Changes save as you make '
  + 'them.'
);

/* Said when the table has more columns than the window has room for. */
const WIDER_THAN_WINDOW = (
  'The table is wider than the window. Scroll sideways for length and '
  + 'slots.'
);

/* What the body says when a filter or a search has hidden everything. */
const NOTHING_MATCHES = (
  'No event in this run matches what you are looking for.'
);

/* Which tab is showing. The names the header's control reports, and
 * the names a path is routed to: each tab is one of the run's two
 * addresses (D28), so what the header says and what the address says
 * have to be the same word. */
export const SHIFTS_VIEW = 'shifts';
export const UNCOLLECTED_VIEW = 'uncollected';

/* What did not happen, said above what is still readable. */
const NOT_CHANGED = 'That change was not made.';
const NOT_NOTED = 'That title was not noted.';
const NOT_READ = 'What this run left out could not be read.';
const NOT_SEALED = 'That revision was not saved.';
const NOT_REVERTED = 'This run was not taken back.';

/* Said while the second tab is being read, and never left up once the
 * read has failed: a line saying something is happening, above a
 * notice saying it did not, is the screen contradicting itself. */
const READING = 'Reading what this run left out';

/* Offered when that read did not arrive. */
const TRY_AGAIN = 'Try again';

/** Return the events a filter and a search leave showing.
 *
 * @param {Array<Object>} events Every event in the revision.
 * @param {Object} state What the screen is showing.
 * @returns {Array<Object>} What to draw.
 */
function showing(events, state) {
  const wanted = state.search.trim().toLowerCase();

  return events.filter((event) => {
    if (state.filters.blocking && !event.blocking) {
      return false;
    }

    if (
      state.filters.fuzzy
      && (event.match === null || event.match.kind !== 'fuzzy')
    ) {
      return false;
    }

    return wanted === '' || event.title.toLowerCase().includes(wanted);
  });
}

/** Return the toolbar above the table.
 *
 * @param {Object} state What the screen is showing.
 * @param {number} shown How many events survive the filters.
 * @param {Object} handlers What its controls do.
 * @returns {HTMLElement} The toolbar.
 */
function toolbar(state, shown, handlers) {
  const total = state.events.length;
  const changes = changesNow(state.run);
  const search = el('input', {
    class: 'input search-field',
    type: 'search',
    value: state.search,
    placeholder: 'Search calendar event names',
    'aria-label': 'Search calendar event names',
    oninput: (event) => handlers.onSearch(event.target.value)
  });

  return el(
    'div',
    { class: 'toolbar card elev-sm' },
    el('button', {
      type: 'button',
      class: handlers.allShown ? 'checkbox checkbox-on' : 'checkbox',
      role: 'checkbox',
      'aria-checked': String(handlers.allShown),
      'aria-label': 'Select every event shown',
      onclick: handlers.onToggleAll
    }),
    el(
      'span',
      { class: 'search-wrap' },
      icon('magnifying-glass'),
      search
    ),
    shown !== total
      ? el('span', {
        class: 'muted meta',
        text: `Showing ${shown} of ${total}`
      })
      : null,
    el(
      'span',
      { class: 'toolbar-right' },
      el(
        'span',
        { class: 'tag tag-neutral' },
        icon('note-pencil'),
        `${changes} change${changes === 1 ? '' : 's'}`
      ),
      el(
        'button',
        {
          type: 'button',
          class: 'btn btn-ghost',
          'aria-pressed': String(state.showLog),
          onclick: handlers.onToggleLog
        },
        'Change log'
      )
    )
  );
}

/**
 * One run on screen, and the client-only state of looking at it.
 */
export class ReviewScreen {
  /** Hold what was read, and what the reader has chosen.
   *
   * @param {Object} answers What the service said.
   * @param {Array<Object>} answers.runs Every run.
   * @param {Object} answers.run The one being reviewed, in full.
   * @param {Array<Object>} answers.revisions Its revisions.
   * @param {Object} answers.config What the deployment was configured
   *     with, read for the calendar's categories.
   * @param {string} [answers.view] Which tab to open on, which is
   *     what the address named. The run's own rows by default.
   * @param {Object} handlers What the screen's exits do.
   * @param {Function} handlers.onView Go to a tab, which is a path
   *     rather than a state this screen sets for itself: the tab is
   *     addressable, so pressing one and arriving at one have to be
   *     the same drawing.
   * @param {Function} handlers.onCollectNew Open the collect drawer
   *     over nothing, to collect a window into a new run.
   * @param {Function} handlers.onSeeInterrupted Open the job the
   *     service stopped in the middle of, which the run names.
   * @param {Function} handlers.onCollectAgain Open the collect drawer
   *     over this run, to read its window again.
   */
  constructor(
    { runs, run, revisions, config, view = SHIFTS_VIEW },
    handlers = {}
  ) {
    this.state = {
      runs,
      run,
      revisions,
      config,
      events: run.events,
      view,
      search: '',
      filters: { blocking: false, fuzzy: false },
      collapsed: new Set(),
      selection: new Set(),
      showLog: false,
      busy: false,
      refusal: null,

      /* The second tab's two answers, read the first time it is
       * opened rather than with the run: most visits to a run never
       * open it, and what it holds is stored rather than worked out,
       * so it is the same answer whenever it is asked for. */
      uncollected: null,
      noted: null,
      notedKeys: new Set(),
      reading: false
    };

    this.handlers = handlers;
    this.element = el('div', { class: 'review' });
    this.body = el('div', { class: 'review-body' });

    this.draw();

    /* Opening straight onto the second tab reads it, the way pressing
     * it does. 'setView' does that read on the way in and is not
     * called for the tab the screen opens on. */
    if (this.state.view === UNCOLLECTED_VIEW) {
      this.loadUncollected();
    }
  }

  /** Return what the rows are drawn against.
   *
   * Built once per draw rather than per row: thirty rows each keying
   * the same opportunities would be thirty copies of one answer.
   *
   * @returns {Object} The context.
   */
  context() {
    const { run, config } = this.state;
    const calendar = config.calendars.find(
      (each) => each.key === run.calendar
    );
    const categories = calendar ? calendar.categories : [];
    const opportunities = new Map(
      run.opportunities.map((each) => [each.needId, each])
    );

    return {
      categories,
      calendarNotes: Boolean(calendar && calendar.notes),
      categoriesByKey: new Map(
        categories.map((each) => [each.key, each])
      ),
      opportunities,
      byId: new Map(run.events.map((each) => [each.id, each])),
      collapsed: this.state.collapsed,
      selection: this.state.selection,
      busy: this.state.busy,
      onToggleDay: (day) => this.toggleDay(day),
      onToggleSelected: (eventId) => this.toggleSelected(eventId),
      onEdit: (operation) => this.edit([operation]),

      /* The role's own, not the run's opportunity: one Amplify
       * listing can be named by categories that time it differently,
       * so two rows here can send to one listing on different offsets.
       * An event's roles still share their offsets -- a category whose
       * need IDs disagree about them is refused when the run is
       * collected -- so the first role speaks for the event. */
      offsetOf: (event) => {
        const first = event.roles[0];

        return {
          start: first ? first.offsetStart : 0,
          end: first ? first.offsetEnd : 0
        };
      }
    };
  }

  /** Redraw whichever tab is showing, leaving the header alone.
   *
   * @returns {void}
   */
  redraw() {
    if (this.state.view === UNCOLLECTED_VIEW) {
      this.drawUncollected();

      return;
    }

    this.drawShifts();
  }

  /** Redraw the run's own rows.
   *
   * @returns {void}
   */
  drawShifts() {
    const context = this.context();
    const shown = showing(this.state.events, this.state);
    const anyOffset = this.state.events.some(
      (event) => event.roles.some(
        (role) => role.offsetStart || role.offsetEnd
      )
    );

    const chosen = [...this.state.selection];
    const allShown = shown.length > 0
      && shown.every((event) => this.state.selection.has(event.id));

    const handlers = {
      allShown,
      onSearch: (text) => {
        this.state.search = text;
        this.focusSearch = true;
        this.redraw();
      },
      onToggleLog: () => {
        this.state.showLog = !this.state.showLog;
        this.redraw();
      },
      onToggleBlocking: () => {
        this.state.filters.blocking = !this.state.filters.blocking;
        this.redraw();
      },
      onToggleFuzzy: () => {
        this.state.filters.fuzzy = !this.state.filters.fuzzy;
        this.redraw();
      },
      onToggleAll: () => {
        /* What is shown rather than what the run holds: a select-all
         * that reached past a filter would act on rows nobody could
         * see. */
        this.state.selection = allShown
          ? new Set()
          : new Set(shown.map((event) => event.id));

        this.redraw();
      },
      onSeeInterrupted: () => this.handlers.onSeeInterrupted()
    };

    /* Each of these is one operation naming every selected event, not
     * one call per row: the service applies it whole or not at all,
     * and the change log gets one entry. */
    const bulk = {
      onSetCategory: (category) => this.edit([
        { op: 'set_category', eventIds: chosen, category }
      ]),
      onNudge: (minutes) => this.edit([
        { op: 'nudge', eventIds: chosen, minutes }
      ]),
      onResetSlots: () => this.edit([
        { op: 'reset_slots', eventIds: chosen }
      ]),
      onRemove: () => this.edit([
        { op: 'remove', eventIds: chosen }
      ]),
      onClear: () => this.clearSelection()
    };

    this.body.replaceChildren(
      ...reviewBanners(this.state, handlers),
      this.state.refusal === null
        ? ''
        : refusalNotice(this.state.refusal),
      this.state.selection.size > 0
        ? selectionToolbar(this.state, context.categories, bulk)
        : toolbar(this.state, shown.length, handlers),
      el('p', {
        class: 'table-hint muted note',
        text: anyOffset ? TIMES_OFFSET : TIMES_MATCH
      }),
      el(
        'p',
        { class: 'table-hint muted note' },
        icon('arrows-horizontal'),
        el('span', { text: WIDER_THAN_WINDOW })
      ),
      shown.length === 0
        ? el('p', { class: 'muted meta', text: NOTHING_MATCHES })
        : el(
          'div',
          { class: 'table-scroll' },
          reviewTable(shown, context)
        )
    );

    /* Kept out of the scrolling region: the panel sits beside the
     * table rather than inside what scrolls sideways. */
    this.panel.replaceChildren(
      this.state.showLog
        ? changeLogPanel(this.state, context, handlers.onToggleLog)
        : ''
    );

    /* A search field that lost focus on every keystroke would be a
     * search field nobody could type in.  Asked for by the one
     * handler that redraws while somebody is typing, and answered
     * once: every other redraw is something a person did elsewhere on
     * the screen, and moving focus into the search field would take
     * it off what they pressed and scroll the table back to the top.
     */
    if (this.focusSearch) {
      const field = this.body.querySelector('.search-field');

      if (field !== null) {
        field.focus();
        field.setSelectionRange(field.value.length, field.value.length);
      }
    }

    this.focusSearch = false;
  }

  /** Draw the Not collected tab, and read it if it has not been read.
   *
   * Three states, and the first two are never on screen together: a
   * read that failed replaces the line saying one is happening rather
   * than sitting under it.
   *
   * @returns {void}
   */
  drawUncollected() {
    const { refusal, reading, uncollected, noted } = this.state;
    const readable = uncollected !== null && noted !== null;

    fill(
      this.body,
      refusal === null ? null : refusalNotice(refusal),
      reading
        ? el(
          'p',
          { class: 'reading muted meta' },
          icon('circle-notch'),
          el('span', { text: READING })
        )
        : null,
      readable || reading
        ? null
        : el(
          'button',
          {
            type: 'button',
            class: 'btn btn-secondary self-start',
            onclick: () => this.loadUncollected()
          },
          icon('arrows-clockwise'),
          TRY_AGAIN
        ),
      readable
        ? uncollectedView(this.state, {
          onAdd: (eventId) => this.addFromWindow(eventId),
          onNote: (title) => this.noteTitle(title)
        })
        : null
    );

    /* The change log belongs beside the run's own rows. Cleared
     * rather than left showing, because the toggle that opens it is
     * on the other tab and there would be no way to close it. */
    this.panel.replaceChildren();
  }

  /** Return the header, built against what the screen now shows.
   *
   * @returns {HTMLElement} The header.
   */
  buildHeader() {
    return reviewHeader(this.state, {
      onOpenRun: (runId) => {
        closeAnyPopover();
        this.handlers.onOpenRun(runId);
      },
      /* Out to the address and back in, rather than straight to
       * 'setView': the tab is a path, and a tab pressed has to leave
       * the same history entry behind as a tab arrived at. What comes
       * back is 'setView', on this same screen, so nothing the reader
       * has done to the table is thrown away. */
      onView: (view) => this.handlers.onView(view),
      onSeal: () => this.seal(),
      onRevert: (number) => this.revertTo(number),
      onCollectNew: () => {
        closeAnyPopover();

        /* The entry that was pressed is inside the popover just
         * closed, so a drawer opening now would record a button no
         * longer on the page and hand focus to nothing when it is
         * cancelled. The picker is what opened it and is still here.
         * "Collect again" needs none of this: it is a header button
         * that stays put. */
        const picker = this.headerElement.querySelector('.run-picker');

        if (picker !== null) {
          picker.focus();
        }

        this.handlers.onCollectNew();
      },
      onCollectAgain: () => {
        closeAnyPopover();
        this.handlers.onCollectAgain();
      },
      onPreview: () => this.handlers.onPreview()
    });
  }

  /** Put the header back, built against what the screen now shows.
   *
   * Called for the few things the header states and nothing else:
   * which tab is pressed, which revision is current, and how many
   * there are. Everything else leaves it alone, which is what keeps
   * an open popover open while a filter is applied.
   *
   * @returns {void}
   */
  renderHeader() {
    const header = this.buildHeader();

    this.headerElement.replaceWith(header);
    this.headerElement = header;
  }

  /** Show one of the two tabs.
   *
   * The header is rebuilt for this and for nothing else: which tab is
   * pressed is stated in it, and everything else that changes leaves
   * it alone so that an open popover survives a filter.
   *
   * @param {string} view Which tab.
   * @returns {void}
   */
  setView(view) {
    if (view === this.state.view) {
      return;
    }

    this.state.view = view;

    /* A refusal is about the tab it happened on. */
    this.state.refusal = null;

    this.renderHeader();
    this.redraw();

    if (view === UNCOLLECTED_VIEW && this.state.uncollected === null) {
      this.loadUncollected();
    }
  }

  /** Draw the whole screen.
   *
   * @returns {void}
   */
  draw() {
    this.panel = el('div', { class: 'review-panel' });
    this.focusSearch = false;
    this.headerElement = this.buildHeader();

    this.element.replaceChildren(
      this.headerElement,
      el('div', { class: 'review-with-panel' }, this.body, this.panel)
    );

    /* The design gives Escape an order: what is in front closes first.
     * A popover handles its own, so the selection is cleared only when
     * there was nothing over it. */
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && !anyPopoverOpen()) {
        this.clearSelection();
      }
    });

    this.redraw();
  }

  /** Send one action, and redraw from what it answered.
   *
   * The key names this action and is minted here, once. It is not
   * reused for the next one: two nudges are two actions and have to
   * move the shift twice. A key is what makes a *resend* of this same
   * action safe, not what makes a second action idempotent.
   *
   * @param {Array<Object>} operations What to do, in order.
   * @returns {Promise<void>} When the screen has redrawn.
   */
  async edit(operations) {
    if (this.state.busy) {
      return;
    }

    this.state.busy = true;
    this.state.refusal = null;
    this.redraw();

    try {
      const answer = await editEvents(
        this.state.run.id,
        operations,
        idempotencyKey()
      );

      /* The whole revision, and the entries the edit added. Replaced
       * rather than merged: what the service holds is the answer to
       * what the rows now are. */
      this.state.run.events = answer.events;
      this.state.events = answer.events;
      this.state.run.log = [...this.state.run.log, ...answer.log];

      /* An event the edit removed cannot stay selected. */
      const alive = new Set(answer.events.map((each) => each.id));

      this.state.selection = new Set(
        [...this.state.selection].filter((id) => alive.has(id))
      );
    } catch (error) {
      this.refused(error, NOT_CHANGED);
    } finally {
      this.state.busy = false;
      this.redraw();
    }
  }

  /** Fix what the run holds now as a numbered revision.
   *
   * The answer is the revision the work has moved to, which is not
   * the whole of what the picker draws: the one just sealed stops
   * being current and the list gains a member. So the list is read
   * again rather than adjusted here, the way every other answer this
   * screen redraws from is the server's.
   *
   * @returns {Promise<void>} When the header has redrawn.
   */
  async seal() {
    if (this.state.busy) {
      return;
    }

    closeAnyPopover();
    this.state.busy = true;
    this.state.refusal = null;
    this.redraw();

    try {
      const opened = await sealRevision(
        this.state.run.id,
        idempotencyKey()
      );

      /* The events do not move: the revision opened holds a copy,
       * keeping each event's own identifier, so the rows on screen
       * are the rows it holds. What changes is which revision they
       * are in, and the change count with it -- the log is counted
       * by revision, so entries made in the one just sealed stay
       * under its number. */
      this.state.run.currentRevision = opened.number;
      this.state.revisions = await listRevisions(this.state.run.id);
    } catch (error) {
      this.refused(error, NOT_SEALED);
    } finally {
      this.state.busy = false;
      this.renderHeader();
      this.redraw();
    }
  }

  /** Take the run back to what an earlier revision holds.
   *
   * One revision per revert, which is the service's doing and not
   * this screen's: nothing is sealed first and nothing between the
   * two is touched.
   *
   * @param {number} number Which revision to go back to.
   * @returns {Promise<void>} When the screen has redrawn.
   */
  async revertTo(number) {
    if (this.state.busy) {
      return;
    }

    closeAnyPopover();
    this.state.busy = true;
    this.state.refusal = null;
    this.redraw();

    try {
      const run = await revertRevision(
        this.state.run.id,
        number,
        idempotencyKey()
      );

      /* The run in full, because every row has changed. Replaced
       * rather than merged, and the selection with it: the events a
       * revert leaves are not necessarily the ones that were ticked. */
      this.state.run = run;
      this.state.events = run.events;
      this.state.selection = new Set();
      this.state.revisions = await listRevisions(run.id);
      this.forgetUncollected();
    } catch (error) {
      this.refused(error, NOT_REVERTED);
    } finally {
      this.state.busy = false;
      this.renderHeader();
      this.redraw();

      /* Read after the redraw and not before it, so the tab is put
       * back into its reading state by a screen that is no longer
       * busy -- started inside the call above, the two would be
       * drawing over each other. */
      if (
        this.state.view === UNCOLLECTED_VIEW
        && this.state.uncollected === null
      ) {
        this.loadUncollected();
      }
    }
  }

  /** Let go of what the second tab holds, so it is asked for again.
   *
   * Going back to the first revision drops the events somebody pulled
   * in and offers them there once more. Whether a row may be pulled
   * in is `addable`, which is the server's answer and never this
   * screen's, so what that tab holds after a revert is a question
   * rather than something to adjust here. Both are dropped, because
   * they are read together: a tab assembled from two moments is one
   * whose rows and whose noted list can disagree about a title.
   *
   * @returns {void}
   */
  forgetUncollected() {
    this.state.uncollected = null;
    this.state.noted = null;
    this.state.notedKeys = new Set();
  }

  /** Remember why a call was refused, in the shape the notice reads.
   *
   * The reason is the service's where there is one; anything that is
   * not a problem document is the page's own fault and is logged, so
   * that what reaches the screen is still a sentence.
   *
   * @param {Error} error What came back.
   * @param {string} said What did not happen, as a sentence.
   * @returns {void}
   */
  refused(error, said) {
    if (!(error instanceof ApiError)) {
      console.error(error);
    }

    this.state.refusal = {
      said,
      failure: error instanceof ApiError
        ? error
        : new ApiError({
          status: 0,
          detail: String(error.message || error)
        })
    };
  }

  /** Hold the log kept for the data model, and what it already holds.
   *
   * The Set is what a row asks whether it has been noted, keyed the
   * way the log keys an entry -- by the calendar as well as the
   * title, because the categories a title is matched against belong
   * to a calendar.
   *
   * @param {Array<Object>} noted The entries, newest sighting first.
   * @returns {void}
   */
  rememberNoted(noted) {
    this.state.noted = noted;
    this.state.notedKeys = new Set(
      noted.map((entry) => notedKey(entry.calendar, entry.title))
    );
  }

  /** Read what the run left out, and what has been noted for the
   * model.
   *
   * Asked for together rather than one after the other: a tab
   * assembled from two moments is a tab whose rows and whose noted
   * list can disagree about the same title.
   *
   * @returns {Promise<void>} When the tab has redrawn.
   */
  async loadUncollected() {
    if (this.state.reading) {
      return;
    }

    this.state.reading = true;
    this.state.refusal = null;
    this.redraw();

    try {
      const [uncollected, noted] = await Promise.all([
        listUncollected(this.state.run.id),
        listUnmatchedTitles()
      ]);

      this.state.uncollected = uncollected;
      this.rememberNoted(noted);
    } catch (error) {
      this.refused(error, NOT_READ);
    } finally {
      this.state.reading = false;
      this.redraw();
    }
  }

  /** Pull one event the search missed into the run.
   *
   * No key: naming an event the revision already holds is refused, so
   * a second arrival of this request is a refusal rather than a
   * second row.
   *
   * @param {string} eventId Which uncollected entry to pull in.
   * @returns {Promise<void>} When the tab has redrawn.
   */
  async addFromWindow(eventId) {
    if (this.state.busy) {
      return;
    }

    this.state.busy = true;
    this.state.refusal = null;
    this.redraw();

    try {
      const answer = await addEvent(this.state.run.id, eventId);

      this.state.run.events = answer.events;
      this.state.events = answer.events;
      this.state.run.log = [...this.state.run.log, ...answer.log];

      /* Read again rather than struck off here. Whether a row may be
       * pulled in is `addable`, which is the server's answer, and the
       * row is *not* removed by being pulled in -- it is what a
       * revert to the first revision gives back. Working either out
       * from the answer to the write would be this screen holding a
       * second opinion about both. */
      this.state.uncollected = await listUncollected(this.state.run.id);
    } catch (error) {
      this.refused(error, NOT_CHANGED);
    } finally {
      this.state.busy = false;
      this.redraw();
    }
  }

  /** Record one title the data model did not match.
   *
   * No key either: a run is held to one sighting of a title by the
   * repository, so asking twice from the same run adds nothing.
   *
   * @param {string} title The title, as the calendar gave it.
   * @returns {Promise<void>} When the tab has redrawn.
   */
  async noteTitle(title) {
    if (this.state.busy) {
      return;
    }

    this.state.busy = true;
    this.state.refusal = null;
    this.redraw();

    try {
      const entry = await recordUnmatchedTitle(
        this.state.run.calendar,
        title,
        this.state.run.id
      );

      /* The answer is the entry as the log now holds it, this
       * sighting counted, so it replaces whatever was there rather
       * than joining it. Put at the front, which is the order the
       * list is read in: newest sighting first. */
      const key = notedKey(entry.calendar, entry.title);

      this.rememberNoted([
        entry,
        ...this.state.noted.filter(
          (each) => notedKey(each.calendar, each.title) !== key
        )
      ]);
    } catch (error) {
      this.refused(error, NOT_NOTED);
    } finally {
      this.state.busy = false;
      this.redraw();
    }
  }

  /** Put an event in the selection, or take it out.
   *
   * @param {string} eventId Which event.
   * @returns {void}
   */
  toggleSelected(eventId) {
    if (this.state.selection.has(eventId)) {
      this.state.selection.delete(eventId);
    } else {
      this.state.selection.add(eventId);
    }

    this.redraw();
  }

  /** Empty the selection.
   *
   * @returns {void}
   */
  clearSelection() {
    if (this.state.selection.size > 0) {
      this.state.selection = new Set();
      this.redraw();
    }
  }

  /** Collapse a day's group, or open it again.
   *
   * @param {string} day Which day.
   * @returns {void}
   */
  toggleDay(day) {
    if (this.state.collapsed.has(day)) {
      this.state.collapsed.delete(day);
    } else {
      this.state.collapsed.add(day);
    }

    this.redraw();
  }
}
