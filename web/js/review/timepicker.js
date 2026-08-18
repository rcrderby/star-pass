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

import { el } from '../dom.js';
import { closeAnyPopover, Popover } from '../popover.js';

/* The grain, in minutes, and what a day holds at that grain. */
const STEP = 15;
const IN_A_DAY = 24 * 60;

/* The design's width for the list. */
const WIDTH = 132;

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
    field.addEventListener('focus', () => popover.show());
  }

  return popover.element;
}
