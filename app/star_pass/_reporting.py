#!/usr/bin/env python3
""" Progress and result reporting for the core.

    The core describes what it is doing; something else decides how that
    looks.  The CLI renders these calls as terminal text, and the API
    service will record them as job steps and stream them to a browser.
    Neither rendering belongs in the domain logic, and the service
    cannot recover the data by reading text the core printed.

    The methods are events, not messages: a caller says a step began, or
    that a batch of shifts went to an opportunity and with what, and the
    renderer decides how much of that to show.  Output verbosity is a
    property of the renderer for the same reason -- how much detail to
    display is not something the domain knows about.

    **A step is named, not described.**  The core says which step
    began and each client decides what to call it, the same way it
    publishes a blocker reason rather than a sentence about one: the
    terminal words them in 'star_pass_cli._sending' and the browser in
    'web/phrases.json', each held to 'STEPS' by a test.  A label built
    here would be English in the job's event log, which is read back
    over the API by clients that word everything else themselves.

    'Reporter' itself does nothing, so the core can run unobserved: a
    test, or a caller that only wants the return value, needs no
    argument.
"""
# Every method here accepts what a renderer needs and does nothing with
# it: that is what makes this usable as the default.
# pylint: disable=unused-argument

# Imports - Python Standard Library
from dataclasses import dataclass
from typing import Any, Dict, List


# The steps the core reports, as identifiers a client words for
# itself.  Every one of them is work that can fail on its own, which
# is what makes it a step rather than a moment inside another: reading
# the calendar and reading the Amplify opportunities are two upstream
# services, and an operator whose collection stopped needs to see
# which of them stopped it.
STEP_READ_CALENDAR = 'read_calendar'
STEP_FILTER_EVENTS = 'filter_events'
STEP_MATCH_EVENTS = 'match_events'
STEP_READ_OPPORTUNITIES = 'read_opportunities'
STEP_STORE_EVENTS = 'store_events'
STEP_READ_OPPORTUNITY = 'read_opportunity'

# Every step, for the tests that hold each client's wordings to it.  A
# step no client words would otherwise reach a screen as its
# identifier, quietly.
STEPS = (
    STEP_READ_CALENDAR,
    STEP_FILTER_EVENTS,
    STEP_MATCH_EVENTS,
    STEP_READ_OPPORTUNITIES,
    STEP_STORE_EVENTS,
    STEP_READ_OPPORTUNITY
)


@dataclass(frozen=True)
class ShiftBatch:
    """ One opportunity's shifts, as they were sent.

        A record rather than six parameters, because they describe one
        thing and always travel together.  Every reporter would
        otherwise repeat the same long signature, and adding a seventh
        field would mean editing each of them.

        Attributes:
            index (int):
                Position of this opportunity in the run, from one.

            need_id (str | int):
                Amplify need ID the shifts were created under.

            title (str):
                Amplify opportunity title.

            url (str):
                Amplify API URL for the opportunity's shifts.

            shifts (List[Dict[str, Any]]):
                The individual shifts, each with a start and a
                duration.  Empty when Amplify already held every shift
                this opportunity was asked for, which is a batch that
                finished rather than one that did not happen.

            skipped (int):
                Shifts this opportunity was asked for that Amplify
                already had.  Reported beside what was created rather
                than left to the preview: what a reader is owed while
                a send runs is what became of every row, and the
                preview describes a moment before it started.

            payload (Dict[str, Any]):
                The request body, for a renderer that shows it.  Holds
                no shifts when none were created, because no request
                was made.
    """

    index: int
    need_id: str | int
    title: str
    url: str
    shifts: List[Dict[str, Any]]
    skipped: int
    payload: Dict[str, Any]


class Reporter:
    """ Accepts progress events and discards them.

        The default for every core object that reports progress, and the
        base for a renderer, which overrides only the events it shows.
    """

    def step_started(
            self,
            step: str,
            subject: str = ''
    ) -> None:
        """ A named unit of work began.

            Args:
                step (str):
                    Which one, from 'STEPS'.  An identifier rather
                    than a sentence: a renderer words it, and a job's
                    event log is read back by clients that word
                    everything else themselves.

                subject (str, optional):
                    What the step is working on, where a step is
                    working on one thing -- the Amplify need ID, for
                    the read a send makes before it writes.  Defaults
                    to an empty string, for a step that is about the
                    run as a whole.

            Returns:
                None.
        """

        return None

    def step_finished(self) -> None:
        """ The step most recently started completed successfully.

            Args:
                None.

            Returns:
                None.
        """

        return None

    def step_failed(self) -> None:
        """ The step most recently started did not complete.

            Called before the failure is logged and raised, so a
            renderer can close out whatever it displayed for the step.
            The reason is not passed: it reaches the caller as an
            exception, and reporting it twice would say it twice.

            Args:
                None.

            Returns:
                None.
        """

        return None

    def sending_started(
            self,
            opportunities: int
    ) -> None:
        """ The run began sending shift data to Amplify.

            **Carries how many opportunities the send will work
            through**, because that total is what a reader watching it
            is counting against and there is nowhere else to get it.
            It is not on the run, which does not know what a send
            would touch, and reading the preview for it would mean
            asking Amplify about a run while the send is writing to
            it.  Reported by the send itself rather than recorded when
            the job was asked for, so a job resumed after an
            interruption (D10) counts the opportunities it is about to
            work through rather than the ones the first attempt was.

            Args:
                opportunities (int):
                    How many opportunities the send will work through,
                    one request each.

            Returns:
                None.
        """

        return None

    def slack_dry_run(
            self,
            payload: List[Dict[str, Any]]
    ) -> None:
        """ A Slack post was prepared but not sent.

            The payload is passed rather than a rendering of it: what a
            dry run is for is seeing what would have been posted, and
            how to show that is the renderer's decision.

            Args:
                payload (List[Dict[str, Any]]):
                    The Block Kit blocks that would have been posted.

            Returns:
                None.
        """

        return None

    def summary_skipped(self) -> None:
        """ There was nothing in the window, so nothing was posted.

            Routine rather than an error: the summary covers a short day
            window, and an empty one means a day with nothing scheduled.

            Args:
                None.

            Returns:
                None.
        """

        return None

    def opportunity_sent(
            self,
            batch: ShiftBatch
    ) -> None:
        """ One opportunity's turn in the send is over.

            **Reported for every opportunity, including one that
            needed nothing.**  A send reads each opportunity and
            creates what it is missing, and an opportunity Amplify
            already held every shift for is one the send finished with
            rather than one it never reached.  Reported only when rows
            were created, it would be indistinguishable from an
            opportunity still being worked on -- so a screen drawing a
            row per opportunity could never finish that row, and the
            count of what is done would stop short of the total.

            Every field a renderer might show is passed, because
            choosing between them is the renderer's job.  In check mode
            the batch was not sent, and the caller reports it the same
            way: what would have been created is what an operator is
            checking.

            Args:
                batch (ShiftBatch):
                    The opportunity, what was created under it, and
                    what it already held.

            Returns:
                None.
        """

        return None
