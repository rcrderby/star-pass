#!/usr/bin/env python3
""" The setup script writes what a deployment needs and nothing else.

    Three properties are worth a test, and they are the three the
    instructions this script replaces could not offer: it refuses to
    overwrite a value already set, it never lets a value reach the
    screen, and what it writes is readable by its owner alone.  The
    fourth is arithmetic the services do at startup - a generated
    value has to clear the length they refuse to start under - and the
    number lives in three files, so a test holds them to each other.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
import stat
from pathlib import Path
from types import ModuleType

# Imports - Third-Party
import pytest

# Imports - Local
from _scripts import loaded_script
from star_pass_api import _defaults as api_defaults
from star_pass_bff import _defaults as bff_defaults

# Constants
REPOSITORY_ROOT = Path(__file__).parent.parent
SCRIPT = REPOSITORY_ROOT / 'scripts' / 'setup_env.py'

# The four names the script fills in, bound rather than written
# where they are used: bandit reads a name holding TOKEN or SECRET
# beside a string as a credential somebody hardcoded (B105), and a
# dictionary key is one of the places it looks.
SIGNS_REQUESTS = 'STAR_PASS_API_TOKEN'
SIGNS_SESSIONS = 'STAR_PASS_SESSION_SECRET'
AMPLIFY = 'AMPLIFY_TOKEN'
GCAL = 'GCAL_TOKEN'

# A value long enough to pass, and one that is not.
LONG_ENOUGH = 'a' * 40
TOO_SHORT = 'a' * 8

# What the template says about being a template, which is the block
# the script leaves behind.
TEMPLATE_BLOCK = (
    '# star-pass environment configuration template.\n'
    '#\n'
    '# The script writes .env from this file.\n'
)


@pytest.fixture(name='setup')
def _setup() -> ModuleType:
    return loaded_script('setup_env', SCRIPT)


@pytest.fixture(name='template')
def _template(tmp_path: Path) -> Path:
    """ A template with the shape the real one has: a first block
        describing the template itself, then two placeholders for the
        credentials, and the two generated names commented out under
        the comments that explain them.

        The first block matters to what is tested here rather than
        being scenery -- it is the part the script drops -- so a
        fixture without one could not tell a script that drops it
        from a script that does not.
    """

    template = tmp_path / '.env.example'
    template.write_text(
        TEMPLATE_BLOCK
        + '\n'
        + '# Required: API credentials\n'
        'AMPLIFY_TOKEN=your-amplify-api-token\n'
        'GCAL_TOKEN=your-google-calendar-api-key\n'
        '\n'
        '# The token every request to the API service carries.\n'
        '# STAR_PASS_API_TOKEN=\n'
        '\n'
        '# What the front end signs a browser session with.\n'
        '# STAR_PASS_SESSION_SECRET=\n',
        encoding='utf-8'
    )

    return template


@pytest.fixture(name='placed')
def _placed(setup, template, tmp_path, monkeypatch):
    """ Point the script at a template and a target under 'tmp_path'.
    """

    target = tmp_path / '.env'
    monkeypatch.setattr(setup, 'TEMPLATE', template)
    monkeypatch.setattr(setup, 'TARGET', target)

    return target


class TestTheLengthThreeFilesAgreeOn:
    def test_the_script_states_what_the_api_service_enforces(self, setup):
        assert setup.MINIMUM_LENGTH == api_defaults.API_TOKEN_MINIMUM_LENGTH

    def test_the_script_states_what_the_frontend_enforces(self, setup):
        assert (
            setup.MINIMUM_LENGTH
            == bff_defaults.SESSION_SECRET_MINIMUM_LENGTH
        )

    def test_a_generated_value_clears_it(self, setup):
        # The script chooses how many bytes to generate; what matters
        # is the length of the text that comes out, which is what the
        # services measure.
        generated = setup.collect({SIGNS_REQUESTS: ''})

        assert (
            len(generated[SIGNS_REQUESTS]) >= setup.MINIMUM_LENGTH
        )


class TestWhatCountsAsAlreadySet:
    def test_a_placeholder_is_not_a_value(self, setup):
        settings = setup.already_set(
            ['AMPLIFY_TOKEN=your-amplify-api-token\n']
        )

        assert AMPLIFY not in settings

    def test_a_commented_line_is_not_a_value(self, setup):
        settings = setup.already_set(['# STAR_PASS_API_TOKEN=\n'])

        assert settings == {}

    def test_an_empty_value_is_not_a_value(self, setup):
        settings = setup.already_set(['AMPLIFY_TOKEN=\n'])

        assert settings == {}

    def test_a_real_value_is_one(self, setup):
        settings = setup.already_set(['AMPLIFY_TOKEN=abc123\n'])

        assert settings == {AMPLIFY: 'abc123'}


class TestItRefusesToOverwrite:
    def test_a_value_already_set_is_left_alone(
        self, setup, placed, capsys, monkeypatch
    ):
        placed.write_text(
            f'AMPLIFY_TOKEN=kept-by-hand\n'
            f'GCAL_TOKEN=also-kept\n'
            f'STAR_PASS_API_TOKEN={LONG_ENOUGH}\n'
            f'STAR_PASS_SESSION_SECRET={LONG_ENOUGH}\n',
            encoding='utf-8'
        )
        monkeypatch.setattr(
            setup,
            'ask',
            lambda prompt: pytest.fail('asked for a value already set')
        )

        assert setup.main() == 0
        assert 'kept-by-hand' in placed.read_text(encoding='utf-8')
        assert 'Nothing to do' in capsys.readouterr().out

    def test_only_what_is_missing_is_filled(
        self, setup, placed, monkeypatch
    ):
        placed.write_text(
            'AMPLIFY_TOKEN=kept-by-hand\n'
            '# STAR_PASS_API_TOKEN=\n'
            '# STAR_PASS_SESSION_SECRET=\n'
            'GCAL_TOKEN=your-google-calendar-api-key\n',
            encoding='utf-8'
        )
        monkeypatch.setattr(setup, 'ask', lambda prompt: 'typed-gcal')

        assert setup.main() == 0

        written = setup.already_set(
            placed.read_text(encoding='utf-8').splitlines(keepends=True)
        )

        assert written[AMPLIFY] == 'kept-by-hand'
        assert written[GCAL] == 'typed-gcal'
        assert len(written[SIGNS_REQUESTS]) >= setup.MINIMUM_LENGTH
        assert (
            written[SIGNS_SESSIONS]
            != written[SIGNS_REQUESTS]
        )

    def test_a_name_is_set_once_however_often_it_runs(
        self, setup, placed, monkeypatch
    ):
        # What '>>' could not promise: the second run finds all four
        # set and writes nothing, so no name appears twice.
        monkeypatch.setattr(setup, 'ask', lambda prompt: 'typed')

        assert setup.main() == 0
        assert setup.main() == 0

        lines = placed.read_text(encoding='utf-8').splitlines()
        names = [
            line.partition('=')[0]
            for line in lines
            if line and not line.startswith('#') and '=' in line
        ]

        assert len(names) == len(set(names))


class TestWhatReachesTheScreen:
    def test_no_value_is_printed(
        self, setup, placed, capsys, monkeypatch
    ):
        monkeypatch.setattr(setup, 'ask', lambda prompt: 'typed-secret')

        assert setup.main() == 0

        shown = capsys.readouterr()
        written = setup.already_set(
            placed.read_text(encoding='utf-8').splitlines(keepends=True)
        )

        assert 'typed-secret' not in shown.out
        assert 'typed-secret' not in shown.err

        for value in written.values():
            assert value not in shown.out

    def test_it_says_what_it_did_for_each_name(
        self, setup, placed, capsys, monkeypatch
    ):
        monkeypatch.setattr(setup, 'ask', lambda prompt: 'typed')
        setup.main()

        shown = capsys.readouterr().out

        assert placed.is_file()
        assert f'{SIGNS_REQUESTS}: generated' in shown
        assert f'{AMPLIFY}: set' in shown


class TestTheTemplateDescribesItselfAndNotWhatItWrites:
    def test_the_block_is_dropped(
        self, setup, placed, monkeypatch
    ):
        # Copied through, it left the written file calling itself a
        # template and telling its reader how to create the file they
        # already had.
        monkeypatch.setattr(setup, 'ask', lambda prompt: LONG_ENOUGH)
        setup.main()

        written = placed.read_text(encoding='utf-8')

        assert 'template' not in written
        assert 'The script writes .env from this file.' not in written

        # The blank line that ended the block goes with it. Keeping it
        # would open the written file with an empty line, which is the
        # off-by-one this drop has.
        assert written.startswith('# Required: API credentials')

    def test_what_follows_the_block_is_kept(
        self, setup, placed, monkeypatch
    ):
        # The other half, and the one that says the drop stops where
        # it should: a rule that took the whole file would pass the
        # test above.
        monkeypatch.setattr(setup, 'ask', lambda prompt: LONG_ENOUGH)
        setup.main()

        written = placed.read_text(encoding='utf-8')

        assert '# Required: API credentials' in written
        assert '# The token every request to the API service carries.' \
            in written
        assert f'{AMPLIFY}={LONG_ENOUGH}' in written

    def test_a_file_it_already_wrote_keeps_its_head(
        self, setup, placed, monkeypatch
    ):
        # An existing '.env' is its own source, and its first block is
        # the head this already gave it. Dropping that would take a
        # block off the file every time somebody filled in one more
        # value.
        monkeypatch.setattr(setup, 'ask', lambda prompt: LONG_ENOUGH)
        setup.main()

        first = placed.read_text(encoding='utf-8')

        placed.write_text(
            first.replace(f'{GCAL}={LONG_ENOUGH}', f'{GCAL}='),
            encoding='utf-8'
        )
        setup.main()

        assert placed.read_text(encoding='utf-8') == first

    def test_a_template_of_one_block_is_left_alone(self, setup):
        # Dropping all of it would write an empty file, which is worse
        # than writing a header nobody wanted.
        only = ['# all of it\n', '# and no more\n']

        assert setup.without_the_template_block(only) == only


class TestWhatIsWritten:
    def test_the_file_is_readable_by_its_owner_alone(
        self, setup, placed, monkeypatch
    ):
        monkeypatch.setattr(setup, 'ask', lambda prompt: 'typed')
        setup.main()

        mode = stat.S_IMODE(placed.stat().st_mode)

        assert mode == stat.S_IRUSR | stat.S_IWUSR

    def test_a_value_is_written_where_its_comment_explains_it(
        self, setup, placed, monkeypatch
    ):
        monkeypatch.setattr(setup, 'ask', lambda prompt: 'typed')
        setup.main()

        lines = placed.read_text(encoding='utf-8').splitlines()
        above = lines[lines.index(
            next(
                line for line in lines
                if line.startswith('STAR_PASS_API_TOKEN=')
            )
        ) - 1]

        assert above.startswith('# The token every request')

    def test_a_short_answer_is_refused_and_asked_for_again(
        self, setup, placed, capsys, monkeypatch
    ):
        # Only the generated names carry the length rule: an upstream
        # credential is whatever Amplify and Google issued.
        answers = iter([TOO_SHORT, LONG_ENOUGH])
        monkeypatch.setattr(setup, 'ask', lambda prompt: next(answers))

        assert not placed.is_file()

        complaint = setup.short(SIGNS_REQUESTS, TOO_SHORT)

        assert complaint is not None
        assert str(setup.MINIMUM_LENGTH) in complaint
        assert setup.short(AMPLIFY, TOO_SHORT) is None
        assert setup.short(AMPLIFY, '') is not None

        values = setup.collect({SIGNS_SESSIONS: 'what it is for'})

        assert values[SIGNS_SESSIONS] == LONG_ENOUGH
        assert str(setup.MINIMUM_LENGTH) in capsys.readouterr().err

    def test_a_missing_template_is_said_rather_than_raised(
        self, setup, placed, capsys, monkeypatch
    ):
        monkeypatch.setattr(setup, 'TEMPLATE', placed.parent / 'gone')

        assert setup.main() == 1
        assert not placed.is_file()
        assert 'gone' in capsys.readouterr().err
