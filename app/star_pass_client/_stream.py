#!/usr/bin/env python3
""" What arrives on a stream, as records rather than as wire syntax.

    An operation the contract answers over time hands its caller
    these, not the lines a server-sent event stream is written in.  The
    same operation is answered locally by reading the job's events out
    of the database, and a line-shaped surface would make that half
    serialize records into wire syntax for the next layer to parse
    straight back.

    So the parsing happens once, here, on the side that actually
    receives wire syntax.  What a caller works with is the same record
    whichever half produced it.

    The field names below are the event stream specification's, not
    this service's.  Nothing in this module knows what any particular
    event means.
"""

# Imports - Python Standard Library
import json
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Iterator, List, Optional

# Constants
# The three fields this client reads, and what separates a field's
# name from its value.
#
# A comment needs no rule of its own.  It is a line beginning with the
# separator, so its field name is empty, and an empty name is not one
# of the three below -- which is how a keep-alive, the thing that
# holds a stream open while a job is quiet, reports nothing.
EVENT_FIELD = 'event'
DATA_FIELD = 'data'
ID_FIELD = 'id'
FIELD_SEPARATOR = ':'

# What an event is called when a frame does not name one.  The
# specification's default, kept so that a frame this service does not
# send is still parsed rather than refused.
DEFAULT_EVENT = 'message'

# The one space a reader drops from the front of a value.  Written by
# the sender for legibility and not part of what was sent -- so one is
# dropped and a second is the value's own.
VALUE_PREFIX = ' '


class StreamProtocolError(Exception):
    """ A frame that is not what the contract says a frame is.

        Raised rather than skipped.  A frame nobody can read is a
        report that was made and then lost, and a client that dropped
        it would leave the caller watching a job that had gone quiet
        for a reason nothing recorded.
    """


@dataclass(frozen=True)
class StreamEvent:
    """ One thing that arrived on a stream.

        Attributes:
            kind (str):
                What happened, named by whatever reported it.  The
                same vocabulary the job's stored events use, plus the
                frame that says the job is over.

            payload (Dict[str, Any]):
                What the event carried, which differs by kind.

            id (int, optional):
                Where in the job's events this one sits, or None for a
                frame that is not one of them.  A client that
                reconnects gives back the last one it saw, so the
                stream continues instead of repeating; a frame without
                one is not somewhere to resume from.
    """

    kind: str
    payload: Dict[str, Any]
    id: Optional[int] = None


@dataclass
class _Frame:
    """ The fields of one frame, while it is still being read.

        Attributes:
            kind (str, optional):
                What the 'event' field said, or None while it has not.

            data (List[str]):
                The 'data' lines, in the order they arrived.  Several
                are one value split across lines.

            identifier (str, optional):
                What the 'id' field said, unparsed, or None when the
                frame carried none.
    """

    kind: Optional[str] = None
    data: List[str] = field(default_factory=list)
    identifier: Optional[str] = None


def _parsed_identifier(
        identifier: Optional[str]
) -> Optional[int]:
    """ Return a frame's identifier as the number it resumes from.

        Args:
            identifier (str, optional):
                What the frame's 'id' field said, or None.

        Raises:
            StreamProtocolError:
                If it is not a number.  The identifier's only use is
                to be given back as the place to continue from, and a
                value that cannot be compared with the stored ones
                cannot do that.

        Returns:
            identifier (int | None):
                The identifier, or None when the frame had none.
    """

    if identifier is None:
        return None

    try:
        return int(identifier)

    except ValueError as error:
        raise StreamProtocolError(
            f'The stream sent "{identifier}" as an event identifier, '
            'which is not a number to resume from.'
        ) from error


def _parsed_payload(
        data: List[str]
) -> Dict[str, Any]:
    """ Return a frame's data as what it carried.

        Args:
            data (List[str]):
                The frame's data lines, which are one value split
                across lines.

        Raises:
            StreamProtocolError:
                If the value is not a JSON object.

        Returns:
            payload (Dict[str, Any]):
                What the event carried.
    """

    joined = '\n'.join(data)

    try:
        payload = json.loads(joined)

    except ValueError as error:
        raise StreamProtocolError(
            'The stream sent an event whose data is not JSON.'
        ) from error

    if not isinstance(payload, dict):
        raise StreamProtocolError(
            'The stream sent an event whose data is not an object.'
        )

    return payload


def _dispatched(
        frame: _Frame
) -> Optional[StreamEvent]:
    """ Return the event a completed frame describes, if it is one.

        Args:
            frame (_Frame):
                The fields read since the last blank line.

        Raises:
            StreamProtocolError:
                If the frame carries something unreadable.

        Returns:
            event (StreamEvent | None):
                The event, or None for a frame carrying no data, which
                the specification says is not dispatched.
    """

    if not frame.data:
        return None

    return StreamEvent(
        kind=frame.kind if frame.kind is not None else DEFAULT_EVENT,
        payload=_parsed_payload(data=frame.data),
        id=_parsed_identifier(identifier=frame.identifier)
    )


def _read_field(
        frame: _Frame,
        line: str
) -> None:
    """ Add one line of a frame to what has been read of it.

        Args:
            frame (_Frame):
                The frame being read.

            line (str):
                The line, which is not blank.  A comment reaches here
                like any other and is ignored for having no name.

        Returns:
            None.
    """

    name, separator, value = line.partition(FIELD_SEPARATOR)

    # A line with no separator is a field whose value is empty, which
    # is what the specification says and is not the same as a line
    # nobody sent.
    if separator and value.startswith(VALUE_PREFIX):
        value = value[len(VALUE_PREFIX):]

    if name == DATA_FIELD:
        frame.data.append(value)

    elif name == EVENT_FIELD:
        frame.kind = value

    elif name == ID_FIELD:
        frame.identifier = value

    # Any other field is one this client does not read.  Ignored
    # rather than refused: the specification allows a sender to add
    # fields, and a reader that failed on one could not be extended
    # without breaking every client at once.

    return None


def events(
        lines: Iterable[str]
) -> Iterator[StreamEvent]:
    """ Return what a stream reported, as it reports it.

        A frame left unterminated when the stream ends is discarded.
        The blank line is what says a frame is complete, so what
        arrived without one is a report that was cut off part way, and
        there is no way to tell how much of it is missing.

        Args:
            lines (Iterable[str]):
                The stream's lines, without their terminators, with a
                blank line where one arrived.

        Raises:
            StreamProtocolError:
                If a frame carries something unreadable.

        Yields:
            event (StreamEvent):
                One event, in the order they arrived.  A comment
                yields nothing: its field name is empty, and no field
                this client reads is called that.
    """

    frame = _Frame()

    for line in lines:
        if line:
            _read_field(frame=frame, line=line)
            continue

        dispatched = _dispatched(frame=frame)
        frame = _Frame()

        if dispatched is not None:
            yield dispatched
