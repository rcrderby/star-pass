/* The review screen: what a run holds, and what is worth saying about
 * it before somebody sends it.
 *
 * The state here is the client-only half the design lists -- which
 * view, the search text, the two filters, which day groups are
 * collapsed, whether the change log is showing.  Everything else
 * belongs to the server and arrives with the run.
 *
 * A change to any of it redraws the body and leaves the header alone,
 * which is what keeps an open popover open while a filter is applied.
 */

import { el, icon } from '../dom.js';
import { closeAnyPopover } from '../popover.js';
import { changeLogPanel } from './changelog.js';
import { reviewBanners } from './banners.js';
import { reviewHeader } from './header.js';
import { reviewTable } from './table.js';

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
  const revision = state.revisions.find((each) => each.current);
  const changes = revision ? revision.changes : 0;
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
    el('span', {
      class: 'checkbox',
      role: 'checkbox',
      'aria-checked': 'false',
      'aria-disabled': 'true',
      'aria-label': 'Select every event'
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
      showLog: false
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
      onToggleDay: (day) => this.toggleDay(day),

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

    const handlers = {
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
      }
    };

    this.body.replaceChildren(
      ...reviewBanners(this.state, handlers),
      toolbar(this.state, shown.length, handlers),
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
      onCollectAgain: () => alert(NOT_YET),
      onPreview: () => alert(NOT_YET)
    });

    this.element.replaceChildren(
      header,
      el('div', { class: 'review-with-panel' }, this.body, this.panel)
    );

    this.redraw();
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
