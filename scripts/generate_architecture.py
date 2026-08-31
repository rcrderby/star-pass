#!/usr/bin/env python3
""" Draw the architecture diagrams and write them to 'docs/architecture'.

    Run after changing the shape of the deployment - a service, a
    network, where a credential lives, or what a step of a run
    touches - and commit what it writes:

        python scripts/generate_architecture.py

    The pictures are generated so the thing a person edits is the
    thing a person can read: the boxes, networks and arrows below are
    names and coordinates, and the SVG is an artifact of them.

    Positions are stated rather than computed, and the generator
    refuses what it cannot draw honestly: a label wider than its box,
    or an arrow naming a box or a side that is not there.

    '_drawing.py' beside this holds how a diagram is drawn, and
    'tests/test_architecture.py' fails while a committed file disagrees
    with what this writes.
"""

# Imports - Python Standard Library
import sys
from pathlib import Path
from typing import Tuple

# Imports - Local
from _drawing import Box, Diagram, Edge, Frame, Note, render

# Where the artifacts go, and what regenerates them.  Named here
# because the drift test quotes the command in its failure message.
OUTPUT_DIRECTORY = Path(__file__).parent.parent / 'docs' / 'architecture'
REGENERATE_COMMAND = 'python scripts/generate_architecture.py'

# The deployment.  Read left to right: a browser reaches one published
# port, and every hop after it is inside the host.  The two frames are
# the two networks in 'compose.yaml', and the frontend is deliberately
# the only box inside both of them.
TOPOLOGY = Diagram(
    name='topology',
    title='star-pass deployment: two networks, one published port',
    description=(
        'A browser reaches Caddy, the only service publishing a port. '
        'Caddy proxies to the frontend on the edge network. The '
        'frontend proxies to the API on the backend network, which '
        'Caddy is not on. The API alone holds the Amplify credential '
        'and the database, and alone reaches Amplify and Google '
        'Calendar.'
    ),
    size=(1060, 470),
    frames=(
        Frame(label='edge network', at=(184, 118, 430, 176)),
        Frame(label='backend network', at=(394, 136, 460, 252))
    ),
    boxes=(
        Box(
            name='browser',
            kind='actor',
            at=(24, 156, 130, 98),
            lines=('Browser', 'no credential', 'session cookie')
        ),
        Box(
            name='caddy',
            kind='service',
            at=(204, 156, 160, 98),
            lines=(
                'Caddy',
                'only published port',
                '80 and 443',
                'TLS ends here'
            )
        ),
        Box(
            name='frontend',
            kind='service',
            at=(414, 156, 180, 98),
            lines=(
                'Frontend',
                'adds the API token',
                'checks the origin',
                'no Amplify credential'
            )
        ),
        Box(
            name='api',
            kind='service',
            at=(644, 156, 180, 98),
            lines=(
                'API',
                'holds AMPLIFY_TOKEN',
                'reads ./.env read-only',
                'owns the database'
            )
        ),
        Box(
            name='database',
            kind='store',
            at=(659, 300, 150, 58),
            lines=('star_pass.db', 'a named volume')
        ),
        Box(
            name='amplify',
            kind='external',
            at=(884, 141, 150, 58),
            lines=('Amplify', 'read and written')
        ),
        Box(
            name='calendar',
            kind='external',
            at=(884, 225, 150, 58),
            lines=('Google Calendar', 'read at collection')
        )
    ),
    edges=(
        Edge(start='browser:right', end='caddy:left', label='HTTPS'),
        Edge(start='caddy:right', end='frontend:left', label='HTTP'),
        Edge(start='frontend:right', end='api:left', label='HTTP'),
        Edge(start='api:bottom', end='database:top'),
        Edge(
            start='api:right',
            end='amplify:left',
            shift=(-18, 0)
        ),
        Edge(
            start='api:right',
            end='calendar:left',
            shift=(18, 0)
        )
    ),
    notes=(
        Note(
            at=(24, 424),
            text=(
                'Caddy is absent from the backend network, so the '
                'frontend is the only path to the process holding the '
                'Amplify credential, rather than merely the intended '
                'one.'
            )
        ),
        Note(
            at=(24, 444),
            text=(
                'Neither application service publishes a port, which '
                'is why the documentation the API serves at /docs and '
                '/redoc cannot be reached from the host.'
            )
        )
    )
)

# What a run does.  The middle column is the order the four steps
# happen in; the columns beside it are what each step reaches for.
# Below the rule is the scheduled post, which shares none of it.
RUN_PATHS = Diagram(
    name='run-paths',
    title='A run, and what each step touches',
    description=(
        'A run collects a window, is reviewed, is previewed and is '
        'sent. Every step reads and writes the database. Collecting '
        'reads Google Calendar and the Amplify listings; the preview '
        'and the send read and write Amplify. Collecting and sending '
        'run as jobs, watched over the job stream. The scheduled '
        'Slack post runs elsewhere and touches none of it.'
    ),
    size=(1060, 870),
    frames=(),
    boxes=(
        Box(
            name='page',
            kind='actor',
            at=(300, 64, 360, 56),
            lines=(
                'The page in the browser',
                'every call below goes through Caddy and the frontend'
            )
        ),
        Box(
            name='database',
            kind='store',
            at=(60, 150, 190, 424),
            lines=(
                'star_pass.db',
                'runs, revisions,',
                'events, the change',
                'log, and the shifts',
                'a send recorded',
                '',
                'read by every step',
                'below, written by',
                'all but the preview'
            )
        ),
        Box(
            name='collect',
            kind='flow',
            at=(300, 150, 360, 88),
            lines=(
                '1. Collect',
                'POST /v1/runs',
                'runs as a job on a thread',
                'watched over the job stream below'
            )
        ),
        Box(
            name='review',
            kind='flow',
            at=(300, 262, 360, 88),
            lines=(
                '2. Review',
                'GET /v1/runs/{id}',
                'POST and PATCH /v1/runs/{id}/events',
                'every edit writes a log entry'
            )
        ),
        Box(
            name='preview',
            kind='flow',
            at=(300, 374, 360, 88),
            lines=(
                '3. Preview',
                'GET /v1/runs/{id}/preview',
                'reads Amplify before it answers',
                'writes nothing at all'
            )
        ),
        Box(
            name='send',
            kind='flow',
            at=(300, 486, 360, 88),
            lines=(
                '4. Send',
                'POST /v1/runs/{id}/send',
                'runs as a job on a thread',
                'resumable where it was interrupted'
            )
        ),
        Box(
            name='stream',
            kind='service',
            at=(300, 598, 360, 76),
            lines=(
                'The job stream',
                'GET /v1/jobs/{id}/events',
                'server-sent, and passed on unbuffered'
            )
        ),
        Box(
            name='calendar',
            kind='external',
            at=(710, 88, 320, 76),
            lines=(
                'Google Calendar',
                'the events in the window',
                'read once, at collection'
            )
        ),
        Box(
            name='amplify',
            kind='external',
            at=(710, 262, 320, 312),
            lines=(
                'Amplify',
                'the listings, read at collection',
                'the shifts it already holds,',
                'read again at preview and',
                'once more per opportunity',
                'as a send writes to it',
                '',
                'the only service outside',
                'this host that a run reaches'
            )
        ),
        Box(
            name='runner',
            kind='external',
            at=(60, 752, 230, 76),
            lines=(
                'GitHub Actions',
                'Wednesday and Friday',
                '19:12 UTC'
            )
        ),
        Box(
            name='image',
            kind='service',
            at=(330, 752, 230, 76),
            lines=(
                'The slim image',
                'star-pass -s',
                'no database, no page'
            )
        ),
        Box(
            name='upstream',
            kind='external',
            at=(600, 752, 190, 76),
            lines=('Amplify', 'read, never written')
        ),
        Box(
            name='slack',
            kind='external',
            at=(830, 752, 170, 76),
            lines=('Slack', 'one post')
        )
    ),
    edges=(
        Edge(start='page:bottom', end='collect:top'),
        Edge(start='collect:bottom', end='review:top'),
        Edge(start='review:bottom', end='preview:top'),
        Edge(start='preview:bottom', end='send:top'),
        Edge(
            start='database:right',
            end='collect:left',
            both_ways=True,
            shift=(-168, 0)
        ),
        Edge(
            start='database:right',
            end='review:left',
            both_ways=True,
            shift=(-56, 0)
        ),
        Edge(
            start='database:right',
            end='preview:left',
            shift=(56, 0)
        ),
        Edge(
            start='database:right',
            end='send:left',
            both_ways=True,
            shift=(168, 0)
        ),
        Edge(
            start='collect:right',
            end='calendar:left',
            shift=(-20, 0)
        ),
        Edge(
            start='collect:right',
            end='amplify:left',
            shift=(30, -118)
        ),
        Edge(
            start='preview:right',
            end='amplify:left',
            shift=(0, -18)
        ),
        Edge(start='send:right', end='amplify:left', shift=(0, 82)),
        Edge(start='send:bottom', end='stream:top', dashed=True),
        Edge(start='runner:right', end='image:left'),
        Edge(start='image:right', end='upstream:left'),
        Edge(start='upstream:right', end='slack:left')
    ),
    notes=(
        Note(
            at=(24, 722),
            text='The scheduled Slack post, which none of the above '
                 'reaches and which reaches none of it',
            style='section'
        ),
        Note(
            at=(24, 852),
            text=(
                'It runs on a machine GitHub creates and destroys, '
                'from an image holding what the -s run mode imports '
                'and nothing else: no API service, no frontend, no '
                'database and no page to serve.'
            )
        )
    ),
    rules=(700,)
)

DIAGRAMS = (TOPOLOGY, RUN_PATHS)


def write(
        directory: Path = OUTPUT_DIRECTORY
) -> Tuple[Path, ...]:
    """ Draw every diagram and write it where it belongs.

        Args:
            directory (Path):
                Where the files go.  Created when it is absent.

        Returns:
            written (Tuple[Path, ...]):
                What was written, in the order it was drawn.
    """

    directory.mkdir(parents=True, exist_ok=True)
    written = []

    for diagram in DIAGRAMS:
        path = directory / f'{diagram.name}.svg'
        path.write_text(render(diagram=diagram), encoding='utf-8')
        written.append(path)

    return tuple(written)


def main() -> int:
    """ Write every diagram and report where each one went.

        Args:
            None.

        Returns:
            status (int):
                Zero, for a process that succeeded.
    """

    for path in write():
        print(f'Wrote {path}')

    return 0


if __name__ == '__main__':
    sys.exit(main())
