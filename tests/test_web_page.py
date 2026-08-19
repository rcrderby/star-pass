#!/usr/bin/env python3
""" What the page loads, and whether it is there.

    There is no build step: the modules and stylesheets under 'web/'
    are what is committed and what a browser is given, so nothing
    resolves an import or a stylesheet path before a person opens the
    page.  A file named and not present is a screen with no styles at
    all, or a module that never runs -- which has happened once
    already, and which no linter catches because each file is valid on
    its own.

    A Python test for files the browser reads, for the same reason
    'test_web_phrases.py' is one: there is no JavaScript test runner
    here, and adding one to check that a path exists would be a
    toolchain for a question a directory listing answers.

    It checks paths and never contents.  What a stylesheet says and
    what a module does are looked at in a browser, which is where they
    can be seen.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
from pathlib import Path
from re import findall
from typing import List, Tuple

# Where the page is, from this file.
WEB_ROOT = Path(__file__).parent.parent / 'web'
PAGE = WEB_ROOT / 'index.html'

# What the page names in an attribute, and what a module names in an
# import.  Both are read as text: the alternative is a parser for each
# language, to answer a question about a string.
REFERENCE = r'(?:href|src)="(/[^"]+)"'
IMPORT = r'from\s+\'(\.[^\']+)\''


def modules() -> List[Path]:
    """ Return every module the page ships. """
    return sorted(WEB_ROOT.glob('js/**/*.js'))


def stated() -> List[str]:
    """ Return every same-origin path the page names. """
    return findall(REFERENCE, PAGE.read_text(encoding='utf-8'))


def imports() -> List[Tuple[Path, str]]:
    """ Return every relative import, with the module making it. """
    found = []

    for module in modules():
        for target in findall(IMPORT, module.read_text(encoding='utf-8')):
            found.append((module, target))

    return found


class TestWhatThePageNames:
    def test_the_page_is_there(self) -> None:
        assert PAGE.is_file()

    def test_every_file_the_page_names_exists(self) -> None:
        # A stylesheet named and absent is every screen unstyled, and
        # the browser says so nowhere a linter can hear it.
        for path in stated():
            assert (WEB_ROOT / path.lstrip('/')).is_file(), path

    def test_the_page_names_something_to_load(self) -> None:
        # Guards the check above from passing on an empty list, which
        # is what a changed attribute spelling would leave it.
        assert len(stated()) > 1


class TestWhatTheModulesImport:
    def test_every_import_resolves_to_a_module(self) -> None:
        # No build step and no bundler, so an import is a URL the
        # browser fetches: a wrong one is a screen that never draws.
        for module, target in imports():
            assert (module.parent / target).resolve().is_file(), (
                f'{module.name} imports {target}'
            )

    def test_the_modules_import_each_other(self) -> None:
        # The same guard: a pattern matching nothing would let the
        # check above pass over an empty list.
        assert len(imports()) > 1

    def test_every_module_is_reachable_from_the_page(self) -> None:
        # A module nothing imports is one the browser never fetches.
        # It would sit in the directory being linted and copied into
        # the image, looking like part of the interface.
        entry = {
            WEB_ROOT / path.lstrip('/')
            for path in stated()
            if path.endswith('.js')
        }
        imported = {
            (module.parent / target).resolve()
            for module, target in imports()
        }

        for module in modules():
            assert module in entry | imported, module.name
