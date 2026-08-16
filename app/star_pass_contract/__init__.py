#!/usr/bin/env python3
""" The shapes the contract publishes, and how records become them.

    A package of its own, between the core and the two things that
    speak the contract.  The service answers over HTTP and the command
    line client answers from the same database in the same process
    (D2), and both have to produce the same answer, so the shapes and
    the conversion belong to neither of them.

    Its own package rather than a module inside 'star_pass_api',
    because importing anything from that package runs its '__init__'
    and pulls in the web framework.  A command line client reading a
    run locally would then have acquired a server as a dependency,
    which is the thing D2 exists to prevent.  Nothing here imports
    FastAPI, and a test holds that true.

    Not inside 'star_pass' either: the core knows what is stored, and
    these are the shapes a caller is shown, which are allowed to
    differ and are versioned with the API rather than with the domain.
"""

# Imports - Local
from ._messages import (
    already_sent,
    already_working,
    has_moved,
    no_such_job,
    no_such_run,
    why_not_recollect
)
from ._schemas import (
    ApiModel,
    BlockerView,
    EventRoleView,
    EventView,
    JobView,
    CollectRequest,
    LogEntryView,
    MatchView,
    OpportunityView,
    PreviewRowView,
    PreviewTotalsView,
    PreviewView,
    RecollectRequest,
    RevisionView,
    RunCountsView,
    RunDetailView,
    RunView,
    WindowRequest,
    WindowView
)
from ._views import (
    to_detail_view,
    to_job_view,
    to_preview_view,
    to_revision_views,
    to_run_view
)

__all__ = [
    'ApiModel',
    'BlockerView',
    'CollectRequest',
    'EventRoleView',
    'EventView',
    'JobView',
    'LogEntryView',
    'MatchView',
    'OpportunityView',
    'PreviewRowView',
    'PreviewTotalsView',
    'PreviewView',
    'RecollectRequest',
    'RevisionView',
    'RunCountsView',
    'RunDetailView',
    'RunView',
    'WindowRequest',
    'WindowView',
    'already_sent',
    'already_working',
    'has_moved',
    'no_such_job',
    'no_such_run',
    'to_detail_view',
    'to_job_view',
    'to_preview_view',
    'to_revision_views',
    'to_run_view',
    'why_not_recollect'
]
