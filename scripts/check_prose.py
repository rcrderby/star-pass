#!/usr/bin/env python3
""" Hold comments and docstrings to the house style.

        python scripts/check_prose.py <path> [<path> ...]
        python scripts/check_prose.py --changed origin/main

    A comment states what the code does now, simply.  It does not
    narrate how the code came to be this way, argue for the decision
    behind it, or run to an essay.  Reasoning belongs in
    'docs/design/decisions.md' or outside the repository.

    Checks what can be measured: how long a docstring or a comment
    run is, and whether it uses the phrasings that introduce history.
    Judgement is still a reviewer's.

    Given '--changed <ref>', reads the files a branch touches, so a
    pull request is held to the standard without the whole tree having
    to meet it first.
"""

# Imports - Python Standard Library
import ast
import re
import subprocess  # nosec B404
import sys
from pathlib import Path
from typing import List

# Longest a module docstring may run.  The swept modules land under
# this; the ones that do not are essays.
MODULE_LIMIT = 20

# Longest the prose of a class or function docstring may run, counted
# before 'Args:' and the other field blocks, which are not prose.
DOCSTRING_LIMIT = 12

# Longest a run of consecutive comment lines may be.
COMMENT_LIMIT = 10

# Field blocks that end the prose of a docstring.
FIELDS = ('Args:', 'Returns:', 'Raises:', 'Attributes:', 'Yields:')

# What ends the prose of a JavaScript comment.  A '@param' block is
# what 'Args:' is, so neither counts as prose.
TAG = '@'

# Phrasings that narrate rather than state.  Deliberately few and
# specific: a check that guessed would be argued with rather than
# fixed.
# 'the previous revision' and 'the calendar no longer has' are
# statements about the domain, not about the code, so the nouns are
# named rather than the phrases alone.
HISTORY = r'(?:approach|version|implementation|behaviou?r|code|' \
          r'comment|sentence|docstring|one|rule|design)'
NARRATION = (
    # 'used to be', not 'used to': the latter also means  prose-ok
    # 'employed to', as in 'the separator used to group titles'.
    (r'\bused to be\b', 'says what the code used to be'),
    (r'\bpreviously\b', 'says what was previously true'),
    (rf'\bthe previous {HISTORY}\b', 'refers to a previous version'),
    (rf'\bthe old {HISTORY}\b', 'refers to an old version'),
    (r'\bbefore D\d+\b', 'dates itself against a decision'),
    (r'\bwas written (?:before|when)\b', 'dates itself'),
    (r'\blessons? learned\b', 'records a lesson rather than a fact'),
)

# A decision is cited by number in 'docs/design/decisions.md' and
# nowhere else: a number in the code goes stale where nothing checks
# it.
DECISION = re.compile(r'\(D\d+[^)]*\)|\bD\d+\b')

# What silences one line, for the exception that is genuinely one.
ESCAPE = 'prose-ok'

# What is read.  The generated client is not: its prose lives in the
# generator that writes it.
SUFFIXES = ('.py', '.js')
SKIP = ('app/star_pass_client/_operations.py',)


def _module_docstring_lines(text: str) -> int:
    """ Return how many lines a module's docstring runs to.

        Args:
            text (str):
                The file.

        Returns:
            lines (int):
                Its length, or zero when there is none.
    """

    doc = ast.get_docstring(ast.parse(text), clean=False)

    return doc.count('\n') + 1 if doc else 0


def _prose_of(docstring: str) -> int:
    """ Return how many lines of prose a docstring opens with.

        Args:
            docstring (str):
                The docstring.

        Returns:
            lines (int):
                Lines before the first field block.
    """

    head = docstring

    for field in FIELDS:
        if field in head:
            head = head[:head.index(field)]

    return len([line for line in head.strip().splitlines() if line.strip()])


def _docstrings_too_long(path: Path, text: str) -> List[str]:
    """ Return the Python docstrings that go on too long.

        Args:
            path (Path):
                The file, for naming a problem.

            text (str):
                Its contents.

        Returns:
            problems (List[str]):
                One line per problem.
    """

    if path.suffix != '.py':
        return []

    problems = []
    module = _module_docstring_lines(text)

    if module > MODULE_LIMIT:
        problems.append(
            f'{path}:1: module docstring is {module} lines, over '
            f'{MODULE_LIMIT}'
        )

    for node in ast.walk(ast.parse(text)):
        if not isinstance(
            node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            continue

        doc = ast.get_docstring(node, clean=False)

        if doc and _prose_of(doc) > DOCSTRING_LIMIT:
            problems.append(
                f'{path}:{node.lineno}: {node.name} opens with '
                f'{_prose_of(doc)} lines of prose, over '
                f'{DOCSTRING_LIMIT}'
            )

    return problems


def _limit_for(path: Path, start: int, first: bool, documents: bool) -> int:
    """ Return how long this run of comment lines may be.

        A JavaScript module opens with a block where Python has a
        module docstring, and a '/**' block above a function is that
        function's docstring.  Each is allowed the length its Python
        equivalent is.

        Args:
            path (Path):
                The file the run is in.

            start (int):
                Line the run began on.

            first (bool):
                Whether any run has ended before this one.

            documents (bool):
                Whether the run opened with '/**'.

        Returns:
            limit (int):
                Lines the run may take.
    """

    if path.suffix == '.js' and first and start == 1:
        return MODULE_LIMIT

    return DOCSTRING_LIMIT if documents else COMMENT_LIMIT


def _comments_too_long(path: Path, text: str) -> List[str]:
    """ Return the runs of comment lines that go on too long.

        Args:
            path (Path):
                The file, for naming a problem.

            text (str):
                Its contents.

        Returns:
            problems (List[str]):
                One line per problem.
    """

    problems = []
    run = 0
    start = 0
    first = True
    documents = False

    for number, line in enumerate(text.splitlines(), 1):
        bare = line.lstrip()

        if bare.startswith('/**'):
            documents = True

        opens = (
            bare.startswith('#') or bare.startswith('*')
            or bare.startswith('//') or bare.startswith('/*')
        )

        if opens and not bare.lstrip('*/ ').startswith(TAG):
            run += 1
            start = start or number
            continue

        limit = _limit_for(path, start, first, documents)

        if run:
            first = False

        if run > limit:
            problems.append(
                f'{path}:{start}: comment runs {run} lines, over {limit}'
            )

        run = 0
        start = 0
        documents = False

    return problems


def _narrates(path: Path, text: str) -> List[str]:
    """ Return the lines that narrate rather than state.

        Args:
            path (Path):
                The file, for naming a problem.

            text (str):
                Its contents.

        Returns:
            problems (List[str]):
                One line per problem.
    """

    problems = []

    for number, line in enumerate(text.splitlines(), 1):
        bare = line.lstrip()

        if not (
            bare.startswith('#') or bare.startswith('*')
            or bare.startswith('//') or bare.startswith('"""')
        ):
            continue

        # A line that says why it is an exception is one.
        if ESCAPE in line:
            continue

        for pattern, why in NARRATION:
            if re.search(pattern, line, flags=re.IGNORECASE):
                problems.append(f'{path}:{number}: {why}')

        if DECISION.search(line):
            problems.append(
                f'{path}:{number}: cites a decision by number; '
                'state the fact instead'
            )

    return problems


def check(path: Path) -> List[str]:
    """ Return what is wrong with one file's prose.

        Args:
            path (Path):
                The file to read.

        Returns:
            problems (List[str]):
                One line per problem, empty when there are none.
    """

    text = path.read_text(encoding='utf-8')

    return (
        _docstrings_too_long(path, text)
        + _comments_too_long(path, text)
        + _narrates(path, text)
    )


def changed(ref: str) -> List[Path]:
    """ Return the files a branch has touched.

        Args:
            ref (str):
                What to compare against, such as 'origin/main'.

        Returns:
            paths (List[Path]):
                The files worth checking.
    """

    # 'git' is resolved on PATH, which is how it is reached
    # everywhere else this repository runs it.
    finished = subprocess.run(  # nosec B603 B607
        ['git', 'diff', '--name-only', '--diff-filter=d', f'{ref}...HEAD'],
        capture_output=True,
        text=True,
        check=True
    )

    return [
        Path(name) for name in finished.stdout.split()
        if name.endswith(SUFFIXES) and name not in SKIP
    ]


def main(argv: List[str]) -> int:
    """ Check what was named and say what is wrong with it.

        Args:
            argv (List[str]):
                Paths, or '--changed' and a ref.

        Returns:
            code (int):
                Zero when everything read is within the style.
    """

    if not argv:
        print(__doc__)
        return 2

    if argv[0] == '--changed':
        paths = changed(argv[1] if len(argv) > 1 else 'origin/main')
    else:
        paths = [
            Path(name) for name in argv
            if name.endswith(SUFFIXES) and name not in SKIP
        ]

    problems: List[str] = []

    for path in paths:
        if path.exists():
            problems.extend(check(path))

    for problem in problems:
        print(problem)

    if problems:
        print(f'\n{len(problems)} problem(s) in {len(paths)} file(s).')
        print('Comments state what the code does now.  Reasoning goes in')
        print("docs/design/decisions.md, or out of the repository.")
        return 1

    print(f'{len(paths)} file(s) within the style.')

    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
