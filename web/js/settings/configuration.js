/* What the service resolved at start up, and how long it keeps what a
 * run leaves behind.
 *
 * A pure reading of `GET /v1/config`: every value was answered by the
 * service, and nothing here works one out.
 *
 * **Two columns, not three.**  Where a value came from - a default,
 * the environment, fixed in the tool - is not published, so a third
 * column would be blank or invented.
 *
 * The words are this client's.  The contract answers with a zone, a
 * threshold and three numbers of days, and saying what each is
 * measured from is the job of whoever shows it.
 */

import { el, icon } from '../dom.js';

/* What a calendar searched for nothing in particular is said to be
 * searched for.  An empty query string is a value rather than an
 * absence: it returns the whole window, which is what makes a search
 * miss impossible on a calendar configured with one. */
const EVERYTHING = 'All events';

/* Stood in for a list the deployment configured nothing in. */
const NOTHING = '—';

/* How a list of terms is joined. */
const TERM_GAP = ', ';

/* The note under the settings table.  The zone above is the one a
 * window's dates are read in, and it belongs to the service rather
 * than to whoever is looking at this page. */
const TIMEZONE_NOTE = (
  'Runs read and display calendar data in the specified time zone, '
  + 'never the time zone of the browser.'
);

/* The note under the calendars table. */
const SEARCH_NOTE = (
  'Each term requires a separate search request to the League '
  + 'Calendar. Events that do not match a search term are classified '
  + 'as Not collected, and they may be added to a run manually.'
);

/* What each row of the settings table is called and how its value is
 * worded.  A table rather than three builders, because the difference
 * between the rows is data. */
const SETTINGS = [
  {
    name: 'Time zone',
    value: (config) => config.timezone
  },
  {
    name: 'Match confidence threshold',
    value: (config) => `${config.matchThreshold} out of 100`
  },
  {
    name: 'Filtered event titles',
    value: (config) => config.excludedTitleTerms.join(TERM_GAP) || NOTHING
  }
];

/* What is kept, for how long, and why that is the window it is on.
 * Three axes rather than one: the first two expire by age and
 * the third is answered by the data model coming to match a title,
 * and a single window over all three would delete the thing one of
 * them measures. */
const STORES = [
  {
    name: 'Job logs',
    kept: (retention) => `${retention.jobLogDays} days after the job finished`,
    note: 'The job itself is not removed with its log. The record of '
      + 'when a run occurred and its outcome survives longer than the '
      + 'run data.'
  },
  {
    name: 'Revisions',
    kept: (retention) => `${retention.revisionDays} days after the run `
      + 'last experienced activity',
    note: 'The first and current revisions persist indefinitely. '
      + 'Intermediate revisions expire.'
  },
  {
    name: 'Unmatched titles',
    kept: (retention) => `${retention.unmatchedTitleDays} days after a `
      + 'title was last seen',
    note: 'Unmatched titles expire if they are not added to the '
      + 'shift data model.'
  },
  {
    name: 'Sent shifts',
    kept: () => 'Indefinite',
    note: 'Retaining shift data sent to Amplify supports preventing '
      + 'attempts to create duplicate shifts.'
  }
];

/** Return what one calendar's window is searched for.
 *
 * @param {Object} calendar A calendar, as the configuration lists it.
 * @returns {string} The terms, or what an empty one means.
 */
function searchedFor(calendar) {
  const terms = calendar.searchTerms.filter((term) => term !== '');

  if (terms.length === 0) {
    return EVERYTHING;
  }

  return terms.map((term) => `"${term}"`).join(TERM_GAP);
}

/** Return a two-column table of names and values.
 *
 * @param {string} heading What the first column is called.
 * @param {string} second What the second column is called.
 * @param {Array<Array<string>>} rows The pairs, in order.
 * @returns {HTMLElement} The table.
 */
function pairTable(heading, second, rows) {
  return el(
    'table',
    /* The preview's table, which is the one table this interface
     * has. A second one styled separately would be two things that
     * have to look identical and no reason for them to stay that
     * way; what `settings-table` adds is the column widths, because
     * a name and a value are not a preview's five columns. */
    { class: 'table settings-table' },
    el(
      'thead',
      {},
      el(
        'tr',
        {},
        el('th', { text: heading }),
        el('th', { text: second })
      )
    ),
    el(
      'tbody',
      {},
      rows.map(([name, value]) => el(
        'tr',
        {},
        el('td', { text: name }),
        el('td', { class: 'mono settings-value', text: value })
      ))
    )
  );
}

/** Return one line under a table, saying what it means.
 *
 * @param {string} words The sentence.
 * @returns {HTMLElement} The line.
 */
function tableNote(words) {
  return el(
    'p',
    { class: 'settings-table-note muted note' },
    icon('info'),
    el('span', { text: words })
  );
}

/** Return the settings this service resolved.
 *
 * @param {Object} config What the deployment was configured with.
 * @returns {Array<Node>} The two tables and what they mean.
 */
export function resolvedSettings(config) {
  return [
    pairTable(
      'Setting',
      'Value',
      SETTINGS.map((setting) => [setting.name, setting.value(config)])
    ),
    tableNote(TIMEZONE_NOTE),
    el('h3', { class: 'settings-subheading', text: 'Calendars' }),
    pairTable(
      'Calendar',
      'Search terms',
      config.calendars.map(
        (calendar) => [calendar.key, searchedFor(calendar)]
      )
    ),
    tableNote(SEARCH_NOTE)
  ];
}

/** Return what is kept and for how long.
 *
 * @param {Object} retention The windows, as the configuration
 *     publishes them.
 * @returns {HTMLElement} The rows.
 */
export function stateRows(retention) {
  return el(
    'div',
    { class: 'settings-stores' },
    STORES.map((store) => el(
      'div',
      { class: 'row-card settings-store' },
      el(
        'div',
        {},
        el('div', { class: 'settings-store-name', text: store.name }),
        el('span', {
          class: 'mono muted note',
          text: store.kept(retention)
        })
      ),
      el('span', { class: 'muted meta settings-store-note', text: store.note })
    ))
  );
}
