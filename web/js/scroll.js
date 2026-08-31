/** Where the reader was, per address.
 *
 * The address names the run and the view, so it is what a place is
 * remembered against.
 *
 * **Restoring waits for the content.** A screen is put on the page
 * before it has read anything and fills itself in when the read
 * lands, and nothing publishes "the screen is finished". What is
 * waited on is the page being tall enough to hold the offset, checked
 * on a short timer until it is or until waiting stops being welcome.
 *
 * **In memory, not in storage.** A place is remembered inside one
 * visit rather than across reloads: a position restored into a run
 * whose rows moved while the page was closed is a worse answer than
 * the top of the table.
 */

/* Where each address was left, keyed by the whole path, so two views
 * of one run are two places and two runs are four. */
const places = new Map();

/* How long to keep waiting for the page to grow, in milliseconds,
 * and how often to look.  A read that takes longer than this has
 * bigger problems than where the reader was, and an offset applied a
 * long time after the screen settled would move somebody who had
 * started reading.
 *
 * Looked at on a timer rather than watched with a 'ResizeObserver'.
 * An observer is the tidier way to hear about a box changing size and
 * is what the width hint and the run header use -- but neither of
 * those depends on it alone, and this would: they measure again on
 * every draw, and the whole point here is the moment *after* the last
 * draw this code knows about.  Forty reads of one number over two
 * seconds costs nothing, and unlike an observer it can be watched
 * working. */
const GIVE_UP = 2000;
const LOOK_EVERY = 50;

/* What is being waited on now, so a second navigation cancels the
 * first: going to a run and straight out of it again must not leave
 * an offset waiting to be applied to whatever is on screen when it
 * finally fits. */
let waiting = null;

/** Stop waiting for the page to grow.
 *
 * @returns {void}
 */
function stop() {
  if (waiting === null) {
    return;
  }

  window.clearInterval(waiting.looking);
  window.clearTimeout(waiting.timer);
  window.removeEventListener('wheel', waiting.give);
  window.removeEventListener('touchmove', waiting.give);
  window.removeEventListener('keydown', waiting.give);
  waiting = null;
}

/** Return whether the page can hold an offset yet.
 *
 * @param {number} wanted The offset to reach.
 * @returns {boolean} Whether scrolling there would land there.
 */
function reaches(wanted) {
  return (
    document.documentElement.scrollHeight - window.innerHeight >= wanted
  );
}

/** Remember where an address was left.
 *
 * @param {string} path The address being left.
 * @returns {void}
 */
export function remember(path) {
  places.set(path, window.scrollY);
}

/** Put the reader back where they were at an address.
 *
 * An address nobody has been to opens at the top, which is not the
 * same as doing nothing: the page keeps its offset across a drawing,
 * so a screen entered from halfway down another one would start
 * halfway down itself.
 *
 * @param {string} path The address being entered.
 * @returns {void}
 */
export function restore(path) {
  stop();

  const wanted = places.get(path) ?? 0;

  if (wanted === 0 || reaches(wanted)) {
    window.scrollTo(0, wanted);

    return;
  }

  /* The reader's own scroll wins.  They are looking at what did
   * arrive, and moving them once the rest lands would take the screen
   * away from them -- so any of the three ways of asking for a
   * different place gives this up. */
  const give = () => stop();

  waiting = {
    give,
    timer: window.setTimeout(stop, GIVE_UP),
    looking: window.setInterval(
      () => {
        if (reaches(wanted)) {
          window.scrollTo(0, wanted);
          stop();
        }
      },
      LOOK_EVERY
    )
  };

  window.addEventListener('wheel', give, { passive: true });
  window.addEventListener('touchmove', give, { passive: true });
  window.addEventListener('keydown', give);
}

/** Forget every remembered place.
 *
 * @returns {void}
 */
export function forget() {
  stop();
  places.clear();
}
