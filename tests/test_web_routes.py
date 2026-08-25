#!/usr/bin/env python3
""" The page's route table, held to what the front end answers (D28).

    The page routes itself with the History API, so a screen is a
    path: a person reloads one, bookmarks one, or opens one in a
    second tab, and the request reaches the front end before any of
    the page's own code runs.  The front end answers those paths with
    the page and refuses everything else that is not a file.

    Two lists say what "those paths" are -- 'ROUTES' in
    'web/js/router.js' and 'SCREEN_PATHS' in the front end -- and they
    have to be the same list.  A path the page routes and the service
    refuses is a screen that works until somebody reloads it; a path
    the service answers and the page does not route is a blank screen
    at a 200.  Neither shows up in a diff of one file.

    A Python test for a JavaScript table for the reason
    'test_web_page.py' is one: there is no build step and no
    JavaScript test runner here, and the table is read as text rather
    than parsed, which is what that file already does for the imports
    and the stylesheets the page names.

    The refusal is tested here as well as the answer.  The enumerated
    fallback exists because a catch-all would hand the browser the
    page where it asked for a module, at a 200, and the screen would
    silently never draw -- so a test that only proved the screens are
    answered would pass on the arrangement D28 rejects.
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

    def test_a_module_that_is_there_is_still_served_as_one(
        self,
        browser: TestClient
    ) -> None:
        # What the refusals above are worth nothing without: the mount
        # still serves the page's own files, as themselves.
        answer = browser.get('/js/router.js')

        assert answer.status_code == 200
        assert answer.headers['content-type'].startswith('text/javascript')
