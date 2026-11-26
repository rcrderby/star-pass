#!/usr/bin/env python3
""" Wording shared by the package's messages. """


def counted(
        count: int,
        noun: str,
        plural: str = ''
) -> str:
    """ Return a count with its noun, singular for one.

        Args:
            count (int):
                How many.

            noun (str):
                The singular noun.

            plural (str):
                The plural, when it is not the noun and an 's'.

        Returns:
            text (str):
                Such as '1 shift' or '3 opportunities'.
    """

    many = plural or f'{noun}s'

    return f'{count} {noun if count == 1 else many}'
