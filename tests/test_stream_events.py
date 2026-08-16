#!/usr/bin/env python3
""" What arrives on a stream becomes a record, once, on one side.

    The parsing is here rather than in the caller because the local
    half answers the same operation from the database and has no wire
    syntax to produce (D2).  These tests hold the reading of the wire
    format; that a caller gets the same record either way is held by
    the client's own tests.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
from typing import List

# Imports - Third-Party
import pytest

# Imports - Local
from star_pass_client._stream import (
    DEFAULT_EVENT,
    events,
    StreamEvent,
    StreamProtocolError
)

# Constants
# A frame as the service writes one: named, carrying an object, and
# ended by the blank line that says it is complete.
A_FRAME = ['id: 7', 'event: progress', 'data: {"done": 1}', '']


def read(lines: List[str]) -> List[StreamEvent]:
    return list(events(lines=lines))


class TestReadingAFrame:
    def test_a_frame_becomes_one_event(self) -> None:
        assert read(A_FRAME) == [
            StreamEvent(kind='progress', payload={'done': 1}, id=7)
        ]

    def test_two_frames_become_two_events(self) -> None:
        assert [
            event.kind for event in read(A_FRAME + A_FRAME)
        ] == ['progress', 'progress']

    def test_a_frame_with_no_identifier_has_none(self) -> None:
        assert read(
            ['event: job_finished', 'data: {"status": "succeeded"}', '']
        )[0].id is None

    def test_a_frame_that_names_no_event_takes_the_default_name(
        self
    ) -> None:
        assert read(['data: {}', ''])[0].kind == DEFAULT_EVENT

    def test_data_split_across_lines_is_one_value(self) -> None:
        assert read(
            ['event: progress', 'data: {"done":', 'data: 1}', '']
        )[0].payload == {'done': 1}

    def test_the_break_between_data_lines_is_part_of_the_value(
        self
    ) -> None:
        # Run together instead, two tokens on separate lines would
        # become one, and the value read would be a number nobody
        # sent rather than a frame that could not be read.
        with pytest.raises(StreamProtocolError):
            read(['event: progress', 'data: {"done": 1', 'data: 2}', ''])

    def test_a_field_this_client_does_not_read_is_ignored(self) -> None:
        # A sender is allowed to add fields, and a reader that refused
        # one could not be extended without breaking every client.
        assert read(
            ['retry: 5000', 'event: progress', 'data: {"done": 1}', '']
        ) == [StreamEvent(kind='progress', payload={'done': 1})]

    def test_one_space_is_dropped_from_a_value_and_only_one(self) -> None:
        assert read(['event:  progress', 'data: {}', ''])[0].kind == (
            ' progress'
        )


class TestWhatIsNotAnEvent:
    def test_a_comment_reports_nothing(self) -> None:
        # How the stream stays open while a job is quiet.
        assert not read([': keep-alive', ''])

    def test_a_comment_between_frames_leaves_them_alone(self) -> None:
        assert len(read(A_FRAME + [': keep-alive', ''] + A_FRAME)) == 2

    def test_a_frame_carrying_no_data_reports_nothing(self) -> None:
        assert not read(['event: progress', ''])

    def test_a_frame_the_stream_ended_in_the_middle_of_is_discarded(
        self
    ) -> None:
        # The blank line is what says a frame is complete, so what
        # arrived without one was cut off and there is no telling how
        # much of it is missing.
        assert not read(['event: progress', 'data: {"done": 1}'])

    def test_an_unterminated_frame_does_not_lose_the_ones_before_it(
        self
    ) -> None:
        assert len(read(A_FRAME + ['event: progress', 'data: {"do'])) == 1


class TestAFrameThatCannotBeRead:
    def test_an_identifier_that_is_not_a_number_is_refused(self) -> None:
        # Its only use is to be given back as the place to resume
        # from, which a value nothing can compare cannot do.
        with pytest.raises(StreamProtocolError) as error:
            read(['id: seven', 'event: progress', 'data: {}', ''])

        assert 'seven' in str(error.value)

    def test_data_that_is_not_json_is_refused(self) -> None:
        with pytest.raises(StreamProtocolError):
            read(['event: progress', 'data: not json at all', ''])

    def test_data_that_is_json_but_not_an_object_is_refused(self) -> None:
        with pytest.raises(StreamProtocolError):
            read(['event: progress', 'data: [1, 2]', ''])

    def test_a_frame_is_refused_rather_than_skipped(self) -> None:
        # A report that was made and then dropped would leave a caller
        # watching a job that had gone quiet for no recorded reason.
        with pytest.raises(StreamProtocolError):
            read(A_FRAME + ['event: progress', 'data: {', ''] + A_FRAME)
