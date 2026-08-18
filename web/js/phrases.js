/* The words this page puts on the identifiers the contract publishes.
 *
 * The contract answers with identifiers -- `partly_sent`, and the
 * reasons and operations the later screens branch on -- which is right
 * for something a program reads and wrong for something a person does.
 * Each client words them itself: the command line has
 * `_render.UNCOLLECTED_PHRASES` and `_sending.BLOCKER_PHRASES` for the
 * same reason, and neither wording belongs in the answer both read.
 *
 * They are held in `phrases.json` rather than written here, so that a
 * test can hold them to what the core publishes.  There is no build
 * step and no JavaScript test runner, so the test is a Python one that
 * loads the same file -- see `tests/test_web_phrases.py`.  A value
 * with no wording would otherwise reach a screen as its identifier,
 * quietly, which is exactly what the command line's own tests exist to
 * prevent.
 *
 * Fetched once while the page starts.  A screen calls `phrase` and
 * never waits, because nothing is drawn until the fetch has returned.
 */

const PHRASES_URL = '/phrases.json';

let loaded = null;

/** Read the wordings, once.
 *
 * @throws {Error} When the file cannot be read, which means the page
 *     was deployed incompletely -- worth failing on rather than
 *     drawing screens full of identifiers.
 * @returns {Promise<void>} When they are ready to be asked for.
 */
export async function loadPhrases() {
  const response = await fetch(PHRASES_URL, { credentials: 'same-origin' });

  if (!response.ok) {
    throw new Error(`${PHRASES_URL} could not be read.`);
  }

  loaded = await response.json();
}

/** Return what to call one identifier.
 *
 * @param {string} group Which map to read, such as `runStatus`.
 * @param {string} key The identifier the contract published.
 * @returns {string} What to show. The identifier itself when nothing
 *     words it, because a screen with a gap in it is more use than a
 *     screen that will not draw.
 */
export function phrase(group, key) {
  return loaded?.[group]?.[key] ?? key;
}
