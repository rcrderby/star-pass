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

import { ApiError, editEvents, idempotencyKey } from '../api.js';
import { el, icon } from '../dom.js';
import { anyPopoverOpen, closeAnyPopover } from '../popover.js';
import { changeLogPanel } from './changelog.js';
import { reviewBanners } from './banners.js';
import { reviewHeader } from './header.js';
import { reviewTable } from './table.js';
import { selectionToolbar } from './selection.js';

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

/* What stands in for the screens this one leads to, until they land. */
const NOT_YET = 'That screen is not built yet.';

/** Return what a refused edit says.
 *
 * A notice above the table rather than the screen-wide failure, which
 * would throw away a run that is still perfectly readable. The service
 * applies an action whole or not at all, so nothing was half done and
 * the rows below are what they were.
 *
 * @param {ApiError} failure What went wrong.
 * @returns {HTMLElement} The notice.
 */
function editFailure(failure) {
  return el(
    'div',
    { class: 'banner banner-alert', role: 'alert' },
    icon('warning-circle'),
    el(
      'span',
      { class: 'banner-words meta' },
      el('span', { text: `That change was not made. ${failure.detail}` }),
      failure.reference
        ? el(
          'span',
          { class: 'muted micro failure-reference' },
          'Reference ',
          el('span', { class: 'mono', text: failure.reference })
        )
        : null
    )
  );
}

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
  /* Counted from the log rather than read off the revision, which
   * is the same number -- a revision's count is what was logged while
   * it was current -- and stays right after an edit without asking
   * the service for the revisions again. */
  const changes = state.run.log.filter(
    (entry) => entry.revision === state.run.currentRevision
  ).length;
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
   * @param {Object} handlers What the screen's exits do.
   * @param {Function} handlers.onCollectAgain Open the collect drawer
   *     over this run, to read its window again.
   */
  constructor({ runs, run, revisions, config }, handlers = {}) {
    this.state = {
      runs,
      run,
      revisions,
      config,
      events: run.events,
      view: 'shifts',
      search: '',
      filters: { blocking: false, fuzzy: false },
      collapsed: new Set(),
      selection: new Set(),
      showLog: false,
      busy: false,
      failure: null
    };

    this.handlers = handlers;
    this.element = el('div', { class: 'review' });
    this.body = el('div', { class: 'review-body' });

    this.draw();
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

      /* An event's roles share their offsets: a category whose need
       * IDs disagree about them is refused when the run is collected,
       * so the first role speaks for the event. */
      offsetOf: (event) => {
        const first = event.roles[0];
        const opportunity = first
          ? opportunities.get(first.needId)
          : null;

        return {
          start: opportunity ? opportunity.offsetStart : 0,
          end: opportunity ? opportunity.offsetEnd : 0
        };
      }
    };
  }

  /** Redraw the body, leaving the header where it is.
   *
   * @returns {void}
   */
  redraw() {
    const context = this.context();
    const shown = showing(this.state.events, this.state);
    const anyOffset = this.state.run.opportunities.some(
      (each) => each.offsetStart || each.offsetEnd
    );

    const chosen = [...this.state.selection];
    const allShown = shown.length > 0
      && shown.every((event) => this.state.selection.has(event.id));

    const handlers = {
      allShown,
      onSearch: (text) => {
        this.state.search = text;
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
      }
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
      this.state.failure === null ? '' : editFailure(this.state.failure),
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
        ? changeLogPanel(this.state, handlers.onToggleLog)
        : ''
    );

    /* A search field that lost focus on every keystroke would be a
     * search field nobody could type in. */
    if (this.focusSearch) {
      const field = this.body.querySelector('.search-field');

      if (field !== null) {
        field.focus();
        field.setSelectionRange(field.value.length, field.value.length);
      }
    }

    this.focusSearch = true;
  }

  /** Draw the whole screen.
   *
   * @returns {void}
   */
  draw() {
    this.panel = el('div', { class: 'review-panel' });
    this.focusSearch = false;

    const header = reviewHeader(this.state, {
      onOpenRun: (runId) => {
        closeAnyPopover();
        this.handlers.onOpenRun(runId);
      },
      onView: () => alert(NOT_YET),
      onCollectAgain: () => {
        closeAnyPopover();
        this.handlers.onCollectAgain();
      },
      onPreview: () => this.handlers.onPreview()
    });

    this.element.replaceChildren(
      header,
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
    this.state.failure = null;
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
      if (!(error instanceof ApiError)) {
        console.error(error);
      }

      this.state.failure = error instanceof ApiError
        ? error
        : new ApiError({
          status: 0,
          detail: String(error.message || error)
        });
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
