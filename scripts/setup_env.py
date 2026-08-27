#!/usr/bin/env python3
""" Write the '.env' a deployment needs, without printing a secret.

        python scripts/setup_env.py

    Four values stand between a fresh clone and a deployment that
    starts: the two upstream credentials, which come from Amplify and
    from Google, and the two this deployment signs with, which are
    generated.  The instructions this replaces asked for all four by
    hand, and every part of that was worse than doing it here:

    - **A pasted credential goes into the shell's history**, where it
      outlives the terminal and is read by anything that reads the
      history file.  This asks for one without echoing it and never
      prints it back.
    - **'>>' is not idempotent.**  Running the documented append twice
      leaves a file with the key in it twice, and which one wins is a
      question about the reader of the file rather than about the
      deployment.  This refuses to write a key that is already set, so
      running it again fills in what is missing and touches nothing
      else.
    - **A file of credentials should not be world-readable**, and
      nothing in a documented sequence of shell commands makes it
      otherwise.  This writes it 0600.

    What it does not do is check that a credential works.  That is
    Settings' Test control, and the answer belongs to Amplify.
"""

# Imports - Python Standard Library
import os
import secrets
import stat
import sys
from getpass import getpass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Constants
REPOSITORY_ROOT = Path(__file__).parent.parent
TEMPLATE = REPOSITORY_ROOT / '.env.example'
TARGET = REPOSITORY_ROOT / '.env'

# What both services refuse to start under.  Stated here rather than
# imported, because this script runs before anything is installed and
# an import of the application would be a dependency on the thing it
# exists to make runnable.  'app/star_pass_api/_defaults.py' and
# 'app/star_pass_bff/_defaults.py' hold the same number, and the test
# beside this script holds the three to each other.
MINIMUM_LENGTH = 32

# How many bytes of randomness a generated value carries.  Its text is
# longer than the minimum above, which is the point: nothing generated
# here can fail the check the services make.
GENERATED_BYTES = 32

# The two this deployment signs with, which are generated, and the two
# that come from somewhere else and have to be asked for.
GENERATED = (
    'STAR_PASS_API_TOKEN',
    'STAR_PASS_SESSION_SECRET'
)
ASKED = (
    ('AMPLIFY_TOKEN', 'Amplify (Galaxy Digital) API bearer token'),
    ('GCAL_TOKEN', 'Google Calendar API key')
)

# What the template writes for a value nobody has filled in yet.  A
# line carrying one of these is not a value set: it is the placeholder
# still standing, and overwriting it is what this script is for.
PLACEHOLDERS = (
    'your-amplify-api-token',
    'your-google-calendar-api-key'
)


def _setting(line: str) -> Optional[Tuple[str, str]]:
    """ Return the name and value a line sets, if it sets one.

        A commented line sets nothing.  Neither does one carrying a
        placeholder the template wrote, which is the state a fresh
        copy is in and the state this script exists to leave.

        Args:
            line (str):
                One line of the file.

        Returns:
            setting (tuple | None):
                The name and its value, or None.
    """

    bare = line.strip()

    if not bare or bare.startswith('#') or '=' not in bare:
        return None

    name, _, value = bare.partition('=')
    value = value.strip()

    if not value or value in PLACEHOLDERS:
        return None

    return name.strip(), value


def already_set(lines: List[str]) -> Dict[str, str]:
    """ Return every name the file already gives a value to.

        Args:
            lines (list):
                The file, as lines.

        Returns:
            settings (dict):
                Each name set, and what it is set to.
    """

    settings = {}

    for line in lines:
        found = _setting(line)

        if found is not None:
            settings[found[0]] = found[1]

    return settings


def short(name: str, value: str) -> Optional[str]:
    """ Return what is wrong with a value's length, if anything.

        Args:
            name (str):
                What the value is called.

            value (str):
                What it is.

        Returns:
            complaint (str | None):
                What to say about it, or None when it is long enough.
    """

    if name in GENERATED and len(value) < MINIMUM_LENGTH:
        return (
            f'{name} is shorter than {MINIMUM_LENGTH} characters, '
            'which is what the service refuses to start under.'
        )

    if not value:
        return f'{name} is empty.'

    return None


def written(lines: List[str], values: Dict[str, str]) -> List[str]:
    """ Return the file with each value written where it belongs.

        A name the template mentions is set on the line that mentions
        it, commented or not, so the comment above it goes on
        describing the value below it.  A name it does not mention is
        appended.

        Args:
            lines (list):
                The file, as lines.

            values (dict):
                What to set, by name.

        Returns:
            lines (list):
                The file, with them set.
    """

    remaining = dict(values)
    out = []

    for line in lines:
        bare = line.strip().lstrip('#').strip()
        name = bare.partition('=')[0].strip()

        if '=' in bare and name in remaining:
            out.append(f'{name}={remaining.pop(name)}\n')
        else:
            out.append(line)

    for name, value in remaining.items():
        out.append(f'{name}={value}\n')

    return out


def ask(prompt: str) -> str:
    """ Return what somebody typed, without it reaching the screen.

        Args:
            prompt (str):
                What to ask for.

        Returns:
            answer (str):
                What they typed, stripped.
    """

    return getpass(f'{prompt}: ').strip()


def collect(missing: Dict[str, str]) -> Dict[str, str]:
    """ Return a value for every name still needing one.

        Args:
            missing (dict):
                Each name to fill, and how to describe it. An empty
                description means the value is generated rather than
                asked for.

        Returns:
            values (dict):
                A value for each.
    """

    values = {}

    for name, described in missing.items():
        if not described:
            values[name] = secrets.token_urlsafe(GENERATED_BYTES)
            print(f'{name}: generated')

            continue

        while True:
            typed = ask(f'{described} ({name})')
            complaint = short(name, typed)

            if complaint is None:
                values[name] = typed
                print(f'{name}: set')

                break

            print(complaint, file=sys.stderr)

    return values


def main() -> int:
    """ Fill in what '.env' is missing, and say what happened.

        Returns:
            code (int):
                What to exit with.
    """

    if not TEMPLATE.is_file():
        print(f'No {TEMPLATE.name} to write from.', file=sys.stderr)

        return 1

    source = TARGET if TARGET.is_file() else TEMPLATE
    lines = source.read_text(encoding='utf-8').splitlines(keepends=True)
    settings = already_set(lines)

    missing = {}

    for name in GENERATED:
        if name not in settings:
            missing[name] = ''

    for name, described in ASKED:
        if name not in settings:
            missing[name] = described

    for name in sorted(set(GENERATED) & set(settings)):
        print(f'{name}: already set, left alone')

    for name, _ in ASKED:
        if name in settings:
            print(f'{name}: already set, left alone')

    if not missing:
        print(f'{TARGET.name} has all four values. Nothing to do.')

        return 0

    values = collect(missing)

    TARGET.write_text(
        ''.join(written(lines, values)),
        encoding='utf-8'
    )
    os.chmod(TARGET, stat.S_IRUSR | stat.S_IWUSR)

    print(f'Wrote {TARGET.name}, readable by you alone.')

    return 0


if __name__ == '__main__':
    sys.exit(main())
