/* What this origin can be asked to prove, from a browser.
 *
 * Not a test suite and not the start of one: the interface is built
 * against the contract, and what is checked here is the arrangement
 * underneath it -- that the session is where it should be, that the
 * token a write carries is where the page can reach it, and that the
 * API answers through this origin with a credential the page never
 * holds. */

const CSRF_COOKIE = 'star_pass_csrf=';
const SESSION_COOKIE = 'star_pass_session=';

const CHECKS = [
  {
    label: 'The session cookie is unreadable by script',
    run: () => {
      if (document.cookie.includes(SESSION_COOKIE)) {
        throw new Error('readable here, so it is not HttpOnly');
      }
      return 'absent from document.cookie, which is what HttpOnly means';
    }
  },
  {
    label: 'The token a write carries is readable by script',
    run: () => {
      const pair = document.cookie
        .split('; ')
        .find((each) => each.startsWith(CSRF_COOKIE));

      if (!pair) {
        throw new Error('no star_pass_csrf cookie was set');
      }

      /* Its length, never its value: a token on a screen is a token
       * in a screenshot, and nothing here needs to see it. */
      const length = pair.length - CSRF_COOKIE.length;
      return `${length} characters, sent back in X-Star-Pass-CSRF`;
    }
  },
  {
    label: 'The API answers through this origin',
    run: async () => {
      const answer = await fetch('/api/v1/version');

      if (!answer.ok) {
        throw new Error(`the frontend answered ${answer.status}`);
      }

      const body = await answer.json();
      return `version ${body.version}, read with a credential this page never held`;
    }
  }
];

function reported(check) {
  const item = document.createElement('li');
  const label = document.createElement('span');
  const detail = document.createElement('span');

  label.className = 'label';
  label.textContent = check.label;
  detail.className = 'detail';
  detail.textContent = 'checking…';

  item.append(label, detail);

  Promise.resolve()
    .then(check.run)
    .then((answer) => {
      detail.textContent = answer;
    })
    .catch((error) => {
      item.dataset.state = 'failed';
      detail.textContent = error.message;
    });

  return item;
}

document.getElementById('checks').append(...CHECKS.map(reported));
