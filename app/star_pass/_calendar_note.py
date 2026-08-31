#!/usr/bin/env python3
""" What a calendar description becomes before it is stored.

    A description is written by whoever made the calendar entry, in
    whatever the calendar's editor produced, so it arrives as plain
    text about as often as it arrives as a fragment of HTML holding a
    one-cell table.  Both say the same sentence and both have to store
    the same sentence.

    Converting here rather than in a client is what makes the value
    safe wherever it is read: what is stored is text, so a
    reader has no markup to render even if it tried to.
"""

# Imports - Python Standard Library
from html import unescape
from html.parser import HTMLParser
from typing import List, Optional
import re

# Tags that end a block of text.  A description's line breaks carry
# its meaning -- one line per thing the reader is being told -- and
# these are the tags a calendar editor produces them with.
_BREAKS_AFTER = frozenset({
    'br', 'div', 'li', 'p', 'td', 'tr', 'table', 'ul', 'ol', 'h1',
    'h2', 'h3', 'h4', 'h5', 'h6'
})

# The longest note stored.  A description may hold an agenda, and this
# value crosses the wire on every read of every row of a run.
NOTE_LIMIT = 1000

# Elements whose contents are not prose.  A description should never
# hold either, but what is dropped here is dropped because it would
# otherwise be read as the note's text, not because rendering it could
# do anything: what is stored is text either way.
_NOT_PROSE = frozenset({'script', 'style'})

# Runs of blank space within one line, which a converted table is full
# of, and runs of blank lines, which a converted list is.
_SPACES = re.compile(r'[^\S\n]+')
_BLANK_LINES = re.compile(r'\n{2,}')


class _Text(HTMLParser):
    """ The text of a fragment, with its blocks kept apart.

        Data is collected as it arrives and a break is recorded where
        a block ends, so that a one-cell table and the sentence it
        holds come out the same and a two-row one comes out as two
        lines rather than as one run-on.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []
        self.skipping = 0

    def handle_data(
            self,
            data: str
    ) -> None:
        """ Keep the text between the tags, unless it is not prose. """

        if self.skipping == 0:
            self.parts.append(data)

        return None

    def handle_starttag(
            self,
            tag: str,
            attrs: list
    ) -> None:
        """ Break on a tag that stands alone, such as '<br>'. """

        del attrs

        if tag in _NOT_PROSE:
            self.skipping += 1
        elif tag == 'br':
            self.parts.append('\n')

        return None

    def handle_endtag(
            self,
            tag: str
    ) -> None:
        """ Break where a block of text ends. """

        if tag in _NOT_PROSE:
            self.skipping = max(self.skipping - 1, 0)
        elif tag in _BREAKS_AFTER:
            self.parts.append('\n')

        return None


def as_text(
        description: Optional[str]
) -> Optional[str]:
    """ Return a calendar description as the text to store.

        Args:
            description (str | None):
                What the calendar gave, which may be plain text, a
                fragment of HTML, absent, or blank.

        Returns:
            note (str | None):
                The description as one or more lines of text, capped
                at 'NOTE_LIMIT' characters, or None where there is
                nothing to store.  A description holding only markup
                and blank space is nothing to store: it would draw an
                empty callout, which reads as a fault rather than as
                the absence it is.
    """

    if not description:
        return None

    reader = _Text()
    reader.feed(description)
    reader.close()

    # Unescaped again after the parser has run: it resolves the
    # entities in a fragment it recognizes as markup, and a plain-text
    # description holding '&amp;' is data it passes through untouched.
    text = unescape(''.join(reader.parts))

    text = _SPACES.sub(' ', text)
    text = _BLANK_LINES.sub('\n', text)
    text = '\n'.join(line.strip() for line in text.split('\n'))
    text = text.strip()

    if not text:
        return None

    return text[:NOTE_LIMIT]
