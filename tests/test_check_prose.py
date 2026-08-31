#!/usr/bin/env python3
""" The check that holds comments and docstrings to the house style.

    Two things are worth a test.  It has to catch what it is for -
    prose that narrates rather than states, and prose that runs to an
    essay - and it has to leave alone the sentences that read like
    those and are not, because a check argued with is a check turned
    off.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
from pathlib import Path
from types import ModuleType

# Imports - Third-Party
import pytest

# Imports - Local
from _scripts import loaded_script

# Constants
REPOSITORY_ROOT = Path(__file__).parent.parent
SCRIPT = REPOSITORY_ROOT / 'scripts' / 'check_prose.py'


@pytest.fixture(name='check')
def _check() -> ModuleType:
    return loaded_script('check_prose', SCRIPT)


def written(tmp_path: Path, body: str, name: str = 'sample.py') -> Path:
    """ Return a file holding 'body'. """
    path = tmp_path / name
    path.write_text(body, encoding='utf-8')

    return path


class TestWhatItCatches:
    def test_a_module_docstring_that_runs_long(self, check, tmp_path):
        body = '""" Title.\n\n' + '    A line.\n' * 25 + '"""\n'

        assert any(
            'module docstring' in problem
            for problem in check.check(written(tmp_path, body))
        )

    def test_a_docstring_that_opens_with_an_essay(self, check, tmp_path):
        body = (
            'def f():\n'
            '    """ Title.\n\n'
            + '        A line.\n' * 15
            + '\n        Returns:\n            None.\n    """\n'
        )

        assert any(
            'lines of prose' in problem
            for problem in check.check(written(tmp_path, body))
        )

    def test_a_comment_that_runs_long(self, check, tmp_path):
        body = '# A line.\n' * 12 + 'VALUE = 1\n'

        assert any(
            'comment runs' in problem
            for problem in check.check(written(tmp_path, body))
        )

    def test_prose_that_narrates(self, check, tmp_path):
        body = '# The previous implementation did it differently.\nX = 1\n'

        assert any(
            'previous version' in problem
            for problem in check.check(written(tmp_path, body))
        )

    def test_a_decision_cited_by_number(self, check, tmp_path):
        body = '# One run is one calendar (D5).\nX = 1\n'

        assert any(
            'cites a decision' in problem
            for problem in check.check(written(tmp_path, body))
        )

    def test_narration_in_the_body_of_a_docstring(self, check, tmp_path):
        # A docstring's body is indented prose, opening with none of
        # the marks a comment does.
        body = (
            'def f():\n'
            '    """ Title.\n\n'
            '        The previous implementation did it differently.\n'
            '    """\n'
        )

        assert any(
            'previous version' in problem
            for problem in check.check(written(tmp_path, body))
        )

    def test_a_decision_cited_in_the_body_of_a_docstring(
            self, check, tmp_path
    ):
        body = (
            'def f():\n'
            '    """ Title.\n\n'
            '        One run is one calendar (D5).\n'
            '    """\n'
        )

        assert any(
            'cites a decision' in problem
            for problem in check.check(written(tmp_path, body))
        )


class TestWhatItLeavesAlone:
    def test_used_to_meaning_employed_to(self, check, tmp_path):
        # 'the separator used to group titles' is not history.
        body = '# The separator used to group opportunity titles.\nX = 1\n'

        assert check.check(written(tmp_path, body)) == []

    def test_the_previous_revision_is_a_domain_word(self, check, tmp_path):
        body = '# Carrying the previous revision forward.\nX = 1\n'

        assert check.check(written(tmp_path, body)) == []

    def test_no_longer_about_the_world_not_the_code(self, check, tmp_path):
        body = '# The process that held the work no longer exists.\nX = 1\n'

        assert check.check(written(tmp_path, body)) == []

    def test_a_docstring_body_that_states(self, check, tmp_path):
        body = (
            'def f():\n'
            '    """ Title.\n\n'
            '        The separator used to group opportunity titles.\n'
            '    """\n'
        )

        assert check.check(written(tmp_path, body)) == []

    def test_a_line_that_says_it_is_an_exception(self, check, tmp_path):
        body = '# The previous implementation.  prose-ok\nX = 1\n'

        assert check.check(written(tmp_path, body)) == []

    def test_a_jsdoc_tag_block_is_fields_not_prose(self, check, tmp_path):
        # '@param' is what 'Args:' is, so a well-documented function
        # is not punished for documenting its arguments.
        body = (
            '/** Title.\n'
            + ' * @param {string} a One.\n' * 14
            + ' */\n'
            'export function f(a) { return a; }\n'
        )

        assert check.check(written(tmp_path, body, 'sample.js')) == []

    def test_prose_within_the_limits(self, check, tmp_path):
        body = (
            '""" Title.\n\n    Two lines of it.\n"""\n\n\n'
            'def f():\n'
            '    """ Title.\n\n'
            '        One line.\n\n'
            '        Returns:\n            None.\n    """\n'
        )

        assert check.check(written(tmp_path, body)) == []


class TestTheSweptFilesPass:
    @pytest.mark.parametrize(
        'name',
        [
            'app/star_pass/_migrations.py',
            'app/star_pass/_records.py',
            'app/star_pass_contract/_views.py',
            'app/star_pass_bff/_sessions.py',
            'scripts/check_prose.py'
        ]
    )
    def test_it_is_within_the_style(self, check, name):
        # The check has to pass on the files written to it, or the
        # standard is one nothing meets.
        assert check.check(REPOSITORY_ROOT / name) == []
