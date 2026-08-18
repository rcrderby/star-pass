/* What you can do to several rows at once.
 *
 * It replaces the ordinary toolbar rather than sitting beside it,
 * because while rows are selected the useful controls are these and
 * the search is not one of them.
 *
 * Every control here sends **one** operation naming every selected
 * event.  That is what the contract asks for and what makes a bulk
 * nudge safe: thirty events move together or none of them do, and the
 * change log gets one entry rather than thirty.
 */

import { el, icon } from '../dom.js';

/* How far the two nudges move a shift. The design's wording names the
 * number, so the two agree by construction. */
const NUDGE_MINUTES = 15;

/** Return the toolbar shown while rows are selected.
 *
 * @param {Object} state What the screen is showing.
 * @param {Array<Object>} categories What an event may be put under.
 * @param {Object} handlers What each control does.
 * @returns {HTMLElement} The toolbar.
 */
export function selectionToolbar(state, categories, handlers) {
  const chosen = state.selection.size;
  const busy = state.busy;

  const chooser = el(
    'select',
    {
      class: 'input',
      disabled: busy,
      'aria-label': 'Set the opportunity for every selected event',
      onchange: (event) => {
        const category = event.target.value;

        /* Put back to the prompt straight away: the control names an
         * action rather than a state, and leaving it showing the last
         * category would read as "these are all that". */
        event.target.value = '';

        if (category !== '') {
          handlers.onSetCategory(category);
        }
      }
    },
    el('option', { value: '', text: 'Set opportunity for all' }),
    categories.map((category) => el('option', {
      value: category.key,
      text: category.label
    }))
  );

  return el(
    'div',
    { class: 'toolbar toolbar-selection card elev-sm', role: 'toolbar' },
    el('span', {
      class: 'selection-count',
      text: `${chosen} selected`
    }),
    chooser,
    el(
      'button',
      {
        type: 'button',
        class: 'btn btn-secondary',
        disabled: busy,
        onclick: () => handlers.onNudge(-NUDGE_MINUTES)
      },
      icon('arrow-left'),
      `${NUDGE_MINUTES} min earlier`
    ),
    el(
      'button',
      {
        type: 'button',
        class: 'btn btn-secondary',
        disabled: busy,
        onclick: () => handlers.onNudge(NUDGE_MINUTES)
      },
      `${NUDGE_MINUTES} min later`,
      icon('arrow-right')
    ),
    el(
      'button',
      {
        type: 'button',
        class: 'btn btn-secondary',
        disabled: busy,
        title: 'Put every role back to what its opportunity asks for',
        onclick: handlers.onResetSlots
      },
      icon('arrow-counter-clockwise'),
      'Usual slots'
    ),
    el(
      'button',
      {
        type: 'button',
        class: 'btn btn-secondary btn-danger',
        disabled: busy,
        onclick: handlers.onRemove
      },
      icon('trash'),
      'Remove'
    ),
    el(
      'button',
      {
        type: 'button',
        class: 'btn btn-ghost selection-clear',
        onclick: handlers.onClear
      },
      'Clear selection'
    )
  );
}
