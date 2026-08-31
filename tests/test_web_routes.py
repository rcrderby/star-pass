#!/usr/bin/env python3
""" The page's route table, held to what the front end answers.

    The page routes itself with the History API, so a screen is a
    path: a person reloads one or opens one in a second tab, and the
    request reaches the front end before the page's own code runs.

    Two lists say what those paths are -- 'ROUTES' in
    'web/js/router.js' and 'SCREEN_PATHS' in the front end -- and they
    have to be the same list.  A path the page routes and the service
    refuses is a screen that works until somebody reloads it; a path
    the service answers and the page does not route is a blank screen
    at a 200.

    A Python test for a JavaScript table, as 'test_web_page.py' is:
    there is no JavaScript test runner here, so the table is read as
    text rather than parsed.

    The refusal is tested as well as the answer: a catch-all would
    hand the browser the page where it asked for a module, at a 200.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
from pathlib import Path
from re import findall, sub
from typing import List

# Imports - Third-Party
from fastapi.testclient import TestClient
import pytest

# Imports - Local
from star_pass_bff import _defaults, create_app

# Where the page keeps its table, from this file.
ROUTER_PATH = Path(__file__).parent.parent / 'web' / 'js' / 'router.js'

# One entry of it: the path each route is written with.  The names on
# either side are each language's own, so only the paths are compared.
ROUTE = r'\{\s*name:\s*\w+,\s*path:\s*\'([^\']+)\'\s*\}'

# What a path names its parameter, which the two lists spell
# differently on purpose: '{runId}' is what the rest of the page is
# written in and '{run_id}' is what the rest of the service is.  What
# has to match is where the parameter is, not what it is called.
PARAMETER = r'\{[^}]+\}'


def routed() -> List[str]:
    """ Return every path the page routes. """
    return findall(ROUTE, ROUTER_PATH.read_text(encoding='utf-8'))


def shaped(paths: List[str]) -> List[str]:
    """ Return the paths with their parameters made anonymous. """
    return sorted(sub(PARAMETER, '{}', path) for path in paths)


@pytest.fixture(name='browser')
def fixture_browser() -> TestClient:
    """ Return a client of the front end, as a browser reaches it. """
    return TestClient(create_app())


class TestTheTwoListsAgree:
    def test_the_page_ships_a_route_table(self) -> None:
        assert ROUTER_PATH.is_file()

    def test_the_table_was_read(self) -> None:
        # Guards both directions of the comparison below from passing
        # on an empty list, which is what a changed spelling in the
        # table would leave it.
        assert len(routed()) > 1

    def test_every_path_the_page_routes_is_answered_with_the_page(
        self
    ) -> None:
        # The screen that works until somebody reloads it.
        assert shaped(routed()) == shaped(list(_defaults.SCREEN_PATHS))

    def test_the_root_is_one_of_them(self) -> None:
        # The one path that would work either way, because the mount
        # answers it with 'html=True' whether it is enumerated or not
        # -- so it is the one that could fall out of the list without
        # anything noticing.
        assert '/' in routed()
        assert '/' in _defaults.SCREEN_PATHS


class TestWhatTheFrontEndAnswers:
    def test_every_screen_is_answered_with_the_page(
        self,
        browser: TestClient
    ) -> None:
        for path in _defaults.SCREEN_PATHS:
            answer = browser.get(path.replace('{run_id}', 'a-run'))

            assert answer.status_code == 200, path
            assert answer.headers['content-type'].startswith('text/html')

    def test_a_module_that_is_not_there_is_still_refused(
        self,
        browser: TestClient
    ) -> None:
        # The trap the enumerated fallback exists to avoid: answering
        # this with the page and a 200 turns a loud 404 into a screen
        # that never draws, and 'test_web_page.py' is the test that
        # would stop meaning anything.
        assert browser.get('/js/review/tabel.js').status_code == 404

    def test_a_path_below_a_screen_is_refused(
        self,
        browser: TestClient
    ) -> None:
        # A run identifier is one segment. A deeper path is a
        # different address rather than a run with a slash in its
        # name, and the page's own matching says the same.
        assert browser.get('/runs/a-run/preview/extra').status_code == 404

    def test_every_screen_answers_its_trailing_slash_form(
        self,
        browser: TestClient
    ) -> None:
        # Deleting the run identifier out of '/runs/<id>' leaves
        # '/runs/', which is not an enumerated path -- so the mount
        # answered it, found no file of that name and returned a
        # refusal document as raw JSON.  Every screen had it.
        for path in _defaults.SCREEN_PATHS:
            if path == '/':
                continue

            asked = path.replace('{run_id}', 'a-run')
            answer = browser.get(f'{asked}/', follow_redirects=False)

            assert answer.status_code == 307, path
            assert answer.headers['location'].endswith(asked), path

    def test_the_slash_lands_on_the_page(
        self,
        browser: TestClient
    ) -> None:
        # The redirect is worth nothing if what it points at is not
        # the screen.
        answer = browser.get('/runs/')

        assert answer.status_code == 200
        assert answer.headers['content-type'].startswith('text/html')
        assert str(answer.url).endswith('/runs')

    def test_the_slash_keeps_what_came_after_it(
        self,
        browser: TestClient
    ) -> None:
        # The address is rebuilt from the request rather than from the
        # path the route was registered with, which carries the
        # parameter's name where an identifier goes -- so this is what
        # says the rebuilt one is the whole address.
        answer = browser.get(
            '/runs/a-run/preview/?revision=2',
            follow_redirects=False
        )

        assert answer.headers['location'].endswith(
            '/runs/a-run/preview?revision=2'
        )

    def test_a_slash_is_not_a_way_past_the_enumeration(
        self,
        browser: TestClient
    ) -> None:
        # The redirect is registered per screen, not as a rule about
        # trailing slashes: a rule would answer anything one segment
        # deeper than a screen, which is the catch-all to avoid.
        for path in ('/nope/', '/js/', '/runs/a-run/preview/extra/'):
            assert browser.get(
                path,
                follow_redirects=False
            ).status_code == 404, path

    def test_the_root_is_given_no_redirect(self) -> None:
        # Its trailing-slash form is '//', which is not an address of
        # anything: the root already answers the root.  Asked of the
        # route table rather than of a request, because a request for
        # '//' is answered by the mount whether the route is there or
        # not -- so the arrangement is the only thing that can say
        # this, and a test of the answer passes either way.
        registered = [
            getattr(route, 'path', '')
            for route in create_app().routes
        ]

        assert '/' in registered
        assert '//' not in registered

    def test_a_module_that_is_there_is_still_served_as_one(
        self,
        browser: TestClient
    ) -> None:
        # What the refusals above are worth nothing without: the mount
        # still serves the page's own files, as themselves.
        answer = browser.get('/js/router.js')

        assert answer.status_code == 200
        assert answer.headers['content-type'].startswith('text/javascript')
