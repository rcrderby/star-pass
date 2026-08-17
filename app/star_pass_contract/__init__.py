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
from ._deciding import (
    edited,
    EditRefusals,
    replayed,
    resumable,
    sendable
)
from ._messages import (
    already_sent,
    already_working,
    blocked_message,
    has_moved,
    key_used_differently,
    no_such_job,
    no_such_run,
    not_interrupted,
    replay,
    REPLAY_ANSWERED,
    REPLAY_DIFFERENT,
    REPLAY_KINDS,
    REPLAY_RUNNING,
    send_in_flight,
    shift_count_moved,
    still_collecting,
    why_not_recollect,
    why_not_resume,
    why_not_send
)
from ._schemas import (
    ApiModel,
    IDEMPOTENCY_KEY_HEADER,
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
    EditRequest,
    EditView,
    EventOperationRequest,
    SendRequest,
    SkippedShiftView,
    UncollectedEventView,
    UncollectedGroupView,
    WindowRequest,
    WindowView
)
from ._views import (
    previewed,
    to_detail_view,
    to_edit_view,
    to_job_view,
    to_operations,
    to_preview_view,
    to_revision_views,
    to_run_view,
    to_uncollected_views
)

__all__ = [
    'ApiModel',
    'IDEMPOTENCY_KEY_HEADER',
    'REPLAY_ANSWERED',
    'REPLAY_DIFFERENT',
    'REPLAY_KINDS',
    'REPLAY_RUNNING',
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
    'EditRequest',
    'EditView',
    'EventOperationRequest',
    'SendRequest',
    'SkippedShiftView',
    'UncollectedEventView',
    'UncollectedGroupView',
    'WindowRequest',
    'WindowView',
    'already_sent',
    'already_working',
    'blocked_message',
    'has_moved',
    'key_used_differently',
    'no_such_job',
    'no_such_run',
    'not_interrupted',
    'previewed',
    'replay',
    'edited',
    'EditRefusals',
    'replayed',
    'resumable',
    'sendable',
    'send_in_flight',
    'shift_count_moved',
    'still_collecting',
    'to_detail_view',
    'to_edit_view',
    'to_job_view',
    'to_operations',
    'to_preview_view',
    'to_revision_views',
    'to_run_view',
    'to_uncollected_views',
    'why_not_recollect',
    'why_not_resume',
    'why_not_send'
]
