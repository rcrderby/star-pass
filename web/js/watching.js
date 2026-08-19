/* How a screen follows a job.
 *
 * Two screens do it -- a collection and a send -- and they do it
 * identically, because what differs between them is what the frames
 * mean rather than how they arrive.  The stream is reattachable, so
 * either screen can be opened against a job it did not start and be
 * given the whole log from the first frame; that is what makes
 * "leave this running" a real offer rather than a hope.
 *
 * Below both of them, because a second copy would be a second place
 * to remember that the connection dropping is not the job failing.
 */

import { followJob } from './api.js';

/** Follow one job, reporting what it says into a screen.
 *
 * @param {Object} job The job, as the service reports it.
 * @param {Object} screen What to tell. It supplies three methods:
 *     `reported(kind, payload)` for each frame the job wrote,
 *     `finished(ending)` for the frame that says how it ended, and
 *     `lost()` for a connection the browser is quietly retrying --
 *     which is not the job failing, and must never be drawn as one.
 * @returns {EventSource} The stream, for a screen that wants to stop
 *     following before the job is over.
 */
export function watchJob(job, screen) {
  return followJob(job.id, {
    onEvent: (kind, payload) => screen.reported(kind, payload),
    onFinished: (ending) => screen.finished(ending),
    onLost: () => screen.lost()
  });
}
