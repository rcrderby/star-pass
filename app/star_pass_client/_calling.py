#!/usr/bin/env python3
""" The shape of an operation call, written once.

    Both halves of the client answer the same generated methods, so
    both take exactly the same arguments from them: the method, the
    path, what is sent, the headers the operation requires, and the
    values the path names.  Written in each half, that shape would be
    two declarations of one agreement, and a half that gained a
    parameter the other did not would be a client whose two modes
    could not answer the same call.

    So the shape lives here and each half supplies only what it does
    with it: one sends a request, the other opens a connection.
"""

# Imports - Python Standard Library
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional


@dataclass(frozen=True)
class Operation:
    """ One call of one operation, as a generated method makes it.

        A record rather than five parameters, because they describe one
        call and always travel together.  Both halves would otherwise
        repeat the same signature, which is the same agreement written
        twice, and a sixth field would mean editing each of them.

        Attributes:
            method (str):
                The HTTP method the contract publishes it under.

            path (str):
                The templated path it is published at.

            body (Dict[str, Any], optional):
                What the operation is sent, or None for one that is
                sent nothing.

            headers (Dict[str, str], optional):
                Headers the operation requires, such as the idempotency
                key a send is made under, or None.

            parameters (Dict[str, Any]):
                Values the path names.  A mapping rather than keyword
                arguments, so a value named 'body' or 'headers' cannot
                be mistaken for either.
    """

    method: str
    path: str
    body: Optional[Dict[str, Any]] = None
    headers: Optional[Dict[str, str]] = None
    parameters: Dict[str, Any] = field(default_factory=dict)


class OperationCaller:
    """ What the generated operations call, and what a half must answer.

        Mixed into both halves of the client, above the generated
        methods, so that the one thing they share is inherited rather
        than repeated.
    """

    # What each half has to provide.  Declared rather than written out
    # as a method that raises: the shape is stated once, above, and a
    # second copy of it here would be a third place to keep in step.
    _answer: Callable[..., Any]

    def _call(
            self,
            method: str,
            path: str,
            body: Optional[Dict[str, Any]] = None,
            headers: Optional[Dict[str, str]] = None,
            **parameters: Any
    ) -> Any:
        """ Answer one operation.

            Args:
                method (str):
                    The HTTP method the contract publishes it under.

                path (str):
                    The templated path it is published at.

                body (Dict[str, Any], optional):
                    What the operation is sent.  Defaults to None, for
                    one that is sent nothing.  Named separately from
                    the path values, which fill the template: a body
                    that arrived among them would be interpolated into
                    the address.

                headers (Dict[str, str], optional):
                    Headers the operation requires, such as the
                    idempotency key a send is made under.  Defaults to
                    None, and named separately for the same reason the
                    body is.

                **parameters (Any):
                    Values the path names.

            Raises:
                ApiProblem:
                    If what was asked for cannot be answered.

            Returns:
                answer (Any):
                    What the operation answered.
        """

        return self._answer(
            operation=Operation(
                method=method,
                path=path,
                body=body,
                headers=headers,
                parameters=parameters
            )
        )
