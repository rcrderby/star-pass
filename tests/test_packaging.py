#!/usr/bin/env python3
""" The built distribution holds every package in the import root.

    A package missing from the build is not a build failure: the wheel
    is produced, and the absence only appears when something imports
    what is not there.  These tests compare what the repository holds
    against what 'pyproject.toml' says to package, so the two cannot
    drift.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
import tomllib
from fnmatch import fnmatch
from pathlib import Path
from typing import Set

# Constants
REPOSITORY_ROOT = Path(__file__).parent.parent
IMPORT_ROOT = 'app'


def packages_on_disk() -> Set[str]:
    """ Return every importable package under the import root. """
    return {
        str(
            path.parent.relative_to(REPOSITORY_ROOT)
        ).replace('/', '.')
        for path in (REPOSITORY_ROOT / IMPORT_ROOT).rglob('__init__.py')
    }


def build_configuration() -> dict:
    """ Return the setuptools table from the project configuration. """
    configuration = tomllib.loads(
        (REPOSITORY_ROOT / 'pyproject.toml').read_text(encoding='utf-8')
    )

    return configuration['tool']['setuptools']


def is_packaged(name: str) -> bool:
    """ Return whether the build would include a named package.

        Reads whichever way the packages are declared, so the tests
        below hold for a written list as well as for discovery.
    """
    declared = build_configuration()['packages']

    if isinstance(declared, list):
        return name in declared

    return any(
        fnmatch(name, pattern)
        for pattern in declared['find']['include']
    )


def test_the_import_root_holds_packages() -> None:
    # Guards the test below, which passes vacuously against an empty
    # set -- what a wrong root would produce.
    found = packages_on_disk()

    assert IMPORT_ROOT in found
    assert len(found) > 1


def test_every_package_is_covered_by_the_build() -> None:
    missing = sorted(
        package
        for package in packages_on_disk()
        if not is_packaged(name=package)
    )

    assert missing == []


def test_the_data_directories_are_not_packaged() -> None:
    # They sit beside the import root rather than inside it, which is
    # why discovery has to be pointed at 'app' rather than left to find
    # the top level itself.
    assert not is_packaged(name='data')
    assert not is_packaged(name='models')


def declared_dependencies() -> Set[str]:
    """ Return the requirement files the package declares from. """
    configuration = tomllib.loads(
        (REPOSITORY_ROOT / 'pyproject.toml').read_text(encoding='utf-8')
    )

    return set(
        configuration['tool']['setuptools']['dynamic']['dependencies'][
            'file'
        ]
    )


def pinned_in(name: str) -> Set[str]:
    """ Return the packages one requirements file pins. """
    return {
        line.split('==')[0].strip().lower()
        for line in (REPOSITORY_ROOT / name).read_text(
            encoding='utf-8'
        ).splitlines()
        if '==' in line and not line.strip().startswith('#')
    }


def test_the_package_declares_from_the_requirements_files() -> None:
    # One list rather than two.  A second list is a second place for a
    # version to be pinned and a package to be forgotten, and it is
    # the pip files that the image installs.
    assert declared_dependencies() == {
        'requirements/requirements_core.txt',
        'requirements/requirements_service.txt'
    }


def test_nothing_is_pinned_in_two_files() -> None:
    # The core file is read by the Slack image alone and by the
    # runtime file, so a package in both could come to be pinned
    # twice differently.
    core = pinned_in('requirements/requirements_core.txt')
    service = pinned_in('requirements/requirements_service.txt')

    assert core & service == set()


def test_the_entry_point_reads_both_lists() -> None:
    # 'requirements.txt' is what the image installs from, and it has
    # to reach everything the package declares.
    text = (
        REPOSITORY_ROOT / 'requirements' / 'requirements.txt'
    ).read_text(encoding='utf-8')

    assert '-r requirements_core.txt' in text
    assert '-r requirements_service.txt' in text
