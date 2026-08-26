/* Turning what the contract answers with into what a reader sees.
 *
 * One rule governs everything here, and it is D16's: **the server's
 * zone is authoritative**.  A run carries the zone its window was read
 * in, and every date and time belonging to that run is shown in it.
 * The browser's own zone is never consulted -- a reviewer in another
 * one must not be shown a different day from the one the shift will be
 * created on, and the whole reason run identity, time and idempotency
 * moved server-side is that all three used to be worked out here.
 */

/* What a zone-less formatter would fall back to, which is the thing
 * this module exists to avoid.  Passed explicitly every time, so a
 * call that forgot it is a call that throws rather than one that
 * quietly answers in whoever-is-looking's zone. */
const MISSING_ZONE = 'A time cannot be shown without the zone it belongs to.';

/* For working a span of days out of two dates built in UTC, where
 * every day is this long because no offset changes inside it. */
const MILLISECONDS_PER_DAY = 86400000;

/** Return one timestamp as a reader sees it.
 *
 * @param {string} when ISO-8601 UTC, as the repository records it.
 * @param {string} timeZone The run's zone, from its window.
 * @throws {Error} When no zone was given.
 * @returns {string} The day and time, in that zone.
 */
export function moment(when, timeZone) {
  if (!timeZone) {
    throw new Error(MISSING_ZONE);
  }

  const shown = new Intl.DateTimeFormat('en-US', {
    timeZone,
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit'
  }).format(new Date(when));

  /* The design sets the meridiem in lower case, and the formatter
   * has no option for it. */
  return shown.replace(' AM', ' am').replace(' PM', ' pm');
}

/** Return a bare calendar day as a heading names it.
 *
 * A run's dates are plain days with no zone -- they are league dates
 * the service already resolved -- so they are read as such rather
 * than as instants. Handing '2026-08-12' to `new Date` parses it as
 * UTC midnight, which in any zone behind UTC renders as the 11th; the
 * parts are read out instead and formatted in UTC, so the day named
 * is the day stored.
 *
 * @param {string} day An ISO date, as the run stores it.
 * @returns {string} The weekday, month, day and year.
 */
export function dayHeading(day) {
  const [year, month, date] = day.split('-').map(Number);

  return new Intl.DateTimeFormat('en-US', {
    timeZone: 'UTC',
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric'
  }).format(new Date(Date.UTC(year, month - 1, date)));
}

/** Return a bare calendar day, short, for a window.
 *
 * @param {string} day An ISO date.
 * @param {boolean} [withYear] Whether to name the year.
 * @returns {string} Such as `Aug 1`, or `Sep 7 2026`.
 */
export function shortDay(day, withYear = false) {
  const [year, month, date] = day.split('-').map(Number);
  const shown = new Intl.DateTimeFormat('en-US', {
    timeZone: 'UTC',
    month: 'short',
    day: 'numeric'
  }).format(new Date(Date.UTC(year, month - 1, date)));

  return withYear ? `${shown} ${year}` : shown;
}

/** Return the window a run covers, as a reader means it.
 *
 * Built from `start` and the published `lastDay`. The exclusive `end`
 * is never shown: it names the day after the run, which reads as a
 * run covering a day it does not.
 *
 * @param {Object} window A run's window.
 * @returns {string} Such as `Aug 1 – Sep 7 2026`.
 */
export function windowText(window) {
  return `${shortDay(window.start)} – ${shortDay(window.lastDay, true)}`;
}

/** Return a count with its noun, singular where it should be.
 *
 * Here rather than beside the first screen that needed one: the runs
 * list counts events and shifts, and the send counts shifts and
 * opportunities, and a run reading `1 shifts` on one screen and
 * `1 shift` on the other would be two copies of one rule.
 *
 * @param {number} count How many.
 * @param {string} noun What of, singular.
 * @param {string} [plural] The plural, when it is not the noun and an
 *     `s`.
 * @returns {string} Such as `1 shift` or `3 opportunities`.
 */
export function counted(count, noun, plural = null) {
  const many = plural === null ? `${noun}s` : plural;

  return `${count} ${count === 1 ? noun : many}`;
}

/** Return a length in minutes as the table shows it.
 *
 * @param {number} minutes How long the shift lasts.
 * @returns {string} Such as `60 min`.
 */
export function lengthText(minutes) {
  return `${minutes} min`;
}

/** Return today's date, as the server's zone has it.
 *
 * **This is the one place the current moment is turned into a day**,
 * and it is turned into one in the zone the service published rather
 * than the zone the browser happens to be in. D16 calls a preset
 * computed in the visitor's zone a live bug in the original design,
 * and it is: somebody in London opening the drawer at nine in the
 * morning would otherwise be offered a September window on the last
 * day of August.
 *
 * `en-CA` because its short date is an ISO one, which is the shape
 * every date in this contract crosses the wire as.
 *
 * @param {string} timeZone The zone `GET /config` reports.
 * @throws {Error} When no zone was given.
 * @returns {string} Today there, as an ISO date.
 */
export function today(timeZone) {
  if (!timeZone) {
    throw new Error(MISSING_ZONE);
  }

  return new Intl.DateTimeFormat('en-CA', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit'
  }).format(new Date());
}

/** Return the day after a given one.
 *
 * A run's window crosses the wire with an **exclusive** end, and a
 * person says a window by its last day, so a request has one more
 * day added to it. That conversion is the client's here and only
 * here: the answer publishes `lastDay` beside `end` so nothing has to
 * subtract, but no request takes an inclusive day, which is why the
 * command line's `_render.after` does the same thing in the same
 * direction.
 *
 * Read out as parts and built in UTC. `new Date('2026-09-30')` is
 * parsed as UTC midnight and lands on the 29th anywhere behind UTC,
 * which is a window a day short.
 *
 * @param {string} day An ISO date.
 * @returns {string} The next one.
 */
export function dayAfter(day) {
  const [year, month, date] = day.split('-').map(Number);
  const next = new Date(Date.UTC(year, month - 1, date + 1));

  return next.toISOString().slice(0, 10);
}

/** Return how many days a window covers, counting its last day.
 *
 * @param {string} first The first day, as an ISO date.
 * @param {string} last The last day it covers.
 * @returns {number} Days covered, which is not above zero when the
 *     last day comes before the first.
 */
export function spanDays(first, last) {
  const [fromYear, fromMonth, fromDate] = first.split('-').map(Number);
  const [toYear, toMonth, toDate] = last.split('-').map(Number);
  const from = Date.UTC(fromYear, fromMonth - 1, fromDate);
  const to = Date.UTC(toYear, toMonth - 1, toDate);

  return Math.round((to - from) / MILLISECONDS_PER_DAY) + 1;
}

/** Return a month's window, as a first day and a last day.
 *
 * Worked out from today in the server's zone, so "this month" means
 * the month it is there.
 *
 * @param {string} timeZone The zone `GET /config` reports.
 * @param {number} monthsAhead 0 for this month, 1 for the next.
 * @returns {Object} Its `first` and `last` day, as ISO dates.
 */
export function monthWindow(timeZone, monthsAhead) {
  const [year, month] = today(timeZone).split('-').map(Number);
  const first = new Date(Date.UTC(year, month - 1 + monthsAhead, 1));
  const last = new Date(Date.UTC(year, month + monthsAhead, 0));

  return {
    first: first.toISOString().slice(0, 10),
    last: last.toISOString().slice(0, 10)
  };
}

/** Return a bare calendar day, spelled out.
 *
 * @param {string} day An ISO date.
 * @returns {string} Such as `September 1, 2026`.
 */
export function longDay(day) {
  const [year, month, date] = day.split('-').map(Number);

  return new Intl.DateTimeFormat('en-US', {
    timeZone: 'UTC',
    year: 'numeric',
    month: 'long',
    day: 'numeric'
  }).format(new Date(Date.UTC(year, month - 1, date)));
}
