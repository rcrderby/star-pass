#!/usr/bin/env python3
""" How a diagram is drawn, with no opinion about what is in one.

    The shapes below say what a picture is made of - a box, a network
    frame, an arrow, a note - and 'render' turns one into SVG. What
    goes where is 'generate_architecture.py' beside this, which is
    also the command that writes the files.

    Split from it because the two change on different occasions: this
    half is stable, and the half naming the boxes moves whenever the
    deployment does. Together they came to twenty lines short of the
    thousand-line cap, which is a poor place to be when the thing that
    grows is a list of boxes.

    Nothing here parses SVG or builds it through a document tree: the
    output is written a line at a time so that it diffs a line at a
    time, which is most of what makes a generated picture reviewable.
"""

# Imports - Python Standard Library
from html import escape
from typing import Dict, NamedTuple, Tuple

# The ink.  A light ground is painted explicitly rather than left
# transparent: these files are read on a page whose theme is the
# reader's, and text with no ground of its own disappears against a
# dark one.
GROUND = '#ffffff'
INK = '#0f172a'
MUTED = '#475569'
LINE = '#334155'
FRAME_INK = '#64748b'

# Fill and stroke per kind of box.  A kind is a role in the drawing,
# not a technology: what matters to a reader is which boxes are
# processes this repository ships, which are somebody else's service,
# and which one is the state that outlives a container.
KINDS: Dict[str, Tuple[str, str]] = {
    'actor': ('#fff7ed', '#f97316'),
    'service': ('#eef2ff', '#6366f1'),
    'external': ('#f6f7f9', '#94a3b8'),
    'store': ('#ecfdf5', '#10b981'),
    'flow': ('#f8fafc', '#6366f1')
}

# Size, weight, colour and alignment per named style.  One table
# rather than an argument list, so a text element is placed by saying
# what it is.
STYLES: Dict[str, Tuple[int, str, str, str]] = {
    'title': (15, '700', INK, 'start'),
    'section': (12, '700', INK, 'start'),
    'frame': (12, '600', FRAME_INK, 'start'),
    'heading': (13, '700', INK, 'middle'),
    'line': (11, '400', MUTED, 'middle'),
    'edge': (10, '400', MUTED, 'middle'),
    'note': (11, '400', MUTED, 'start')
}

# What a character costs, as a fraction of the font size.  An estimate,
# because measuring text needs the font and the standard library has
# no way to ask.  Deliberately generous: the cost of guessing high is a
# box wider than it had to be, and the cost of guessing low is a label
# that runs out past its own border in the picture.
ADVANCE = 0.58

# Room left between a label and the border of the box it sits in.
PADDING = 12

# The gap between two lines of text inside a box.
LEADING = 16

FONT = (
    "system-ui, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, "
    'sans-serif'
)


class LabelTooWide(Exception):
    """ A label does not fit the box it was given.

        Raised while generating rather than reported afterwards: a
        picture whose text has escaped its border is not worth
        committing, and the number to change is in this file.
    """


class NoSuchAnchor(Exception):
    """ An arrow names a box or a side the diagram does not hold.

        Refused by name for the reason 'LabelTooWide' is: the mistake
        is a typo in this file, and a message naming the arrow says so
        where a lookup failure would only say a key was missing.
    """


class Box(NamedTuple):
    """ A labelled rectangle, and where it sits.

        Attributes:
            name (str):
                What an edge calls this box.  Not drawn.

            kind (str):
                A key of 'KINDS', which decides the colours.

            at (Tuple[int, int, int, int]):
                Left, top, width and height.

            lines (Tuple[str, ...]):
                The heading, then whatever qualifies it.
    """

    name: str
    kind: str
    at: Tuple[int, int, int, int]
    lines: Tuple[str, ...]


class Frame(NamedTuple):
    """ A dashed rectangle drawn behind boxes, naming what holds them.

        Attributes:
            label (str):
                Drawn inside the bottom left corner.

            at (Tuple[int, int, int, int]):
                Left, top, width and height.
    """

    label: str
    at: Tuple[int, int, int, int]


class Edge(NamedTuple):
    """ An arrow from the side of one box to the side of another.

        Attributes:
            start (str):
                'box:side', where a side is left, right, top or bottom.

            end (str):
                The same, for the box the arrow points at.

            label (str):
                Drawn beside the middle of the arrow.  May be empty.

            dashed (bool):
                True for a path something is watched over rather than
                driven by.

            both_ways (bool):
                True where the arrow has a head at each end.

            shift (Tuple[int, int]):
                How far to slide each end along its own side, which is
                what keeps two arrows meeting one box apart.
    """

    start: str
    end: str
    label: str = ''
    dashed: bool = False
    both_ways: bool = False
    shift: Tuple[int, int] = (0, 0)


class Note(NamedTuple):
    """ A line of text placed on its own.

        Attributes:
            at (Tuple[int, int]):
                Where the text starts.

            text (str):
                What it says.

            style (str):
                A key of 'STYLES'.
    """

    at: Tuple[int, int]
    text: str
    style: str = 'note'


class Diagram(NamedTuple):
    """ Everything one picture is made of.

        Attributes:
            name (str):
                The file's name, without a suffix.

            title (str):
                Drawn at the top, and the accessible name of the file.

            description (str):
                What the picture shows, for a reader who cannot see it.

            size (Tuple[int, int]):
                Width and height.

            frames (Tuple[Frame, ...]):
                Drawn first, behind everything.

            boxes (Tuple[Box, ...]):
                Drawn over the frames.

            edges (Tuple[Edge, ...]):
                Drawn over the boxes.

            notes (Tuple[Note, ...]):
                Text belonging to no box.

            rules (Tuple[int, ...]):
                Heights of the full width lines that divide the
                picture into sections.
    """

    name: str
    title: str
    description: str
    size: Tuple[int, int]
    frames: Tuple[Frame, ...]
    boxes: Tuple[Box, ...]
    edges: Tuple[Edge, ...]
    notes: Tuple[Note, ...] = ()
    rules: Tuple[int, ...] = ()


def _width_of(
        text: str,
        style: str
) -> float:
    """ Estimate how wide a line of text will be drawn.

        Args:
            text (str):
                The line.

            style (str):
                A key of 'STYLES'.

        Returns:
            width (float):
                The estimate, in the same units as the drawing.
    """

    size = STYLES[style][0]

    return len(text) * size * ADVANCE


def _check_fit(
        box: Box
) -> None:
    """ Refuse a box whose own text does not fit inside it.

        Args:
            box (Box):
                The box to measure.

        Returns:
            None.

        Raises:
            LabelTooWide:
                When a line needs more room than the box leaves it.
    """

    _, _, width, _ = box.at
    room = width - PADDING * 2

    for index, line in enumerate(box.lines):
        style = 'heading' if index == 0 else 'line'
        needed = _width_of(text=line, style=style)

        if needed > room:
            message = (
                f'"{line}" needs about {needed:.0f} of the {room} '
                f'available in "{box.name}". Widen the box or shorten '
                'the line.'
            )
            raise LabelTooWide(message)


def _text(
        at: Tuple[int, int],
        content: str,
        style: str
) -> str:
    """ Draw one line of text.

        Args:
            at (Tuple[int, int]):
                Where the line sits.  What the coordinate means depends
                on the style's own alignment.

            content (str):
                What it says.

            style (str):
                A key of 'STYLES'.

        Returns:
            element (str):
                One SVG element.
    """

    size, weight, fill, anchor = STYLES[style]
    x, y = at

    return (
        f'  <text x="{x}" y="{y}" font-size="{size}" '
        f'font-weight="{weight}" fill="{fill}" '
        f'text-anchor="{anchor}">{escape(content, quote=False)}</text>'
    )


def _draw_frame(
        frame: Frame
) -> Tuple[str, ...]:
    """ Draw a network's dashed border and its name.

        The name goes inside the bottom left corner.  Along the top is
        where a reader looks for it, and it is also where the boxes
        are: a frame drawn snugly enough to say what it holds has no
        room up there, and the label ends up written over a box.

        Args:
            frame (Frame):
                What to draw.

        Returns:
            elements (Tuple[str, ...]):
                The rectangle and its label.
    """

    x, y, width, height = frame.at

    return (
        f'  <rect x="{x}" y="{y}" width="{width}" height="{height}" '
        f'rx="10" fill="none" stroke="{FRAME_INK}" stroke-width="1.5" '
        'stroke-dasharray="7 5"/>',
        _text(
            at=(x + 14, y + height - 13),
            content=frame.label,
            style='frame'
        )
    )


def _draw_box(
        box: Box
) -> Tuple[str, ...]:
    """ Draw a box and the lines of text inside it.

        Args:
            box (Box):
                What to draw.  Measured first.

        Returns:
            elements (Tuple[str, ...]):
                The rectangle, then one element per line.
    """

    _check_fit(box=box)

    x, y, width, height = box.at
    fill, stroke = KINDS[box.kind]
    middle = x + width // 2
    block = LEADING * (len(box.lines) - 1)
    first = y + (height - block) // 2 + 5

    elements = [
        f'  <rect x="{x}" y="{y}" width="{width}" height="{height}" '
        f'rx="8" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>'
    ]

    for index, line in enumerate(box.lines):
        elements.append(
            _text(
                at=(middle, first + LEADING * index),
                content=line,
                style='heading' if index == 0 else 'line'
            )
        )

    return tuple(elements)


def _anchor(
        boxes: Dict[str, Box],
        spec: str,
        shift: int
) -> Tuple[int, int]:
    """ Work out where on a box an arrow meets it.

        Args:
            boxes (Dict[str, Box]):
                Every box in the diagram, by name.

            spec (str):
                'box:side', where a side is left, right, top or bottom.

            shift (int):
                How far to slide the point along that side.

        Raises:
            NoSuchAnchor:
                When the spec names a box the diagram does not hold,
                or a side a box does not have.

        Returns:
            point (Tuple[int, int]):
                Where the arrow starts or ends.
    """

    name, side = spec.split(':')

    if name not in boxes:
        raise NoSuchAnchor(f'"{spec}" names no box in this diagram.')

    x, y, width, height = boxes[name].at
    middles = {
        'left': (x, y + height // 2 + shift),
        'right': (x + width, y + height // 2 + shift),
        'top': (x + width // 2 + shift, y),
        'bottom': (x + width // 2 + shift, y + height)
    }

    if side not in middles:
        raise NoSuchAnchor(
            f'"{spec}" names no side of a box. A side is one of '
            f'{", ".join(sorted(middles))}.'
        )

    return middles[side]


def _draw_edge(
        boxes: Dict[str, Box],
        edge: Edge
) -> Tuple[str, ...]:
    """ Draw an arrow, and its label if it carries one.

        Args:
            boxes (Dict[str, Box]):
                Every box in the diagram, by name.

            edge (Edge):
                What to draw.

        Returns:
            elements (Tuple[str, ...]):
                The line, and the label where there is one.
    """

    start_shift, end_shift = edge.shift
    x1, y1 = _anchor(boxes=boxes, spec=edge.start, shift=start_shift)
    x2, y2 = _anchor(boxes=boxes, spec=edge.end, shift=end_shift)

    dash = ' stroke-dasharray="6 4"' if edge.dashed else ''
    head = ' marker-start="url(#head)"' if edge.both_ways else ''
    elements = [
        f'  <line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
        f'stroke="{LINE}" stroke-width="1.5"{dash}{head} '
        'marker-end="url(#head)"/>'
    ]

    if edge.label:
        upright = abs(y2 - y1) > abs(x2 - x1)
        at = (
            (x1 + x2) // 2 + (14 if upright else 0),
            (y1 + y2) // 2 + (4 if upright else -11)
        )
        elements.extend(_draw_label(at=at, text=edge.label))

    return tuple(elements)


def _draw_label(
        at: Tuple[int, int],
        text: str
) -> Tuple[str, str]:
    """ Draw an arrow's label on a ground of its own.

        A network's border runs between the two boxes an arrow joins,
        which is exactly where the label goes, so the label is drawn
        over a patch of the background rather than over the dashes.

        Args:
            at (Tuple[int, int]):
                Where the text sits, horizontally centred.

            text (str):
                What the label says.

        Returns:
            elements (Tuple[str, str]):
                The patch, then the text.
    """

    x, y = at
    width = int(_width_of(text=text, style='edge')) + 10

    return (
        f'  <rect x="{x - width // 2}" y="{y - 11}" width="{width}" '
        f'height="15" fill="{GROUND}"/>',
        _text(at=at, content=text, style='edge')
    )


def render(
        diagram: Diagram
) -> str:
    """ Draw a whole diagram.

        Args:
            diagram (Diagram):
                What to draw.

        Returns:
            document (str):
                The SVG, one element to a line, ending in a newline.
    """

    width, height = diagram.size
    boxes = {box.name: box for box in diagram.boxes}

    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {width} {height}" width="{width}" '
        f'height="{height}" role="img" '
        'aria-labelledby="title description">',
        f'  <title id="title">{escape(diagram.title)}</title>',
        f'  <desc id="description">{escape(diagram.description)}'
        '</desc>',
        '  <defs>',
        '    <marker id="head" viewBox="0 0 10 10" refX="9" refY="5" '
        'markerWidth="6" markerHeight="6" '
        'orient="auto-start-reverse">',
        f'      <path d="M 0 0 L 10 5 L 0 10 z" fill="{LINE}"/>',
        '    </marker>',
        '  </defs>',
        f'  <rect width="{width}" height="{height}" fill="{GROUND}"/>',
        f'  <g font-family="{FONT}">',
        _text(at=(24, 36), content=diagram.title, style='title')
    ]

    for rule in diagram.rules:
        lines.append(
            f'  <line x1="24" y1="{rule}" x2="{width - 24}" '
            f'y2="{rule}" stroke="{FRAME_INK}" stroke-width="1" '
            'stroke-dasharray="3 4"/>'
        )

    for frame in diagram.frames:
        lines.extend(_draw_frame(frame=frame))

    for box in diagram.boxes:
        lines.extend(_draw_box(box=box))

    for edge in diagram.edges:
        lines.extend(_draw_edge(boxes=boxes, edge=edge))

    for note in diagram.notes:
        lines.append(
            _text(at=note.at, content=note.text, style=note.style)
        )

    lines.extend(('  </g>', '</svg>', ''))

    return '\n'.join(lines)
