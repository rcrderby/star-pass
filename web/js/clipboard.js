/* Putting something on the clipboard, in one place.
 *
 * Two screens offer to copy an identifier -- the collecting screen a
 * job's, the run picker a run's -- and both want the same answer to a
 * browser that refuses: say nothing alarming, because the thing being
 * copied is on the screen either way, which is what showing it is
 * for.
 */

/** Put text on the clipboard, and say whether it went.
 *
 * A browser may refuse: the clipboard is a permission, and a page
 * that has not been interacted with does not get one. Refusing is not
 * a failure worth a notice, so this answers rather than raising, and
 * the caller shows what it can.
 *
 * @param {string} text What to copy.
 * @returns {Promise<boolean>} Whether it reached the clipboard.
 */
export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);

    return true;
  } catch (error) {
    console.error(error);

    return false;
  }
}
