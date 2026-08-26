/* Building elements, and the one way an icon is drawn.
 *
 * There is no framework and no build step, so this is what stands in
 * for one: a function that makes an element from a tag, some
 * properties and its children.  It is deliberately not a rendering
 * library -- nothing here diffs anything.  A screen redraws the region
 * that changed, which is affordable because the server owns the state
 * and hands back the whole revision after an edit.
 *
 * Text is set through `textContent` and never through `innerHTML`.
 * The values on these screens are calendar titles, opportunity titles
 * and volunteer-facing copy that came from Google Calendar and
 * Amplify, and markup that arrived in one of them should reach the
 * screen as the characters somebody typed.
 */

/* Where the icon sprite is, and what a symbol in it is called.  One
 * file, referenced rather than inlined, so thirty rows drawing the
 * same elbow cost one copy of it. */
const SPRITE = '/assets/icons.svg';

const SVG_NAMESPACE = 'http://www.w3.org/2000/svg';
const XLINK_NAMESPACE = 'http://www.w3.org/1999/xlink';

/* Properties that are not properties: these name how an element is
 * built rather than something to assign to it. */
const CLASS = 'class';
const TEXT = 'text';
const DATASET = 'dataset';

/** Return an element, built.
 *
 * @param {string} tag Element to make.
 * @param {Object} [properties] What to set on it. `class` and `text`
 *     are spelled as they are in markup; `dataset` takes an object of
 *     data attributes; `onclick` and its neighbours take a function;
 *     anything else starting with `aria-` is set as an attribute, and
 *     everything else is assigned as a property.
 * @param {...(Node|string|null|undefined|Array)} children What goes
 *     inside it. A string becomes text, and null and undefined are
 *     skipped so a caller can write a condition inline.
 * @returns {HTMLElement} The element.
 */
export function el(tag, properties = {}, ...children) {
  const element = document.createElement(tag);

  for (const [name, value] of Object.entries(properties)) {
    if (value === null || value === undefined) {
      continue;
    }

    if (name === CLASS) {
      element.className = value;
    } else if (name === TEXT) {
      element.textContent = value;
    } else if (name === DATASET) {
      Object.assign(element.dataset, value);
    } else if (name.startsWith('aria-') || name === 'role') {
      element.setAttribute(name, value);
    } else {
      element[name] = value;
    }
  }

  append(element, children);

  return element;
}

/** Put children into an element, flattening arrays and skipping gaps.
 *
 * @param {Node} parent What to fill.
 * @param {Array} children What to put in it.
 * @returns {Node} The parent.
 */
export function append(parent, children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) {
      continue;
    }

    parent.append(child);
  }

  return parent;
}

/** Return one icon from the sprite.
 *
 * Decorative by default: the icons on these screens sit beside the
 * words they illustrate, and a screen reader announcing both reads
 * everything twice. A control understood from its icon alone passes a
 * label, and gets one an assistive technology can reach.
 *
 * @param {string} name Symbol in the sprite, which is a Phosphor
 *     regular icon name.
 * @param {string} [label] What to announce it as, when it is the only
 *     thing saying what a control does.
 * @returns {SVGElement} The icon.
 */
export function icon(name, label = null) {
  const svg = document.createElementNS(SVG_NAMESPACE, 'svg');
  const use = document.createElementNS(SVG_NAMESPACE, 'use');

  svg.setAttribute('class', 'icon');
  svg.setAttribute('viewBox', '0 0 256 256');

  /* `href` is what the specification says and every current browser
   * reads; the namespaced one is what Safari wanted for long enough
   * that leaving it out is a bug somebody finds on a phone. */
  use.setAttribute('href', `${SPRITE}#${name}`);
  use.setAttributeNS(XLINK_NAMESPACE, 'xlink:href', `${SPRITE}#${name}`);
  svg.append(use);

  if (label === null) {
    svg.setAttribute('aria-hidden', 'true');
  } else {
    svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', label);
  }

  return svg;
}

/** Return a chooser: a select, with the caret that says it is one.
 *
 * 'select.input' asks for 'appearance: none', which takes the
 * native arrow with it, and reserves the room the arrow stood in.
 * Nothing put anything back, so every chooser on these screens read
 * as a text field that happened to refuse typing.
 *
 * Drawn from the sprite rather than as a background image, so there
 * is one caret in this application and not two that can come to
 * disagree. It takes no pointer events: the click belongs to the
 * select underneath, which is what opens the list.
 *
 * @param {HTMLElement} select The select to dress.
 * @returns {HTMLElement} It, wrapped with its caret.
 */
export function chooser(select) {
  return el('span', { class: 'chooser' }, select, icon('caret-down'));
}

/** Replace everything inside an element with something else.
 *
 * The whole of how a region is redrawn. Building the replacement
 * before emptying the element is deliberate: a builder that throws
 * leaves what was on screen rather than a blank where a screen used
 * to be.
 *
 * @param {Node} parent Region to redraw.
 * @param {...(Node|string|null|undefined|Array)} children What it
 *     holds now.
 * @returns {Node} The parent.
 */
export function fill(parent, ...children) {
  const built = document.createDocumentFragment();

  append(built, children);
  parent.replaceChildren(built);

  return parent;
}
