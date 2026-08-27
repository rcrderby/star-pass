#!/usr/bin/env python3
""" The committed diagrams draw the deployment that is here.

    A committed generated file is only worth having while something
    checks it, and a diagram has a second way to go wrong that a
    contract does not: it can match its generator perfectly and still
    describe a deployment nobody runs any more.  So there are two
    kinds of check below.  The first is drift, the same check
    'tests/test_api_spec.py' makes of the specification.  The second
    holds what the pictures claim against the files that decide it -
    the networks against 'compose.yaml', the addresses against the
    contract - because those are the two things most likely to be
    renamed by work that never opens this directory.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
import json
import re
from pathlib import Path
from typing import Set

# Imports - Third-Party
import pytest
import yaml

# Imports - Local
from _scripts import loaded_script

# Constants
REPOSITORY_ROOT = Path(__file__).parent.parent
SCRIPTS = REPOSITORY_ROOT / 'scripts'
GENERATOR = SCRIPTS / 'generate_architecture.py'
DRAWING_MODULE = SCRIPTS / '_drawing.py'
COMPOSE_FILE = REPOSITORY_ROOT / 'compose.yaml'
CONTRACT_FILE = REPOSITORY_ROOT / 'docs' / 'api' / 'openapi.json'

# What an address looks like in a box, and what a path parameter is
# called once its name is set aside.  The pictures write '{id}', which
# is what every other document here writes, and the contract writes the
# parameter's own name; comparing the shapes rather than the text is
# what lets both be right.
ADDRESS = re.compile(r'/v1/[\w\-{}/]+')
PARAMETER = re.compile(r'{[^}]*}')


def _shapes(addresses: Set[str]) -> Set[str]:
    """ Set aside what each path parameter is called.

        Args:
            addresses (Set[str]):
                Addresses as they were written.

        Returns:
            shapes (Set[str]):
                The same addresses, with every parameter reduced to
                the fact that there is one.
    """

    return {
        PARAMETER.sub('{}', address)
        for address in addresses
    }


DRAWING = loaded_script('_drawing', DRAWING_MODULE)
ARCHITECTURE = loaded_script('generate_architecture', GENERATOR)

# Thirty characters, which the generator estimates at 226 across when
# it is a heading and 191 when it is a line beneath one.  The two
# widths below leave room for one and not the other, once the padding
# on each side is taken off: 244 leaves 220, and 264 leaves 240.
#
# Both are close to 226 on purpose, and NARROW is close on the side
# that also depends on the padding being taken off twice: 244 leaves
# 232 when it is taken off once, which is room enough, so a mutation
# that halves the padding is caught by this number and by no other.
LABEL = 'a label thirty characters wide'
NARROW = 244
WIDE = 264


def _one_box(width: int, lines=None):
    """ Build a diagram holding a single box of a stated width.

        Args:
            width (int):
                How wide to draw the box.

            lines (Optional[Tuple[str, ...]]):
                What it says.  LABEL alone by default.

        Returns:
            diagram (Diagram):
                A diagram with nothing in it but that box.
    """

    return DRAWING.Diagram(
        name='one-box',
        title='One box, and what it says',
        description='A box built to measure, for the checks below.',
        size=(width + 40, 100),
        frames=(),
        boxes=(
            DRAWING.Box(
                name='box',
                kind='service',
                at=(20, 20, width, 60),
                lines=lines or (LABEL,)
            ),
        ),
        edges=()
    )


DRIFT_MESSAGE = (
    'A committed diagram no longer matches the generator. Run '
    f'"{ARCHITECTURE.REGENERATE_COMMAND}" and commit the result.'
)

DIAGRAMS = ARCHITECTURE.DIAGRAMS
BY_NAME = {diagram.name: diagram for diagram in DIAGRAMS}


@pytest.fixture(name='committed')
def fixture_committed():
    def read(name: str) -> str:
        path = ARCHITECTURE.OUTPUT_DIRECTORY / f'{name}.svg'

        return path.read_text(encoding='utf-8')

    return read


def _two_boxes(start: str = 'here:right'):
    """ Build a diagram of two boxes joined by one arrow.

        Args:
            start (str):
                Where the arrow starts, which each check above names
                to say what it is testing.

        Returns:
            diagram (Diagram):
                Two boxes, and an arrow from 'start' to the second.
    """

    def box(name: str, left: int):
        return DRAWING.Box(
            name=name,
            kind='service',
            at=(left, 20, 100, 60),
            lines=('a box',)
        )

    return DRAWING.Diagram(
        name='two-boxes',
        title='Two boxes, and an arrow',
        description='A diagram built to measure, for the checks below.',
        size=(300, 100),
        frames=(),
        boxes=(box('here', 20), box('there', 180)),
        edges=(DRAWING.Edge(start=start, end='there:left'),)
    )


class TestTheCommittedCopies:
    @pytest.mark.parametrize('diagram', DIAGRAMS, ids=lambda d: d.name)
    def test_a_committed_copy_matches_the_generator(
        self,
        diagram,
        committed
    ) -> None:
        drawn = DRAWING.render(diagram=diagram)

        assert committed(diagram.name) == drawn, DRIFT_MESSAGE

    def test_every_diagram_is_committed(self) -> None:
        # The drift check above runs once per diagram the generator
        # knows, so a diagram whose file was never committed would be
        # caught -- but a file nobody generates any more would not.
        written = {
            path.stem
            for path in ARCHITECTURE.OUTPUT_DIRECTORY.glob('*.svg')
        }

        assert written == set(BY_NAME)


class TestWritingTheFiles:
    """ The drift check above compares drawings, not files.

        Everything else here goes through 'render', so the command's
        own step - writing one file per diagram, where they belong -
        is checked here or nowhere.
    """

    def test_one_file_is_written_for_each_diagram(self, tmp_path) -> None:
        written = ARCHITECTURE.write(directory=tmp_path)

        assert {path.name for path in written} == {
            f'{diagram.name}.svg' for diagram in DIAGRAMS
        }

    def test_what_is_written_is_what_is_drawn(self, tmp_path) -> None:
        ARCHITECTURE.write(directory=tmp_path)

        for diagram in DIAGRAMS:
            written = tmp_path / f'{diagram.name}.svg'

            assert written.read_text(encoding='utf-8') == DRAWING.render(
                diagram=diagram
            )


class TestWhatAnArrowMayName:
    """ The committed diagrams are checked by being drawn.

        An arrow naming a box that is not there, or a side a box does
        not have, is refused while drawing - so the drift check above
        is what holds the real diagrams to it, and what is left to
        test here is the refusal itself.
    """

    def test_an_arrow_naming_a_box_that_is_absent_is_refused(
        self
    ) -> None:
        with pytest.raises(DRAWING.NoSuchAnchor):
            DRAWING.render(diagram=_two_boxes(start='absent:right'))

    def test_an_arrow_naming_a_side_that_is_absent_is_refused(
        self
    ) -> None:
        with pytest.raises(DRAWING.NoSuchAnchor):
            DRAWING.render(diagram=_two_boxes(start='here:middle'))

    def test_an_arrow_naming_both_properly_is_drawn(self) -> None:
        # Both refusals are only worth having while the arrow they
        # are named against is otherwise drawn.
        assert '<line' in DRAWING.render(diagram=_two_boxes())

    @pytest.mark.parametrize('diagram', DIAGRAMS, ids=lambda d: d.name)
    def test_no_two_boxes_share_a_name(self, diagram) -> None:
        # An arrow finds its box by name, so a repeated name would
        # silently point every arrow at whichever came last.
        names = [box.name for box in diagram.boxes]

        assert len(names) == len(set(names))


class TestALabelThatDoesNotFit:
    """ Each case below sits close to the boundary on purpose.

        A label ten times too wide is refused by any guard at all,
        including a broken one, so it says nothing about where the
        line is.  LABEL is thirty characters, which the generator
        estimates at 226 across as a heading and 191 as a line
        beneath one; the two widths below are chosen to fall between
        those numbers and above them.
    """

    def test_a_heading_wider_than_its_box_is_refused(self) -> None:
        with pytest.raises(DRAWING.LabelTooWide):
            DRAWING.render(diagram=_one_box(width=NARROW))

    def test_the_same_heading_fits_a_wider_box(self) -> None:
        # The refusal is only worth having while the same label in a
        # box a little wider is drawn rather than refused.
        assert LABEL in DRAWING.render(diagram=_one_box(width=WIDE))

    def test_a_line_below_the_heading_is_measured_smaller(self) -> None:
        # The same label that does not fit NARROW as a heading does
        # fit it beneath one, because only the first line is drawn at
        # the heading size.
        drawn = DRAWING.render(
            diagram=_one_box(width=NARROW, lines=('short', LABEL))
        )

        assert LABEL in drawn


class TestWhatThePicturesClaim:
    def test_the_networks_drawn_are_the_networks_deployed(self) -> None:
        # A renamed network in 'compose.yaml' is a picture that has
        # quietly stopped being true, and nothing else would notice.
        compose = yaml.safe_load(
            COMPOSE_FILE.read_text(encoding='utf-8')
        )
        drawn = {
            frame.label.removesuffix(' network')
            for frame in BY_NAME['topology'].frames
        }

        assert drawn == set(compose['networks'])

    def test_the_addresses_drawn_are_addresses_the_contract_has(
        self
    ) -> None:
        contract = json.loads(
            CONTRACT_FILE.read_text(encoding='utf-8')
        )
        drawn = {
            match
            for box in BY_NAME['run-paths'].boxes
            for line in box.lines
            for match in ADDRESS.findall(line)
        }

        assert drawn, 'No address was found in the picture at all.'
        assert _shapes(drawn) <= _shapes(set(contract['paths']))
