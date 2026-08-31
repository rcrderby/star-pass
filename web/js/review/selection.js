/* What you can do to several rows at once.
 *
 * It sits under the ordinary toolbar rather than in place of it, so
 * the search stays reachable while rows are selected: narrowing the
 * table to find the few rows to spare, and unchecking them, is how a
 * selection of everything becomes a selection of most things.
 *
 * That is also why the count says how many selected rows are **not**
 * on screen.  Every control here acts on the whole selection, and a
 * search that hides two thirds of it would otherwise leave a Remove
 * button standing over three rows and taking away thirty.
 *
 * Every control here sends **one** operation naming every selected
 * event.  That is what the contract asks for and what makes a bulk
 * nudge safe: thirty events move together or none of them do, and the
 * change log gets one entry rather than thirty.
 */

import { chooser, el, icon } from '../dom.js';

/* How far the two nudges move a shift. The design's wording names the
 * number, so the two agree by construction. */
const NUDGE_MINUTES = 15;

/* Said in place of the slots controls when the selection shares no
 * opportunity to set. */
const NO_SHARED_ROLE = (
  'These rows serve no opportunity in common, so there is none to set '
  + 'volunteers for. Select rows that share one.'
);

/** Return the events the selection names.
 *
 * @param {Object} state What the screen is showing.
 * @returns {Array<Object>} Them, in the run's own order.
 */
function selected(state) {
  return state.events.filter((event) => state.selection.has(event.id));
}

/** Return the selected events an undo would put back.
 *
 * The same field the per-row Undo is drawn from, so the two agree
 * about what counts as edited. Named rather than the whole selection
 * because the entry the change log gets names what it was asked for:
 * an undo listing rows that had nothing to undo is an entry that
 * overstates what happened.
 *
 * @param {Object} state What the screen is showing.
 * @returns {Array<string>} Their identifiers.
 */
export function undoable(state) {
  return selected(state)
    .filter((event) => event.edited)
    .map((event) => event.id);
}

/** Return the opportunities every selected event serves.
 *
 * The intersection and not the union. 'set_slots' names one role, the
 * service applies an operation whole or not at all, and 'with_slots'
 * refuses an event that serves no such opportunity -- so offering one
 * only some of them serve would turn the whole batch down. A bulk
 * control was rejected on that exact ground, a selection being
 * refused "for a reason the person selecting could not have
 * predicted". Offering only what will work is the other way out.
 *
 * @param {Array<Object>} events The selected events.
 * @returns {Array<string>} Need IDs, in the first event's own order.
 */
function sharedRoles(events) {
  const [first, ...rest] = events;

  if (first === undefined) {
    return [];
  }

  return first.roles
    .map((role) => role.needId)
    .filter((needId) => rest.every(
      (event) => event.roles.some((role) => role.needId === needId)
    ));
}

/** Return the slots controls: which opportunity, and how many.
 *
 * Two fields rather than one, because 'set_slots' is about a role and
 * not about an event: a row serving skating and non-skating officials
 * wants different numbers of each, which is what the request shape
 * says in as many words.
 *
 * The number is cleared once it has been sent, for the reason the
 * opportunity chooser puts itself back to its prompt: these name an
 * action rather than a state, and a selection whose rows hold
 * different numbers has no one number for the field to be showing.
 *
 * @param {Array<string>} shared Need IDs every selected event serves.
 * @param {Map} opportunities What each need ID is called.
 * @param {boolean} busy Whether a call is in flight.
 * @param {Function} onSetSlots What applying does.
 * @returns {HTMLElement} The pair, wrapped so they wrap together.
 */
function slotsControls(shared, opportunities, busy, onSetSlots) {
  const none = shared.length === 0;
  const role = el(
    'select',
    {
      class: 'input slots-role',
      disabled: busy || none,
      title: none ? NO_SHARED_ROLE : null,
      'aria-label': 'Which opportunity to set volunteers for'
    },
    none
      ? el('option', { value: '', text: 'No shared opportunity' })
      : shared.map((needId) => {
        const opportunity = opportunities.get(needId);

        return el('option', {
          value: needId,
          text: opportunity ? opportunity.title : needId
        });
      })
  );

  const wanted = el('input', {
    class: 'input mono slots-field',
    type: 'text',
    inputMode: 'numeric',
    disabled: busy || none,
    placeholder: '0',
    'aria-label': 'Volunteers wanted for every selected row',
    onchange: (event) => {
      const count = Number(event.target.value);

      /* The guard the per-row field uses, and for its reason: slots
       * is a count, and a count is a whole number above nothing. */
      event.target.value = '';

      if (Number.isInteger(count) && count > 0) {
        onSetSlots(role.value, count);
      }
    }
  });

  return el(
    'span',
    { class: 'slots-group' },
    chooser(role),
    wanted,
    el('span', { class: 'muted micro', text: 'slots' })
  );
}

/** Return the toolbar shown while rows are selected.
 *
 * @param {Object} state What the screen is showing.
 * @param {Object} context What the rows are drawn against, read for
 *     the categories a row may be put under and the opportunities its
 *     roles name.
 * @param {Object} handlers What each control does.
 * @param {number} hidden How many selected events a filter or a
 *     search is keeping off screen.
 * @returns {HTMLElement} The toolbar.
 */
export function selectionToolbar(state, context, handlers, hidden = 0) {
  const { categories, opportunities } = context;
  const chosen = state.selection.size;
  const busy = state.busy;
  const shared = sharedRoles(selected(state));
  const undoing = undoable(state).length;

  const categoryChooser = el(
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
    hidden > 0
      ? el('span', {
        class: 'selection-hidden muted meta',
        text: `· ${hidden} not shown`
      })
      : null,
    chooser(categoryChooser),
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
    slotsControls(shared, opportunities, busy, handlers.onSetSlots),
    el(
      'button',
      {
        type: 'button',
        class: 'btn btn-secondary',
        disabled: busy,
        title: 'Put every role back to the slots its category asked for',
        onclick: handlers.onResetSlots
      },
      icon('arrow-counter-clockwise'),
      'Default slots'
    ),
    el(
      'button',
      {
        type: 'button',
        class: 'btn btn-secondary',
        disabled: busy || undoing === 0,
        title: undoing === 0
          ? 'Nothing in this selection has been edited'
          : `Put ${undoing} of these rows back as they were collected`
            + ' - opportunity, shift times and volunteers alike',
        onclick: handlers.onUndo
      },
      icon('arrow-counter-clockwise'),
      'Undo edits'
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
