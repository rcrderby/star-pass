/* The only way this page talks to anything.
 *
 * It reaches `/api` on its own origin and nothing else.  The frontend
 * attaches the Amplify-holding service's credential on the way past;
 * this page holds none and must never be given one (D4).
 *
 * Three things are this module's alone, so that no screen has to
 * remember them:
 *
 *   - A write carries the `star_pass_csrf` cookie's value in the
 *     `X-Star-Pass-CSRF` header.  Together with the session cookie
 *     being SameSite=Strict and the frontend checking the origin, that
 *     is what says a write came from this page (D18).
 *   - Four operations require an `Idempotency-Key`, and the key names
 *     one thing somebody did.  A retry of the same action sends the
 *     same key and is answered with the original result rather than
 *     writing twice; a new action mints a new one.
 *   - A failure arrives as a problem document (RFC 9457).  Below 500 it
 *     carries a reason the caller can act on, and at 500 and above it
 *     deliberately does not -- the reason is in the service's log under
 *     the same reference, because an internal failure can carry a
 *     credential or a volunteer's name.
 *
 * Only headers on the frontend's allowlist reach the API: `accept`,
 * `content-type` and `idempotency-key`.  Nothing else a page sets is
 * forwarded, so setting one here would be setting it nowhere.
 */

/* Where the API is, from this page.  Same origin, which is why there
 * is no CORS configuration anywhere in the system. */
const BASE = '/api/v1';

const CSRF_COOKIE = 'star_pass_csrf';
const CSRF_HEADER = 'X-Star-Pass-CSRF';
const IDEMPOTENCY_HEADER = 'Idempotency-Key';

const JSON_MEDIA_TYPE = 'application/json';
const PROBLEM_MEDIA_TYPE = 'application/problem+json';

/* At and above this, a problem document carries no reason on purpose. */
const OPAQUE_FROM = 500;

/* What a job's stream can send.  Server-sent events are delivered by
 * name and there is no way to listen for all of them, so a client
 * that wants a frame has to say which -- these are the reporting
 * methods the core describes its work through, which is what the
 * command line's own reader lists for the same reason. A kind absent
 * here is a kind no screen would see. */
const STREAM_EVENTS = [
  'step_started',
  'step_finished',
  'step_failed',
  'sending_started',
  'opportunity_sent'
];

/* The frame that ends a stream. Named unlike any of the job's own
 * events, and the only one that is not something the job reported:
 * it says how the job ended. */
const JOB_FINISHED = 'job_finished';

/* What to say when the service could not be reached at all, which is a
 * different thing from the service refusing: nothing answered, so
 * there is no reference to quote and nothing to look up. */
const UNREACHABLE = (
  'The star-pass page could not reach the service. It may be '
  + 'restarting; try again in a moment.'
);

/* What to say when something answered but not with a problem document.
 * Worth its own sentence rather than showing the raw body: what comes
 * back in that case is a proxy error page, not something to read. */
const UNREADABLE = 'The service answered in a way this page could not read.';

/**
 * A request the service refused, or could not answer.
 *
 * Carries what the problem document held, so a screen can show the
 * detail where there is one and the reference either way. The
 * reference is the whole point of the class: at 500 and above it is
 * the only thing connecting what somebody saw to what was logged.
 */
export class ApiError extends Error {
  /**
   * @param {Object} fields What the document held.
   * @param {number} fields.status HTTP status, or 0 when nothing
   *     answered.
   * @param {string} fields.detail What to show. Already safe to
   *     display: the service replaces the reason with a fixed sentence
   *     on the statuses where the reason is not the caller's to see.
   * @param {string} [fields.title] Short summary of the problem type.
   * @param {string} [fields.reference] What to quote when reporting it.
   * @param {number} [fields.retryAfter] Seconds to wait, when the
   *     service said.
   */
  constructor({ status, detail, title = '', reference = '', retryAfter = 0 }) {
    super(detail);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
    this.title = title;
    this.reference = reference;
    this.retryAfter = retryAfter;
  }

  /** Whether the reason was withheld, and only the reference is real.
   *
   * @returns {boolean} Whether this is one of those.
   */
  get isOpaque() {
    return this.status >= OPAQUE_FROM;
  }
}

/** Return the value of one cookie this page can read.
 *
 * The session cookie is httpOnly and is deliberately not reachable
 * here; the token derived from it is the readable one, which is the
 * whole shape of D18.
 *
 * @param {string} name Cookie to read.
 * @returns {string} Its value, or an empty string when there is none.
 */
function cookie(name) {
  const wanted = `${name}=`;

  for (const entry of document.cookie.split(';')) {
    const trimmed = entry.trim();

    if (trimmed.startsWith(wanted)) {
      return decodeURIComponent(trimmed.slice(wanted.length));
    }
  }

  return '';
}

/** Return a key naming one thing somebody did.
 *
 * Minted per action rather than per request, so that the retry of a
 * send is the same action and a second send is not.
 *
 * @returns {string} A fresh key.
 */
export function idempotencyKey() {
  return crypto.randomUUID();
}

/** Return what a failed response meant.
 *
 * @param {Response} response What came back.
 * @returns {Promise<ApiError>} The failure, shaped for a screen.
 */
async function failure(response) {
  const retryAfter = Number(response.headers.get('retry-after')) || 0;
  const type = response.headers.get('content-type') || '';

  if (!type.startsWith(PROBLEM_MEDIA_TYPE)) {
    return new ApiError({
      status: response.status,
      detail: UNREADABLE,
      retryAfter
    });
  }

  let document_ = {};

  try {
    document_ = await response.json();
  } catch {
    return new ApiError({
      status: response.status,
      detail: UNREADABLE,
      retryAfter
    });
  }

  return new ApiError({
    status: response.status,
    detail: document_.detail || UNREADABLE,
    title: document_.title || '',
    reference: document_.reference || '',
    retryAfter
  });
}

/** Ask the API for something, and return what it said.
 *
 * @param {string} path Below `/api/v1`, starting with a slash.
 * @param {Object} [options] How to ask.
 * @param {string} [options.method] Defaults to a read.
 * @param {Object} [options.body] Sent as JSON when there is one.
 * @param {string} [options.key] The `Idempotency-Key` for the four
 *     operations that require one. Nothing else should pass it.
 * @param {AbortSignal} [options.signal] For abandoning the request.
 * @throws {ApiError} When the service refused, could not answer, or
 *     could not be reached.
 * @returns {Promise<Object|null>} The answer, or null when it carried
 *     no body.
 */
export async function ask(path, options = {}) {
  const { method = 'GET', body = null, key = '', signal = null } = options;
  const headers = { accept: `${JSON_MEDIA_TYPE}, ${PROBLEM_MEDIA_TYPE}` };

  if (body !== null) {
    headers['content-type'] = JSON_MEDIA_TYPE;
  }

  if (method !== 'GET' && method !== 'HEAD') {
    headers[CSRF_HEADER] = cookie(CSRF_COOKIE);
  }

  if (key) {
    headers[IDEMPOTENCY_HEADER] = key;
  }

  let response;

  try {
    response = await fetch(`${BASE}${path}`, {
      method,
      headers,
      signal,
      body: body === null ? null : JSON.stringify(body),
      /* The session cookie rides on this. Same origin, so it would be
       * sent anyway; said out loud because it is the one thing that
       * makes the request identifiable. */
      credentials: 'same-origin'
    });
  } catch (error) {
    if (error.name === 'AbortError') {
      throw error;
    }

    throw new ApiError({ status: 0, detail: UNREACHABLE });
  }

  if (!response.ok) {
    throw await failure(response);
  }

  if (response.status === 204 || response.status === 205) {
    return null;
  }

  return response.json();
}

/** Return every run the service holds.
 *
 * @param {Object} [options] Passed through to the request.
 * @returns {Promise<Array<Object>>} The runs, as the contract lists
 *     them.
 */
export function listRuns(options = {}) {
  return ask('/runs', options);
}

/** Return one run, with its events, opportunities and change log.
 *
 * One request rather than several: the review screen is a reading of
 * this answer, and a screen assembled from three would show a run
 * whose parts were read at three different moments.
 *
 * @param {string} runId Which run.
 * @param {Object} [options] Passed through to the request.
 * @returns {Promise<Object>} The run in full.
 */
export function getRun(runId, options = {}) {
  return ask(`/runs/${encodeURIComponent(runId)}`, options);
}

/** Return the run's revisions, newest last.
 *
 * @param {string} runId Which run.
 * @param {Object} [options] Passed through to the request.
 * @returns {Promise<Array<Object>>} The revisions.
 */
export function listRevisions(runId, options = {}) {
  return ask(`/runs/${encodeURIComponent(runId)}/revisions`, options);
}

/** Fix what a run holds now as a numbered revision.
 *
 * Editing changes the revision a run is working in as it goes, so
 * this is what makes a point in that work something to come back to.
 * Nothing is deleted: the revision that was current keeps its rows
 * and stays readable at its own number, and the work moves to a new
 * one holding a copy.
 *
 * The key names this seal. Sealing is not idempotent in itself --
 * twice is two revisions -- so a retry after a lost answer is given
 * the first answer rather than opening a second one.
 *
 * @param {string} runId Which run.
 * @param {string} key The `Idempotency-Key` naming this seal.
 * @param {Object} [options] Passed through to the request.
 * @returns {Promise<Object>} The revision now being worked in.
 */
export function sealRevision(runId, key, options = {}) {
  return ask(`/runs/${encodeURIComponent(runId)}/revisions`, {
    ...options,
    method: 'POST',
    key
  });
}

/** Put a run back to what one of its earlier revisions holds.
 *
 * **One revision per revert**, and nothing between the two is
 * touched, so a revert can itself be reverted. Answers with the run
 * in full, because every row on the screen that asked has changed.
 *
 * The key remembers which revision was asked for: sent again naming a
 * different one it is refused rather than answered from the first.
 *
 * @param {string} runId Which run.
 * @param {number} number Revision to go back to the contents of.
 * @param {string} key The `Idempotency-Key` naming this revert.
 * @param {Object} [options] Passed through to the request.
 * @returns {Promise<Object>} The run as it now is.
 */
export function revertRevision(runId, number, key, options = {}) {
  const run = encodeURIComponent(runId);

  return ask(
    `/runs/${run}/revisions/${encodeURIComponent(number)}/revert`,
    { ...options, method: 'POST', key }
  );
}

/** Return what this deployment was configured with.
 *
 * Read for the categories each calendar offers, which is what an
 * event may be put under and is not derivable from a run: a run holds
 * the opportunities its own events reached, and the event that needs
 * the list is the one that matched nothing.
 *
 * @param {Object} [options] Passed through to the request.
 * @returns {Promise<Object>} The configuration.
 */
export function getConfig(options = {}) {
  return ask('/config', options);
}

/** Apply one thing somebody did to a run's current revision.
 *
 * **One call per user action, not per event.** A nudge over thirty
 * selected rows is one operation naming thirty, which the service
 * applies whole or not at all and records as one log entry. Thirty
 * calls would be thirty entries, thirty keys, and a half-applied
 * action if one of them failed.
 *
 * The key names the action. A second arrival of the same key with the
 * same request is answered with what the first one answered rather
 * than writing again; the same key carrying a *different* request is
 * refused, and a key whose first request has not finished yet is a
 * conflict. So a key is minted per action and never reused for the
 * next one -- two nudges are two actions and must move the shift
 * twice.
 *
 * @param {string} runId Which run.
 * @param {Array<Object>} operations What to do, in order.
 * @param {string} key The `Idempotency-Key` naming this action.
 * @param {Object} [options] Passed through to the request.
 * @returns {Promise<Object>} The revision as it now is, and the
 *     entries the edit added to the change log.
 */
export function editEvents(runId, operations, key, options = {}) {
  return ask(`/runs/${encodeURIComponent(runId)}/events`, {
    ...options,
    method: 'PATCH',
    body: { operations },
    key
  });
}

/** Return what a run's window held and the run did not collect.
 *
 * Grouped by the reason each was left out, and a reason nothing was
 * left out for is not among them. Answered from what the collection
 * stored rather than from a calendar read, so it describes the window
 * as the collection found it.
 *
 * @param {string} runId Which run.
 * @param {Object} [options] Passed through to the request.
 * @returns {Promise<Array<Object>>} One group per reason.
 */
export function listUncollected(runId, options = {}) {
  return ask(`/runs/${encodeURIComponent(runId)}/uncollected`, options);
}

/** Pull one event the search missed into a run's current revision.
 *
 * **No `Idempotency-Key`, and none is needed**: naming an event the
 * revision already holds is refused, so a second arrival of the same
 * request is a refusal rather than a second row.
 *
 * Only an event the uncollected list marks `addable` may be named.
 * That is the server's answer and not a client's reading of the
 * reason, so a button and the endpoint behind it cannot disagree.
 *
 * @param {string} runId Which run.
 * @param {string} uncollectedId The identifier its uncollected entry
 *     carries, which is the calendar's own.
 * @param {Object} [options] Passed through to the request.
 * @returns {Promise<Object>} The revision as it now is, and what the
 *     pull-in added to the change log.
 */
export function addEvent(runId, uncollectedId, options = {}) {
  return ask(`/runs/${encodeURIComponent(runId)}/events`, {
    ...options,
    method: 'POST',
    body: { uncollectedId }
  });
}

/** Return every title the data model has not matched.
 *
 * Belongs to no run: a run is a window that is eventually superseded,
 * and what the model is missing outlives it. So this is read beside a
 * run rather than out of one.
 *
 * @param {Object} [options] Passed through to the request.
 * @returns {Promise<Array<Object>>} One entry per title in a calendar,
 *     newest sighting first.
 */
export function listUnmatchedTitles(options = {}) {
  return ask('/unmatched-titles', options);
}

/** Record one sighting of a title the data model did not match.
 *
 * The calendar is part of what a title *is* rather than a note beside
 * it: the categories a title is matched against belong to a calendar,
 * so the same title can be matched in one and unmatched in another.
 * The run is provenance, and the log outlives it.
 *
 * No key here either. A run is held to one sighting of a title by the
 * repository, so asking twice from the same run adds nothing.
 *
 * @param {string} calendar Which configured calendar it was seen in.
 * @param {string} title The title, as the calendar gave it.
 * @param {string} runId The run it was noticed in.
 * @param {Object} [options] Passed through to the request.
 * @returns {Promise<Object>} The entry as the log now holds it.
 */
export function recordUnmatchedTitle(calendar, title, runId, options = {}) {
  return ask('/unmatched-titles', {
    ...options,
    method: 'POST',
    body: { calendar, title, runId }
  });
}

/** Ask for a calendar window to be collected into a new run.
 *
 * Answers with a job as soon as the run exists rather than when it
 * has been filled: reading a calendar and naming every opportunity it
 * finds takes longer than a request should be held open. The run is
 * in the list from that moment, so somebody who closed the page can
 * find it again.
 *
 * **No `Idempotency-Key`, deliberately**, so nothing here makes a
 * second arrival of the same request safe: two would be two runs.
 * Preventing that is the screen's job, and the screen does it by
 * refusing to have two of these in the air at once.
 *
 * The window's `end` is the day **after** the last day to cover. No
 * request takes an inclusive day, which is why the caller converts.
 *
 * @param {string} calendar Which configured calendar to read.
 * @param {Object} window The days to cover.
 * @param {string} window.start First day, as an ISO date.
 * @param {string} window.end Day after the last, as an ISO date.
 * @param {Object} [options] Passed through to the request.
 * @returns {Promise<Object>} The job doing the collection.
 */
export function collectRun(calendar, window, options = {}) {
  return ask('/runs', {
    ...options,
    method: 'POST',
    body: { calendar, window }
  });
}

/** Ask for a run to be collected again, replacing what it holds.
 *
 * `expectedChangeCount` is how many changes the operator was told
 * would be discarded. The service refuses when that is no longer the
 * number the run holds, which closes the case of a tab left open
 * while the run was edited somewhere else.
 *
 * Takes no `Idempotency-Key` either, for the same reason and with the
 * same answer.
 *
 * @param {string} runId Which run to replace.
 * @param {number} expectedChangeCount What the operator was shown.
 * @param {Object} [options] Passed through to the request.
 * @returns {Promise<Object>} The job doing the collection.
 */
export function recollectRun(runId, expectedChangeCount, options = {}) {
  return ask(`/runs/${encodeURIComponent(runId)}/recollect`, {
    ...options,
    method: 'POST',
    body: { expectedChangeCount }
  });
}

/** Return what sending this run's current revision would create.
 *
 * **This request is the duplicate check.** Every opportunity the
 * revision touches is read from Amplify while it is answered, so the
 * totals are net of what Amplify already holds and `skipped` names
 * every row that will not arrive. Nothing here works that out; the
 * design's separate "checking Amplify" step is this call.
 *
 * @param {string} runId Which run.
 * @param {Object} [options] Passed through to the request.
 * @returns {Promise<Object>} The preview.
 */
export function getPreview(runId, options = {}) {
  return ask(`/runs/${encodeURIComponent(runId)}/preview`, options);
}

/** Ask for this run's shifts to be created in Amplify.
 *
 * Answers with a job as soon as one exists, rather than when the
 * shifts have been created: a send is minutes of upstream requests
 * and the browser is not what holds it open.
 *
 * `expectedShiftCount` is the preview's `totals.willCreate` -- the
 * number the confirmation restated (D11). The service refuses when it
 * no longer matches what a send would create, which is what closes
 * the case of a tab left open while the run was edited or Amplify
 * gained a shift.
 *
 * @param {string} runId Which run.
 * @param {number} expectedShiftCount What the operator was shown.
 * @param {string} key The `Idempotency-Key` naming this attempt.
 * @param {Object} [options] Passed through to the request.
 * @returns {Promise<Object>} The job doing it.
 */
export function sendRun(runId, expectedShiftCount, key, options = {}) {
  return ask(`/runs/${encodeURIComponent(runId)}/send`, {
    ...options,
    method: 'POST',
    body: { expectedShiftCount },
    key
  });
}

/** Return where a job has got to.
 *
 * Read when a screen picks up a job it did not start -- a reload
 * during a send, or a run whose `activeJobId` says something is still
 * working on it.
 *
 * @param {string} jobId Which job.
 * @param {Object} [options] Passed through to the request.
 * @returns {Promise<Object>} The job.
 */
export function getJob(jobId, options = {}) {
  return ask(`/jobs/${encodeURIComponent(jobId)}`, options);
}

/** Follow what a job reports, until it is over.
 *
 * An `EventSource` rather than polling: the service holds the
 * connection open and the frontend passes it through unbuffered, so a
 * frame arrives when the job writes it.
 *
 * **Reattachable, and that is what "leave this running" means.** A
 * browser that opens this stream with no history is sent the job's
 * whole event log from the first frame, because a client that is not
 * resuming names no last event. So a reload during a send is
 * answered with everything it missed rather than with whatever
 * happens next, and a screen rebuilt from it knows as much as one
 * that never went away. A browser that *is* resuming sends
 * `Last-Event-ID` itself.
 *
 * The stream is closed here when the job's own last frame arrives.
 * Left open, the connection would end anyway and the browser would
 * reconnect to a job that has nothing further to say, forever.
 *
 * @param {string} jobId Which job.
 * @param {Object} handlers What to do with what arrives.
 * @param {Function} handlers.onEvent Called with the name of each
 *     frame and what it carried.
 * @param {Function} handlers.onFinished Called with the job's last
 *     frame: its identifier, status and detail.
 * @param {Function} handlers.onLost Called when the connection
 *     dropped and the browser is retrying, so a screen can say so.
 * @returns {EventSource} The stream, for a caller that wants to stop
 *     following before it ends.
 */
export function followJob(jobId, handlers) {
  const source = new EventSource(
    `${BASE}/jobs/${encodeURIComponent(jobId)}/events`
  );

  for (const kind of STREAM_EVENTS) {
    source.addEventListener(kind, (frame) => {
      handlers.onEvent(kind, JSON.parse(frame.data));
    });
  }

  source.addEventListener(JOB_FINISHED, (frame) => {
    source.close();
    handlers.onFinished(JSON.parse(frame.data));
  });

  source.addEventListener('error', () => {
    /* Not necessarily a failure: the browser reconnects on its own
     * and says nothing while it does. Reported so a screen can stop
     * looking live, and never treated as the end of the job -- what
     * ends a job is the job saying so. */
    if (source.readyState !== EventSource.CLOSED) {
      handlers.onLost();
    }
  });

  return source;
}
