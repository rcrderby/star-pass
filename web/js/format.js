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

  return new Intl.DateTimeFormat('en-US', {
    timeZone,
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit'
  }).format(new Date(when));
}
