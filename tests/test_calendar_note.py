""" What a calendar description becomes before it is stored.

    The conversion is the reason a note can be shown safely, so what
    it drops matters as much as what it keeps.
"""
# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Third-Party
import pytest

# Imports - Local
from star_pass._calendar_note import NOTE_LIMIT, as_text


class TestWhatTheCalendarWrote:
    @pytest.mark.parametrize(
        'description, expected',
        [
            # Written as plain text, which is one of the two shapes a
            # description really arrives in.
            (
                'G2: Doors at 1 PM, Game at 1:30 PM',
                'G2: Doors at 1 PM, Game at 1:30 PM'
            ),
            # And the other: the one-cell table a calendar editor
            # produces, which says the same sentence.
            (
                '<br><table><colgroup><col /></colgroup><tbody><tr><td>'
                'Doors at 6 PM, Game at 7 PM</td></tr></tbody></table>',
                'Doors at 6 PM, Game at 7 PM'
            ),
            # Formatting inside a sentence goes without taking the
            # sentence apart.
            ('<b>Doors</b> at <i>6 PM</i>', 'Doors at 6 PM'),
            ('Tacos &amp; Rollers', 'Tacos & Rollers'),
        ]
    )
    def test_a_description_becomes_the_sentence_it_holds(
        self, description, expected
    ) -> None:
        assert as_text(description=description) == expected

    @pytest.mark.parametrize(
        'description, expected',
        [
            ('<p>Doors at 6 PM</p><p>Game at 7 PM</p>',
             'Doors at 6 PM\nGame at 7 PM'),
            ('Doors at 6 PM<br>Game at 7 PM',
             'Doors at 6 PM\nGame at 7 PM'),
            ('<tr><td>One</td></tr><tr><td>Two</td></tr>', 'One\nTwo'),
        ]
    )
    def test_a_block_of_text_keeps_its_own_line(
        self, description, expected
    ) -> None:
        # A description's line breaks carry its meaning: one line per
        # thing the reader is being told.  Run together, two rows of a
        # table would read as one sentence saying something else.
        assert as_text(description=description) == expected

    @pytest.mark.parametrize(
        'description',
        ['<script>alert(1)</script>', '<style>td{color:red}</style>']
    )
    def test_what_is_not_prose_is_not_kept(self, description) -> None:
        # Not a safety measure -- what is stored is text either way --
        # but the contents of these would otherwise be read as the
        # note, which is a note saying something nobody wrote.
        assert as_text(description=f'{description}Doors at 6') == 'Doors at 6'

    @pytest.mark.parametrize(
        'description',
        [None, '', '   ', '<div>   </div>', '<br><br>']
    )
    def test_nothing_written_is_nothing_stored(self, description) -> None:
        # An empty string would draw an empty callout, which reads as
        # a fault rather than as the absence it is.  The screen has
        # its own words for having nothing to show.
        assert as_text(description=description) is None

    def test_a_long_description_is_capped(self) -> None:
        # It crosses the wire on every read of every row of a run.
        assert len(as_text(description='x' * (NOTE_LIMIT * 3))) == NOTE_LIMIT

    def test_a_tag_is_never_kept(self) -> None:
        # The whole of the reason a client may set this as text.
        converted = as_text(
            description='<img src=x onerror=alert(1)>Doors at 6'
        )

        assert '<' not in converted and converted == 'Doors at 6'
