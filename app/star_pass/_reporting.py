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

    'Reporter' itself does nothing, so the core can run unobserved: a
    test, or a caller that only wants the return value, needs no
    argument.
"""
# Every method here accepts what a renderer needs and does nothing with
# it: that is what makes this usable as the default.
# pylint: disable=unused-argument

# Imports - Python Standard Library
from typing import Any, Dict, List


class Reporter:
    """ Accepts progress events and discards them.

        The default for every core object that reports progress, and the
        base for a renderer, which overrides only the events it shows.
    """

    def step_started(
            self,
            label: str
    ) -> None:
        """ A named unit of work began.

            Args:
                label (str):
                    Human-readable description of the work, in the
                    present participle ('Removing duplicate shifts').

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

    def schema_validation_failed(self) -> None:
        """ Shift data did not match the JSON Schema.

            Distinct from 'step_failed' because the run continues: the
            data is reported as invalid rather than raising, so that an
            operator sees why nothing was created.

            Args:
                None.

            Returns:
                None.
        """

        return None

    def sending_started(self) -> None:
        """ The run began sending shift data to Amplify.

            Args:
                None.

            Returns:
                None.
        """

        return None

    def check_mode(self) -> None:
        """ The run is a dry run and will send no shift data.

            Args:
                None.

            Returns:
                None.
        """

        return None

    def shifts_sent(
            self,
            *,
            index: int,
            need_id: str | int,
            title: str,
            url: str,
            shifts: List[Dict[str, Any]],
            payload: Dict[str, Any]
    ) -> None:
        """ A batch of shifts was created for one opportunity.

            Every field a renderer might show is passed, because
            choosing between them is the renderer's job.  In check mode
            the batch was not sent, and the caller reports it the same
            way: what would have been created is what an operator is
            checking.

            Args:
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
                    duration.

                payload (Dict[str, Any]):
                    The request body, for a renderer that shows it.

            Returns:
                None.
        """

        return None

    def shift_data_invalid(
            self,
            detail: str | None = None
    ) -> None:
        """ No shifts were created, because the data did not validate.

            Args:
                detail (str, optional):
                    The validation error, when there is one.  Defaults
                    to None, because unvalidated data reports the same
                    way: returning in silence would read as success.

            Returns:
                None.
        """

        return None
