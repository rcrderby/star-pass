#!/usr/bin/env python3
""" Write the '.env' a deployment needs, without printing a secret.

        python scripts/setup_env.py

    Six values stand between a fresh clone and a deployment that
    starts.  AMPLIFY_TOKEN and GCAL_TOKEN come from Amplify and from
    Google and are asked for without echoing; GCAL_EVENTS_CAL_ID and
    GCAL_PRACTICES_CAL_ID name the calendars and are asked for in the
    open; STAR_PASS_API_TOKEN and STAR_PASS_SESSION_SECRET are
    generated.  A value already set is never overwritten, so running
    this again fills in what is missing and touches nothing else.  The
    file is written 0640.

    Whether a credential works is Settings' Test control to answer.
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

# Shortest generated value both services accept.  The two service
# '_defaults' modules hold the same number and a test holds the three
# to each other.
MINIMUM_LENGTH = 32

# What a shell reports for a command an interrupt ended: 128 plus the
# signal, and SIGINT is 2.
INTERRUPTED = 130

# Bytes of randomness in a generated value.  Its text is longer than
# MINIMUM_LENGTH, so nothing generated here fails the services' check.
GENERATED_BYTES = 32

# The two generated here, and the four asked for.  Every name in the
# three is one the API service refuses to start without.
GENERATED = (
    'STAR_PASS_API_TOKEN',
    'STAR_PASS_SESSION_SECRET'
)
ASKED = (
    ('AMPLIFY_TOKEN', 'Amplify (Galaxy Digital) API bearer token'),
    ('GCAL_TOKEN', 'Google Calendar API key')
)

# Asked for the same way, and echoed: a calendar identifier is not a
# secret, and one typed blind is one nobody can check.
PUBLIC = (
    (
        'GCAL_EVENTS_CAL_ID',
        'Google Calendar ID for the events calendar'
    ),
    (
        'GCAL_PRACTICES_CAL_ID',
        'Google Calendar ID for the practices calendar'
    )
)

# How many values a finished '.env' holds, for the line that says so.
REQUIRED_COUNT = len(GENERATED) + len(ASKED) + len(PUBLIC)

# What the template writes for a value nobody has filled in.  A line
# carrying one is not a value set.
PLACEHOLDERS = (
    'your-amplify-api-token',
    'your-google-calendar-api-key'
)


def _setting(line: str) -> Optional[Tuple[str, str]]:
    """ Return the name and value a line sets, if it sets one.

        A commented line sets nothing, and neither does one carrying a
        placeholder.

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

    if name in dict(PUBLIC) and value.startswith('/'):
        return (
            f'{name} starts with "/". Give the calendar identifier '
            'alone; the address is built around it.'
        )

    return None


def without_the_template_block(lines: List[str]) -> List[str]:
    """ Return the template without the part that describes itself.

        The block is the lines before the first blank one; what
        follows that blank line is the head of the file this writes.

        Args:
            lines (list):
                The template, as lines.

        Returns:
            lines (list):
                What to write from.
    """

    for position, line in enumerate(lines):
        if not line.strip():
            return lines[position + 1:]

    # A template that is one block and nothing else has no head to
    # keep, and dropping all of it would write an empty file.
    return lines


def written(lines: List[str], values: Dict[str, str]) -> List[str]:
    """ Return the file with each value written where it belongs.

        A name the template mentions is set on the line that mentions
        it, commented or not.  A name it does not mention is appended.

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


def ask(prompt: str, secret: bool = True) -> str:
    """ Return what somebody typed.

        Args:
            prompt (str):
                What to ask for.

            secret (bool, optional):
                Whether to keep it off the screen.  Defaults to True.

        Returns:
            answer (str):
                What they typed, stripped.
    """

    if secret:
        return getpass(f'{prompt}: ').strip()

    return input(f'{prompt}: ').strip()


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
    public = dict(PUBLIC)

    for name, described in missing.items():
        if not described:
            values[name] = secrets.token_urlsafe(GENERATED_BYTES)
            print(f'{name}: generated')

            continue

        while True:
            typed = ask(
                f'{described} ({name})',
                secret=name not in public
            )
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

    # Only when reading the template.  Its first block says what a
    # template is and how to turn one into '.env', which is true of
    # the file being read and false of the file being written -- but
    # an existing '.env' is its own source here, and its first block
    # is the head this already gave it.  Dropping that would take a
    # line off the file every time somebody filled in one more value.
    if source is TEMPLATE:
        lines = without_the_template_block(lines)

    settings = already_set(lines)

    missing = {}

    for name in GENERATED:
        if name not in settings:
            missing[name] = ''

    for name, described in ASKED + PUBLIC:
        if name not in settings:
            missing[name] = described

    for name in sorted(set(GENERATED) & set(settings)):
        print(f'{name}: already set, left alone')

    for name, _ in ASKED + PUBLIC:
        if name in settings:
            print(f'{name}: already set, left alone')

    if not missing:
        print(f'{TARGET.name} has all {REQUIRED_COUNT} values. Nothing to do.')

        return 0

    values = collect(missing)

    TARGET.write_text(
        ''.join(written(lines, values)),
        encoding='utf-8'
    )
    # The API container reads the file through its group: a bind
    # mount keeps the host file's mode, and the image runs as UID 1000.
    os.chmod(TARGET, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP)

    print(f'Wrote {TARGET.name}, readable by you and your group.')

    return 0


def run() -> int:
    """ Run it, and answer a Ctrl+C the way a command should.

        Every value is gathered before the single write, so an
        interrupt leaves the file as it was.

        Returns:
            code (int):
                What to exit with.  130 is the shell's own answer for
                a command ended by an interrupt.
    """

    try:
        return main()

    except KeyboardInterrupt:
        print(
            f'\nStopped. {TARGET.name} was not written.',
            file=sys.stderr
        )

        return INTERRUPTED


if __name__ == '__main__':
    sys.exit(run())
