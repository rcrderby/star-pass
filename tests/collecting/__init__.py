""" Collecting a calendar window into a stored run.

    A package rather than a plain directory, so that the conftest here
    is 'collecting.conftest' and the one above it stays reachable as
    'conftest'.  Without it the two share a name and the directory
    cannot read the arrangement the rest of the suite is built from.
"""
