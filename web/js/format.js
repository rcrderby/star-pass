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

/** Return a length in minutes as the table shows it.
 *
 * @param {number} minutes How long the shift lasts.
 * @returns {string} Such as `60 min`.
 */
export function lengthText(minutes) {
  return `${minutes} min`;
}
