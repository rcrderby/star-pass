/* Choosing a shift time.
 *
 * Fifteen-minute steps across the whole day, because that is the grain
 * shifts are actually set at and typing `18:37` into Amplify helps
 * nobody.  The full day rather than a range around the current value:
 * a shift moved from the evening to the morning is a real edit, and a
 * list that only offered nearby times would make it impossible.
 *
 * The keyboard does the same thing without opening anything: up and
 * down move by a step, Enter commits and closes.  That is what makes
 * the list a convenience rather than the only way in.
 */

import { el, icon } from '../dom.js';
import { closeAnyPopover, Popover } from '../popover.js';

/* The grain, in minutes, and what a day holds at that grain. */
const STEP = 15;
const IN_A_DAY = 24 * 60;

/* The design's width for the list. */
const WIDTH = 132;

/* The last time of day a shift can hold.  A shift cannot leave its
 * day: the service parses a time of day to 23:59 at the latest. */
const LAST_MINUTE = IN_A_DAY - 1;

/** Return a count of minutes as a clock reads it.
 *
 * @param {number} minutes Minutes since midnight.
 * @returns {string} `HH:MM`.
 */
function asClock(minutes) {
  const whole = ((minutes % IN_A_DAY) + IN_A_DAY) % IN_A_DAY;
  const hours = String(Math.floor(whole / 60)).padStart(2, '0');
  const rest = String(whole % 60).padStart(2, '0');

  return `${hours}:${rest}`;
}

/** Return a clock time as minutes since midnight.
 *
 * @param {string} clock `HH:MM`.
 * @returns {number|null} The minutes, or null when it is not a time.
 */
function asMinutes(clock) {
  const parts = /^(\d{1,2}):(\d{2})$/.exec(clock.trim());

  if (parts === null) {
    return null;
  }

  const hours = Number(parts[1]);
  const rest = Number(parts[2]);

  if (hours > 23 || rest > 59) {
    return null;
  }

  return (hours * 60) + rest;
}

/** Return every time the list offers.
 *
 * @returns {Array<string>} The whole day, a step apart.
 */
function everyStep() {
  const times = [];

  for (let minutes = 0; minutes < IN_A_DAY; minutes += STEP) {
    times.push(asClock(minutes));
  }

  return times;
}

/** Put the list where the time it is showing is, as it opens.
 *
 * Ninety-six options and nothing scrolling them leaves the list at
 * 00:00, so a field reading 19:15 would open on small hours with the
 * time it holds nineteen hours below the fold.
 *
 * Centred rather than brought to an edge: the steps either side of
 * the current time are what somebody opening this list wants.
 *
 * @param {HTMLElement} panel The list, once it is on the page.
 * @param {string} clock What the field says.
 * @returns {void}
 */
function showTime(panel, clock) {
  const minutes = asMinutes(clock);
  /* Rounded rather than floored, and clamped: the field can hold a
   * time the list does not offer, because the keyboard steps from
   * wherever it already was and because a time can be typed. That
   * opens on the step nearest it. */
  const index = Math.min(
    panel.children.length - 1,
    Math.max(0, Math.round((minutes === null ? 0 : minutes) / STEP))
  );
  const option = panel.children[index];

  if (option === undefined) {
    return;
  }

  panel.scrollTop = option.offsetTop
    - ((panel.clientHeight - option.offsetHeight) / 2);
}

/** Return where a shift's end goes when its start is moved onto it.
 *
 * A start set onto or past its end takes the end with it, so the
 * length survives: 19:00 to 20:00, with the start set to 20:00,
 * becomes 20:00 to 21:00.  A start still before the end moves
 * nothing.
 *
 * **A shift cannot leave its day.**  Where keeping the length would
 * carry the end past 23:59 this answers nothing, so the start is sent
 * alone and the service refuses it.  Clamping would silently change
 * the length.
 *
 * @param {string} shiftStart The start as it stands, `HH:MM`.
 * @param {string} shiftEnd The end as it stands.
 * @param {string} chosen The start that was chosen.
 * @returns {string|null} Where the end goes, or null when it does not
 *     move.
 */
export function endFollowing(shiftStart, shiftEnd, chosen) {
  const started = asMinutes(shiftStart);
  const ended = asMinutes(shiftEnd);
  const moving = asMinutes(chosen);

  if (started === null || ended === null || moving === null) {
    return null;
  }

  if (moving < ended) {
    return null;
  }

  const landing = moving + (ended - started);

  return landing > LAST_MINUTE ? null : asClock(landing);
}

/** Return a shift time field, and the list that opens beside it.
 *
 * @param {Object} options What it edits.
 * @param {string} options.value The time now, as `HH:MM`.
 * @param {string} options.label What the field is called.
 * @param {boolean} options.busy Whether an edit is in flight.
 * @param {Function} options.onChoose Called with the new time, once,
 *     when the reader has settled on one.
 * @returns {HTMLElement} The field and its list.
 */
export function timeField({ value, label, busy, onChoose }) {
  const field = el('input', {
    class: 'input mono',
    type: 'text',
    value,
    disabled: busy,
    'aria-label': label,
    autocomplete: 'off'
  });

  /* An edit is sent once per field. Choosing from the list fires on
   * mousedown, and the field's own blur follows it -- which would
   * send the same edit a second time, under a second key, and move
   * the shift twice. Whichever gets there first wins, and the screen
   * redraws over this field either way. */
  let sent = false;

  /** Send one edit from this field, and only one.
   *
   * @param {string} time What was chosen.
   * @returns {void}
   */
  function fire(time) {
    if (sent) {
      return;
    }

    sent = true;
    onChoose(time);
  }

  /** Commit what the field says, if it says something new and valid.
   *
   * @returns {void}
   */
  function commit() {
    const minutes = asMinutes(field.value);

    if (minutes === null) {
      /* Not a time: put back what it was rather than sending it. The
       * service would refuse it, and refusing it here says so without
       * a round trip. */
      field.value = value;

      return;
    }

    const chosen = asClock(minutes);

    if (chosen !== value) {
      fire(chosen);
    } else {
      field.value = chosen;
    }
  }

  /** Move the time by one step and show it, without committing.
   *
   * @param {number} steps How many steps, signed.
   * @returns {void}
   */
  function nudge(steps) {
    const from = asMinutes(field.value);

    field.value = asClock(
      (from === null ? 0 : from) + (steps * STEP)
    );
  }

  field.addEventListener('keydown', (event) => {
    if (event.key === 'ArrowUp' || event.key === 'ArrowDown') {
      event.preventDefault();
      nudge(event.key === 'ArrowUp' ? 1 : -1);
    } else if (event.key === 'Enter') {
      event.preventDefault();
      closeAnyPopover();
      commit();
    }
  });

  /* Leaving the field commits too: somebody who typed a time and
   * clicked elsewhere has finished with it. */
  field.addEventListener('blur', commit);

  const popover = new Popover({
    trigger: field,
    width: WIDTH,
    top: 40,
    bindClick: false,
    contents: () => everyStep().map((time) => el('button', {
      type: 'button',
      class: time === value ? 'time-option time-option-now' : 'time-option',
      text: time,
      /* Chosen before the field's own blur runs, so the click is what
       * commits rather than the value the field still held. */
      onmousedown: (event) => {
        event.preventDefault();
        closeAnyPopover();

        if (time !== value) {
          field.value = time;
          fire(time);
        }
      }
    }))
  });

  /* Focusing opens it, which is what the design asks: the field is
   * the trigger, so tabbing to it offers the list without a second
   * control to find. */
  if (!busy) {
    field.addEventListener('focus', () => {
      popover.show();
      showTime(popover.panel, field.value);
    });
  }

  /* The field opens a list on focus and said nothing about it: a
   * bordered box holding a time reads as a box to type a time into,
   * which it also is. The glyph is what says there is a list behind
   * it. Inside the anchor, which is already positioned, and taking
   * no pointer events so the field underneath keeps the click. */
  popover.element.classList.add('time-field');
  popover.element.append(icon('clock'));

  return popover.element;
}
