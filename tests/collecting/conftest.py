#!/usr/bin/env python3
""" Collecting a calendar window into a stored run.

    A directory with a conftest of its own rather than a module,
    because one collection answers two different questions -- what the
    run holds, and what its window held that the run does not -- and
    both are asked of the same arrangement.  Everything the rest of
    the suite uses is inherited from the conftest above.

    The calendar and Amplify are reached through
    'Helpers.send_api_request', which is replaced here: no test makes a
    live request.  What is not replaced is everything between that
    boundary and the database, which is what these tests are about.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

# Imports - Python Standard Library
import sqlite3
from typing import Any, Callable, Dict, List

# Imports - Third-Party
import pytest

# Imports - Local
from collecting._arranging import CALENDAR, Script
from conftest import a_category, a_need
from star_pass._collect import collect
from star_pass._reporting import Reporter
from star_pass._repository import RunRepository


@pytest.fixture(name='answers')
def fixture_answers(
    answer_requests: Callable[[Script], None]
) -> Callable[..., None]:
    """ Return a way to script the calendar and Amplify answers. """

    def script(
        items: List[Dict[str, Any]],
        titled: bool = True,
        unsearched: List[Dict[str, Any]] = None
    ) -> None:
        """ Answer every calendar read with 'items', and name needs.

            'titled' is what Amplify answers about an opportunity: a
            title, or an answer carrying none.

            'unsearched' is what the window holds and no configured
            query string returns, so it answers the read that carries
            no query string and nothing else.  That read is the only
            way an event nobody looked for can be known about.
        """

        def need_body(url: str) -> Dict[str, Any]:
            """ Return what Amplify says about one opportunity. """
            if not titled:
                return {'data': {}}

            return {
                'data': {'need_title': f'Need {url.rsplit("/", 1)[-1]}'}
            }

        def body_for(request: Dict[str, Any]) -> Dict[str, Any]:
            """ Return the body for one request. """
            if '/needs/' in request['url']:
                return need_body(url=request['url'])

            if not request['params']['q'] and unsearched is not None:
                return {'items': [*items, *unsearched]}

            return {'items': items}

        answer_requests(body_for)

    return script


@pytest.fixture(name='window')
def fixture_window(monkeypatch: pytest.MonkeyPatch) -> None:
    """ Read an offset-less window in a fixed zone. """
    monkeypatch.setenv('GCAL_TIMEZONE', 'America/Los_Angeles')

    return None


@pytest.fixture(name='collecting')
def fixture_collecting(runs: RunRepository) -> str:
    """ Return a run asked for and not yet collected into. """
    return runs.create(
        calendar=CALENDAR,
        window_start='2026-09-01',
        window_end='2026-10-01'
    ).id


# Every test arranges the same five things and then collects, so the
# arrangement is one fixture rather than five on each of them.  The
# count below is those five; a test that named them itself would carry
# the same disable and repeat the arrangement as well.
# pylint: disable-next=too-many-arguments,too-many-positional-arguments
@pytest.fixture(name='collect_run')
def fixture_collect_run(
    connection: sqlite3.Connection,
    collecting: str,
    answers: Callable[..., None],
    shift_model: Callable[..., None],
    window: None
) -> Callable[..., Any]:
    """ Return a way to script the reads and collect a run. """
    del window

    def run(
        items: List[Dict[str, Any]],
        categories: Dict[str, Any] = None,
        run_id: str = None,
        titled: bool = True,
        unsearched: List[Dict[str, Any]] = None
    ):
        """ Collect, with the calendar and Amplify answering to plan. """
        shift_model(
            categories=(
                categories
                if categories is not None
                else {'adult_game': a_category(need_ids=[a_need()])}
            )
        )
        answers(items=items, titled=titled, unsearched=unsearched)

        return collect(
            connection=connection,
            run_id=run_id if run_id is not None else collecting,
            reporter=Reporter()
        )

    return run
