/* What sending this run would create, before it does.
 *
 * **The preview is the duplicate check.**  The design draws them as
 * two things -- a table, and a spinner beside the send button saying
 * Amplify is being asked -- because the prototype worked the totals
 * out in the page and then went looking for what already existed.
 * One request answers both here: every opportunity the revision
 * touches is read from Amplify while the preview is built, so
 * `willCreate` is already net of what Amplify holds and `skipped`
 * names each row that will not arrive.  So the spinner is this
 * request being in flight, and "Check again" asks for the preview
 * again.
 *
 * Nothing on this screen is worked out from the events.  Every figure
 * is the server's -- counted by shift identity rather than by rows,
 * grouped by Amplify opportunity rather than by category, and net of
 * a live read.  A second implementation of any of it would be a
 * screen that could disagree with the send about what is about to
 * happen.
 */

import { el, icon } from '../dom.js';
import { shortDay } from '../format.js';
import { phrase } from '../phrases.js';

/* The columns, in the order the design gives them. */
const HEADERS = ['Opportunity', 'New shifts', 'Slots', 'Dates'];

/* What the row's date cell says when a send would create nothing
 * under this opportunity, which is what an opportunity Amplify
 * already holds every shift for looks like. */
const NOTHING_LEFT = 'nothing left to create';

/* Said under the table, always, and last: it is the whole reason the
 * confirmation exists. */
const NO_UNDO = (
  'Amplify has no undo. Shifts created here have to be removed in '
  + 'Amplify by hand.'
);

/* While the preview is being read, and when it could not be. */
const CHECKING = 'Checking Amplify first';
const CHECK_FAILED = (
  'Amplify did not answer the check for shifts that already exist, so '
  + 'sending is held back.'
);

/* When the run asks for nothing Amplify does not already have. Its
 * own sentence rather than a disabled button with no explanation,
 * because it is the one blocked state that is not a fault. */
const NOTHING_TO_SEND = (
  'Every shift in this run is already in Amplify. There is nothing '
  + 'left to send.'
);

/** Return a count with its noun, singular where it should be.
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

/** Return the days a row's new shifts fall on.
 *
 * @param {Object} row One preview row.
 * @returns {string} One day, a span, or what an empty row says.
 */
function datesText(row) {
  if (row.firstDate === null || row.lastDate === null) {
    return NOTHING_LEFT;
  }

  return row.firstDate === row.lastDate
    ? shortDay(row.firstDate)
    : `${shortDay(row.firstDate)} to ${shortDay(row.lastDate)}`;
}

/** Return the note under an opportunity naming what it already holds.
 *
 * @param {Object} row One preview row.
 * @returns {HTMLElement|null} The note, or nothing to say.
 */
function skippedNote(row) {
  if (row.alreadyInAmplify === 0) {
    return null;
  }

  const shifts = counted(row.alreadyInAmplify, 'identical shift');
  const verb = row.alreadyInAmplify === 1 ? 'is' : 'are';

  return el('span', {
    class: 'preview-existing note',
    text: `${shifts} ${verb} already in Amplify, so `
      + `${row.alreadyInAmplify === 1 ? 'it' : 'they'} will be skipped`
  });
}

/** Return one opportunity's row.
 *
 * @param {Object} row One preview row.
 * @returns {HTMLElement} The row.
 */
function previewRow(row) {
  return el(
    'tr',
    {},
    el(
      'td',
      {},
      el(
        'span',
        { class: 'preview-opportunity' },
        el('span', { text: row.title === null ? row.needId : row.title }),
        skippedNote(row)
      )
    ),
    el('td', { class: 'mono', text: String(row.willCreate) }),
    el('td', { class: 'mono', text: String(row.slots) }),
    el('td', { class: 'mono muted', text: datesText(row) })
  );
}

/** Return the sentence under the heading.
 *
 * Says what a send would do and everything that changes that number,
 * in one place, because the table below it is grouped by opportunity
 * and a reader counting rows would not arrive at the same figure.
 *
 * @param {Object} preview What the service answered.
 * @returns {string} The line.
 */
export function summaryLine(preview) {
  const { totals, rows } = preview;
  const parts = [
    `${counted(totals.willCreate, 'shift')} across `
    + `${counted(rows.length, 'opportunity', 'opportunities')}.`
  ];

  if (totals.blockingEvents) {
    const events = counted(totals.blockingEvents, 'event');
    const verb = totals.blockingEvents === 1 ? 'is' : 'are';

    parts.push(
      `${events} cannot become a shift, so nothing ${verb} sent `
      + 'until that is fixed.'
    );
  }

  if (totals.alreadyInAmplify) {
    const shifts = counted(totals.alreadyInAmplify, 'shift');
    const verb = totals.alreadyInAmplify === 1 ? 'is' : 'are';

    parts.push(`${shifts} ${verb} already in Amplify and left out.`);
  }

  if (totals.repeatedRows) {
    const rowsAsked = counted(totals.repeatedRows, 'shift');
    const verb = totals.repeatedRows === 1 ? 'is' : 'are';

    parts.push(`${rowsAsked} ${verb} asked for twice and created once.`);
  }

  return parts.join(' ');
}

/** Return why the send button is not available.
 *
 * Reasons are the ones the preview published, worded here and grouped
 * so that three events missing an opportunity is one clause rather
 * than three.
 *
 * @param {Object} preview What the service answered.
 * @returns {string} The line, or an empty string when nothing blocks.
 */
export function blockedReason(preview) {
  if (preview.totals.blockingEvents === 0) {
    return preview.totals.willCreate === 0 ? NOTHING_TO_SEND : '';
  }

  const byReason = new Map();

  for (const blocker of preview.blockers) {
    byReason.set(blocker.reason, (byReason.get(blocker.reason) || 0) + 1);
  }

  return [...byReason]
    .map(([reason, count]) => {
      const events = counted(count, 'event');

      return `${events} with ${phrase('blocker', reason)}`;
    })
    .join(', ');
}

/* What a line of the Checks card can be. **A finding is not a
 * fault**: a shift Amplify already holds, a row asked for twice and a
 * length an opportunity shortened are all things a reader should be
 * told and none of them is wrong. Drawn as problems, they would put
 * three warnings on a card describing a run with nothing the matter
 * with it, and the two that *are* problems would stop standing out. */
const GOOD = { class: 'check', glyph: 'check-circle' };
const NOTED = { class: 'check check-noted', glyph: 'info' };
const BAD = { class: 'check check-bad', glyph: 'warning-circle' };

/** Return one line of the Checks card.
 *
 * @param {Object} kind One of `GOOD`, `NOTED` or `BAD`.
 * @param {string} words What it says.
 * @param {string} [glyph] An icon of its own, where the kind's is not
 *     the one the design gives this line.
 * @returns {HTMLElement} The line.
 */
function check(kind, words, glyph = null) {
  return el(
    'span',
    { class: kind.class },
    icon(glyph === null ? kind.glyph : glyph),
    el('span', { text: words })
  );
}

/** Return what the Checks card says, in the design's order.
 *
 * Each is stated whichever way it came out. A card that listed only
 * problems would be a card a reader could not tell from one that had
 * not finished.
 *
 * @param {Object} preview What the service answered.
 * @param {Object} run The run, for the two figures the preview does
 *     not carry: shortened shifts and the changes made in review.
 * @returns {Array<HTMLElement>} The lines.
 */
export function checks(preview, run) {
  const { totals } = preview;
  const endsFirst = preview.blockers.filter(
    (blocker) => blocker.reason === 'ends_before_start'
  ).length;
  const capped = run.events.filter(
    (event) => event.cappedAt !== null
  ).length;
  const changes = run.log.filter(
    (entry) => entry.revision === run.currentRevision
  ).length;

  return [
    totals.alreadyInAmplify === 0
      ? check(GOOD, 'None of these shifts is in Amplify yet')
      : check(
        NOTED,
        `${totals.alreadyInAmplify} of these shifts `
        + `${totals.alreadyInAmplify === 1 ? 'is' : 'are'} already in `
        + 'Amplify and will be skipped'
      ),
    totals.blockingEvents === 0
      ? check(GOOD, 'Every event can become a shift')
      : check(
        BAD,
        `${counted(totals.blockingEvents, 'event')} cannot become a shift`
      ),
    endsFirst === 0
      ? check(GOOD, 'Every shift ends after it starts')
      : check(
        BAD,
        `${counted(endsFirst, 'shift')} `
        + `${endsFirst === 1 ? 'ends' : 'end'} before `
        + `${endsFirst === 1 ? 'it starts' : 'they start'}`
      ),
    totals.repeatedRows === 0
      ? check(GOOD, 'No repeated rows')
      : check(
        NOTED,
        `${counted(totals.repeatedRows, 'repeated row')} will be `
        + 'created once, not twice',
        'copy'
      ),
    capped === 0
      ? check(GOOD, 'Every shift fits the length its opportunity allows')
      : check(
        NOTED,
        `${counted(capped, 'shift')} will be created shorter than `
        + `${capped === 1 ? 'its' : 'their'} calendar length, to fit `
        + `${capped === 1 ? 'its' : 'their'} opportunity`
      ),
    check(
      GOOD,
      `${counted(changes, 'change')} recorded in this review`,
      'clock-counter-clockwise'
    )
  ];
}

/** Return the card beside the table.
 *
 * @param {Object} preview What the service answered.
 * @param {Object} run The run being previewed.
 * @returns {HTMLElement} The card.
 */
export function checksCard(preview, run) {
  return el(
    'div',
    { class: 'card elev-sm' },
    el('span', { class: 'card-kicker muted', text: 'Checks' }),
    el('div', { class: 'checks' }, checks(preview, run))
  );
}

/** Return the table of what each opportunity would receive.
 *
 * @param {Object} preview What the service answered.
 * @returns {HTMLElement} The table, or what stands in for an empty one.
 */
export function previewTable(preview) {
  if (preview.rows.length === 0) {
    return el('p', {
      class: 'muted meta',
      text: 'This run asks for no shifts at all.'
    });
  }

  return el(
    'table',
    { class: 'table preview-table' },
    el(
      'thead',
      {},
      el(
        'tr',
        {},
        HEADERS.map((heading) => el('th', { text: heading }))
      )
    ),
    el('tbody', {}, preview.rows.map(previewRow))
  );
}

/** Return the row of controls under the table.
 *
 * The button says the number, which is the number the confirmation
 * restates and the number `expectedShiftCount` carries: one figure,
 * said three times, so that what somebody clicks is what the service
 * checks.
 *
 * @param {Object} state What the screen is showing.
 * @param {Object} handlers What its controls do.
 * @returns {HTMLElement} The controls.
 */
export function previewActions(state, handlers) {
  const { preview, reading, failure } = state;
  const willCreate = preview === null ? 0 : preview.totals.willCreate;
  const reason = preview === null ? '' : blockedReason(preview);

  return el(
    'div',
    { class: 'preview-actions' },
    el(
      'button',
      {
        type: 'button',
        class: 'btn btn-primary',
        disabled: preview === null || willCreate === 0 || reason !== '',
        onclick: handlers.onConfirm
      },
      icon('paper-plane-tilt'),
      willCreate === 0
        ? 'Send to Amplify'
        : `Send ${counted(willCreate, 'shift')} to Amplify`
    ),
    el(
      'button',
      {
        type: 'button',
        class: 'btn btn-secondary',
        onclick: handlers.onBack
      },
      'Back to review'
    ),
    reading
      ? el(
        'span',
        { class: 'muted meta checking' },
        icon('circle-notch'),
        el('span', { text: CHECKING })
      )
      : null,
    failure === null
      ? null
      : el(
        'span',
        { class: 'preview-failed meta' },
        icon('warning-circle'),
        el('span', { text: CHECK_FAILED }),
        failure.reference
          ? el('span', { class: 'mono micro', text: failure.reference })
          : null,
        el(
          'button',
          {
            type: 'button',
            class: 'btn btn-secondary',
            onclick: handlers.onReread
          },
          icon('arrows-clockwise'),
          'Check again'
        )
      ),
    reason === ''
      ? null
      : el(
        'span',
        { class: 'preview-blocked meta' },
        icon('warning-circle'),
        el('span', { text: reason })
      ),
    el('span', { class: 'preview-warning muted meta', text: NO_UNDO })
  );
}
