# CLAUDE.md

Guidance for Claude Code (and human contributors) working in this
repository.

## Overview

star-pass automates bulk volunteer-shift operations on the Galaxy
Digital Amplify (Get Connected) platform for the Rose City Rollers. It
reads events from Google Calendars, matches each event to an Amplify
"need" via a keyword data model, and creates the corresponding shifts
through the Amplify API. It is run once per month.

## Repository layout

- `app/` is the Python import root. Modules import as
  `from star_pass.<module> import ...` (the `app/` directory is placed
  on `sys.path`, not the repository root).
- `app/__main__.py` — CLI entry point and dispatch. Two ways in: a
  command word selects something the API publishes (`star_pass_cli`),
  and `-s/--post-slack-summary` selects the Slack sign-up summary,
  which the API deliberately does not publish. **The `-s` path opens no
  database**, and a test holds that: it is the only thing in the
  repository on a schedule, the runner is ephemeral with no volume, and
  a dispatcher that opened one for every invocation would be writing
  into a container about to be destroyed. `runs collect` and
  `runs send` are what create shifts.
- `app/star_pass/gcal_data.py` — read a Google Calendar window
  (`GCALData`): the paged request and the filter that removes items
  which must not become shifts. Construction sends nothing; the caller
  supplies the window, because a run carries its own. `read_window`
  reads it twice — as the deployment searches it and, when the two
  differ, whole — because the events nobody looked for are the ones
  the configured query strings never returned. Why an item must not
  become a shift is `exclusion_reason`'s single answer, read by the
  filter and by the record of what a run left out.
- `app/star_pass/_gcal_time.py` — reading a search window's bounds
  (`resolve_window`) and the zone an offset-less value is read in
  (`gcal_timezone`). A bound without a UTC offset is local time in
  `GCAL_TIMEZONE`, which is what makes Daylight Saving automatic.
- `app/star_pass/_helpers.py` — shared helpers (`Helpers`), including
  `send_api_request` and `amplify_headers`, which is read when a
  request is about to be made rather than held from import time, so a
  deployment that rotates the credential and restarts nothing still
  sends the current one.
- `app/star_pass/_defaults.py` — central configuration and constants,
  including the data-model file paths.
- `app/star_pass/_models.py` — reads `shift_info.yml` and
  `slack_role_labels.yml` on first use and caches them
  (`get_shifts_info`, `get_slack_role_labels`). Separate from
  `_defaults` because `_logging` reads its level from `_defaults`, so a
  reader there could not log without an import cycle.
- `app/star_pass/_database.py` — SQLite connection, schema and the
  helpers every statement goes through (`connect`, `transaction`,
  `execute`, `query`). The database path comes from
  `STAR_PASS_DATABASE_PATH`; the schema version lives in the file's
  own `user_version` pragma.
- `app/star_pass/_records.py` — the frozen dataclasses the repository
  layer stores and returns (`Run`, `Revision`, `Opportunity`, `Event`,
  `EventRole`, `UncollectedEvent`, `LogEntry`).
- `app/star_pass/_repository/` — runs, their revisions, the events in
  each revision, what each run's window held and the run left out, the
  titles the data model did not match, the
  `change_log` of edits made to them — **what was done and the values
  it carried, never a sentence** (D27): a wording stored in a column
  cannot be changed without rewriting every row already holding the
  old one, so each client words an entry from `LOG_ACTIONS` the way it
  words a run status, and a test holds each client's map to that
  tuple. The jobs
  that long operations are watched through, the shifts a send put into
  Amplify, and the reservations made against idempotency keys. The last
  two are separate because they answer different questions — which rows
  a run has already created, and what an already-made request answered
  — and one key covers many shifts, so neither fits inside the other.
  A sent shift is keyed by the run plus the four columns a shift is
  identified by (D16), and its reference to the run does not cascade,
  because that record is never purged (D12). Every
  statement that touches the
  database is in this package and no SQL appears outside it, so the
  core stays testable without a database and a move to another one is
  contained. Only facts are stored: a run's current revision, the
  time it was last revised, its counts and the job still working on
  it are derived, and so are shift length and duplicates. The counts
  and the active job are derived in the same statement that reads a
  run, so a list of runs costs one query rather than one per run.
- The one table belonging to no run is `unmatched_titles`
  (`_repository/_unmatched.py`). A row is one **sighting** of a title
  no category matched, and **a run contributes at most one per
  title**: a window holding the same unmatched title four times saw
  one title, and collecting that window again is one window read
  twice. That rule is in the repository rather than in its callers,
  because the caller that most needs it is the collection —
  recollecting is how a corrected model is picked up, so a count that
  grew with each one would report the operator's own fixing as the
  title coming back. What the count therefore measures is the runs a
  title turned up in, plus any sighting recorded by hand, which is the
  question being asked of it. Read back they are counted into one
  entry per title in a calendar. Append-only — nothing updates a row
  or deletes one — and its reference to the run it was noticed in does
  not cascade, because a run is a window that is eventually superseded
  and what the model is missing outlives it.
- **A collection records the titles it could not match** (`_collect`'s
  `_record_unmatched`), in the transaction that stores everything else
  one reading of a window produced. An event the model matched nothing
  for has no roles, which is the same fact that blocks the send, so
  nothing new has to be detected. Written by the collection rather
  than left to whoever notices: a log that depended on somebody
  remembering would hold what people remembered rather than what
  happened, and the count would measure diligence.
- `app/star_pass/_derived.py` — the things the `Event` record
  deliberately leaves out, worked out from what it does hold: how long
  the shift is, whether an opportunity's maximum shortened it, whether
  another event in the revision would create the same shift, whether
  the event blocks the run for want of a match, and whether it may be
  put back to unassigned (`may_unassign`, true only where the
  collection matched nothing, which is the rule `unassign` refuses by
  and the rule the chooser draws its option from). Pure functions
  over records, in the core rather than the service, so the CLI shows
  the same figures the web interface does. A run's own figures are
  derived in the repository instead, because they are counts over rows
  the caller has not read.
- `app/star_pass/_collect.py` — turning a calendar window into a
  stored run: read the calendar, match each title to a category, and
  write the events, their roles and the opportunities they name. An
  event that cannot become a correct shift stops the run and is named,
  including two cases about what a stored event can express: a
  category whose need IDs disagree about their offsets, and a shift
  that would run past midnight. It also records what it did **not**
  collect, with the reason for each — a title the deployment never
  collects, an all-day or untitled event, or an event no configured
  query string returned. Stored while the window is read and never
  worked out later: the figure is shown on every reading of the run,
  and a live calendar read would cost a request per look and give the
  run a second opinion about its own window.
- `app/star_pass/_building.py` — the event a run stores and the
  opportunity it names, built below both the things that store one
  (`event_from`, `opportunity_read`). A collection builds one per event
  its window held; pulling an event in by hand builds one from a stored
  row. A hand-added event that reached its shift times a second way
  would be a row nobody could tell from a collected one until Amplify
  received a different shift.
- `app/star_pass/_adding.py` — pulling into a run an event the search
  missed (`add_event`). **Only the `search` reason may be pulled in**;
  the other three describe events that cannot become a correct shift
  and are refused here rather than by a disabled button. The record of
  what the window left out is **not** deleted — what keeps a pulled-in
  event off the Not collected list is the revision holding it, which
  is what lets reverting to the first revision give it back. A
  pulled-in event may name an opportunity the run has never read, so
  the run gains it, and that is the one upstream request the operation
  makes.
- `app/star_pass/_revising.py` — sealing the revision a run is working
  in (`seal`) and going back to an earlier one (`revert`). An edit
  changes a revision in place, so sealing is what fixes a point in
  that work as something to come back to, and reverting is coming
  back to it. Each opens a revision holding a copy — of the current
  one, or of the one being gone back to — and leaves every other
  revision's rows where they are. **One revision per revert**: what
  it leaves is already readable at its own number, so there is
  nothing to fix in place first and sealing before reverting would
  add a revision holding an identical copy of the one before it.
  Reverting to revision 1 also drops the events added by hand,
  because that revision is the run as the calendar gave it, and the
  row saying the collection left one out was never deleted — so the
  current revision no longer holding it is what offers it again.
  **No `change_log` entry** from either, because the change count on a
  revision is what was done *while it was current*, and one written as
  a revision opens would have every sealed revision starting at a
  change nobody made; who sealed or reverted is recorded against the
  idempotency key instead (D13). A run that has collected nothing has
  no revision to seal and none to go back to, and both refuse it: the
  first revision belongs to the collection, which is the one that
  says what filled it. **What kind of revision each is is not a
  caller's to say**: it follows from whether the revision replaces
  what was there and whether the run held anything, so the repository
  works it out and nothing above it can disagree with what happened.
  A revert is the one that also records a number, because which
  revision a run went back to is not derivable from anything else.
- `app/star_pass/_shift_timing.py` — what a category asks of an event
  and the shift times it produces (`role_timings`, `shift_times`).
  Below both callers: collection works them out from a calendar item
  and an edit works them out again, and two copies would eventually
  disagree — a run that previews one shift and sends another. The two
  things a stored event cannot express are refused here, so a
  collection and an edit refuse them alike: a category whose need IDs
  disagree about their offsets, and a shift running past midnight.
- `app/star_pass/_editing.py` — one user action's worth of operations
  applied to a run's current revision (`apply`), and the write that
  stores them (`edit`). What each operation is called lives in
  `_records.EDIT_OPERATIONS`, beside the other vocabularies the
  contract publishes, because three things read it: the operation a
  request carries, the table here that answers it, and the wordings
  each client keeps for `change_log`. Operations apply in order, each seeing what
  the one before produced, and **a call is applied whole or not at
  all**: a bulk nudge that would push one event of thirty out of its
  day leaves all thirty alone, because a partly applied action is one
  the reviewer cannot see the shape of. `apply` writes nothing; the
  caller decides when the answer becomes durable.
- `app/star_pass/_event_edits.py` — what changes about *one* event,
  below the operations that ask for it. **An edit moves the shift
  times; the calendar times never move**: they are what the calendar
  said, so a run can always say what it started from. That is what
  lets an undo recompute the original from the calendar times and the
  offsets of the category the collection matched rather than storing a
  copy of it. A maximum does not pull a hand-set end time back in — a
  maximum shortens what the offsets produced, and a person setting a
  time has overridden that. **The category is the one thing an undo
  cannot recompute** — the title matched it under a data model that may
  since have changed — so the event carries it (D26), and
  `under_category` is what places an event under one, for a reviewer
  choosing a different opportunity and for the undo alike.
  The same arithmetic answers whether an event *has* been edited
  (`was_edited`), which is the `edited` an event is published with and
  what the review screen offers an undo on: nothing stored says so, and
  a client working it out would be a second copy of `_shift_timing`. It
  is false where the undo could not be carried out at all — a category
  the data model no longer holds — because that is the refusal the
  operation itself would raise, and a row said to be editable is a row
  offered a control that fails. Where the collection matched nothing, an
  undo puts the row back to **Unassigned**, which is where it began -
  a state with a name, offered in the chooser on that row and on no
  other, so landing back in it is putting the row back rather than
  stranding it (D29).
- `app/star_pass/_opportunities.py` — reading an Amplify opportunity:
  its title, the shifts it already holds, and the public address it is
  published at. Below every caller, because collection stores the
  title on the run, the shift preview reads the same one, and the
  preview and the send both ask what Amplify already has. One request
  answers title and shifts together. A shift whose times cannot be
  read is logged and left out, which is the only case where a row that
  exists is counted as absent; a shift crossing midnight is left out
  silently, because collection refuses to store one and so no run
  could have created it.
- `app/star_pass/_credentials.py` — asking Amplify whether the
  credential this process holds still works (`check_credential`). The
  only thing published about it, and deliberately: no endpoint
  replaces a credential, because one that could rewrite the service's
  own production credential is the highest-value target in the system
  for the least benefit (D8). The answer is whether one small
  authenticated read was accepted, plus the **last four characters** —
  enough to tell two credentials apart and no use to whoever reads
  them. The read names no need, so a deployment whose data model
  matches nothing is not told its credential is broken, and the row it
  returns is discarded unread. A credential Amplify refuses is
  returned as an answer rather than raised: whether it works is what
  was asked.
- `app/star_pass/_preview.py` — what sending a revision would create,
  worked out before it does: totals, a row per Amplify opportunity,
  the shifts Amplify already has, and every reason an event cannot be
  sent. Grouped by opportunity and never by category, and counted by
  shift identity (`_derived.shift_identity`) rather than by how many
  events there are. In the core because the CLI previews the same run.
  A shift Amplify already holds is reported as skipped rather than
  counted in what would be created, so the number the confirmation
  restates (D11) is the number of rows that arrive. The live answer is
  a required parameter with no default: a preview cannot be produced
  without having asked. `asked_for` and `split_by_existing` are the two
  answers the send works from as well — written twice, a preview and a
  send could differ about a row and nothing would say so.
- `app/star_pass/_send.py` — putting a revision's shifts into Amplify,
  the one thing star-pass does that cannot be undone. **One request per
  opportunity, not per shift**: Amplify's create endpoint takes an
  array, and a single-shift request that times out is exactly as
  unknown as a batch that times out, only smaller. Per-shift
  idempotency is unaffected, because it was never about the unit of the
  request — the record is per shift and so is the decision to skip.
  Each opportunity is read from Amplify in the step that writes to it,
  not all of them once at the start, because minutes pass between the
  first batch and the last. A batch is recorded only once its request
  succeeded, so a batch whose answer never arrived leaves the run
  `partly_sent` and the next send reads the opportunity and sends the
  difference; those rows are then in Amplify and not in the run's sent
  record, which says what the run saw itself create.
- `app/star_pass/_retention.py` — forgetting what a run leaves behind
  (`sweep`), on three axes rather than one window (D12, D20). A job's
  event log expires by age and the job row outlives it; a run's middle
  revisions go once the run is untouched, while revision 1 and the
  current one never do; an unmatched title goes when the **data model
  matches it**, with a year as a backstop, because its value is that
  it accumulates and any expiry short enough to protect a name would
  destroy the count. A title is forgotten whole. The sent record is
  never purged and is deliberately absent. Nothing here is reachable
  over the API and nothing should be: retention removes a run's
  leavings, a caller does not.
- `app/star_pass/_job_runner.py` — `JobRunner`, which runs a job's
  work on a thread and records how it ended, and `JobReporter`, a
  `Reporter` that writes the core's progress calls to the job's event
  log. Both are in the core, not the service: neither is about HTTP,
  and the CLI runs the same operations locally.
- `app/star_pass/_exceptions.py` — `StarPassError` and the three
  subclasses the core raises: `ConfigurationError`, `ValidationError`,
  `UpstreamError`. The core raises; the CLI decides the exit code.
- `app/star_pass/_reporting.py` — `Reporter`, which accepts progress
  and result events and discards them. The default, so the core runs
  unobserved; the CLI passes `TerminalReporter` from `__main__.py`.
  **A step is named, not described**: `step_started` carries an
  identifier from `STEPS` and, where a step works on one thing, what
  it is working on. The words are each client's — `STEP_PHRASES` in
  `star_pass_cli/_sending.py` for both the terminal renderer and the
  job watcher, and `web/phrases.json` for the browser — because a
  job's event log is read back over the API by clients that word
  everything else the contract publishes themselves. A collection
  reports five steps, not the four the design was drawn with: reading
  the calendar and reading the Amplify opportunities are two upstream
  services, and which of them stopped a collection is what an
  operator needs to see. `sending_started` carries how many
  opportunities the send will work through, and `opportunity_sent` is
  reported for **every** opportunity, including one Amplify already
  held every shift for — reported only when rows were created, a
  screen drawing a row per opportunity could never finish that row.
- `app/star_pass/_logging.py` — package logger setup (`get_logger`);
  level via the `LOG_LEVEL` environment variable. Diagnostics and status
  flow through `logging`; report data goes to the caller's
  `Reporter` (`app/star_pass/_reporting.py`), which the CLI renders.
- `models/shift_info.yml` — shift data model: per calendar, `categories`
  (need IDs, slots, timing) each with an `aliases` list of title
  keywords. Add a team by adding its keyword to a category's `aliases`.
  `Helpers.search_shift_info` matches an event title to a category by the
  longest alias whose words all appear in the title, falling back to a
  fuzzy match (`FUZZY_MATCH_THRESHOLD`); an unmatched title logs a
  warning and uses the `default` category, whose need IDs are empty. An
  empty need ID cannot become a shift, so the event is collected and
  named as unmatched, and stops the **send** rather than being dropped.
  See the "Unmatched event titles" section of `README.md` for the
  operator workflow.
- `app/star_pass_api/` — the remote surface over the core: the
  application factory (`create_app`), the service's own `_defaults.py`,
  `_problems.py`, `_security.py`,
  `_storage.py` (how it reaches the database), `_limiting.py` (how
  often one caller may ask for something), and a module per group
  of endpoints. The shapes that cross the wire are not here: they are
  in `star_pass_contract`, because the command line client sends and
  receives the same ones. A separate
  package from `star_pass`, because the core knows nothing about HTTP
  and this package holds no domain logic. Run it with
  `uvicorn --factory star_pass_api:create_app`.
- `app/star_pass_bff/` — the frontend's own service: the browser
  reaches the API only through it, and holds **no** credential (D4).
  It keeps the token server-side and attaches it to what it forwards,
  so cross-site scripting cannot exfiltrate what is not in the page;
  same origin, so there is no CORS configuration at all. A separate
  container from the API with no credential mount on it, because the
  internet-facing process must never have the Amplify secret on its
  filesystem (D17). It holds **no domain logic and imports nothing of
  the core** — a test in `tests/test_bff_configuration.py` holds that
  in a subprocess, because this suite has imported the core already
  and `sys.modules` would say nothing. `_sessions.py` is the only
  module that decides what a session is (D18), `_proxy.py` passes
  requests on and streams what the API streams, and `_configuration.py`
  refuses to start half-configured. Run it with
  `uvicorn --factory star_pass_bff:create_app`. It serves `web/` at
  its root, and refuses to start when there is no page there. It also
  answers the page's own paths with the page (D28) — `SCREEN_PATHS` in
  `_defaults.py`, registered between the proxy and the mount, because
  the mount would answer `/settings` with a 404 before they were
  reached. **Enumerated, never a catch-all**: a blanket fallback would
  hand a browser the page where it asked for a module, at a 200, and
  turn the loud 404 that `tests/test_web_page.py` exists to catch into
  a screen that silently never draws.
- `web/` — what the frontend serves at `/`. It lives here and not in
  the design project because it can work from no other origin: the
  token a write carries is a cookie the page reads, the session cookie
  is `SameSite=Strict`, and a write whose `Origin` names another host
  is refused. A page served elsewhere would fail all three, and
  answering that with CORS would be the boundary leaking rather than
  moving (D4, D18). **No framework and no build step**: the modules
  under `js/` and the CSS under `css/` are what is committed
  and what a browser is given, and the image copies the directory as
  it is. The state a framework would reconcile is mostly the server's
  — an edit returns the whole revision — so what stands in for one is
  a `render(state)` per region and `dom.js`. The review screen is
  `js/review/`, split by what a reader looks at rather than by
  component kind: the header, the banners, the table and the change
  log, composed by `screen.js`, which owns the client-only state the
  design lists and redraws the body while leaving the header alone —
  which is what keeps an open popover open while a filter is applied.
  **An edit is one call and its answer is what the screen redraws
  from**: the service applies an action whole or not at all and hands
  back the revision it produced, so a bulk nudge over thirty rows is
  one operation naming thirty, one key and one log entry. One at a
  time — every control is disabled while a call is in flight, because
  two edits in the air would each be applied to a revision the other
  had already changed. A key names one action and is never reused for
  the next: it makes a *resend* safe, and two nudges are two actions
  that must move the shift twice.
  The revision picker seals a revision and reverts to one, both
  keyed. A seal answers with the revision the work moved to and a
  revert with the run in full, and neither is the whole of what the
  picker draws, so the revisions are read again after both rather
  than adjusted in the page. **The current revision is offered no
  revert**: the service would take one and spend a revision arriving
  where it started. A revert to revision 1 drops the events added by
  hand, so what the second tab holds is let go of and asked for
  again.
  `js/review/uncollected.js` is the screen's second tab: what the
  window held and the run left out, grouped by reason. **Whether a
  row may be pulled in is `addable`**, which the server answers, and
  the reason a group is drawn under is never read to decide it — the
  two line up today and a client deciding for itself would go on
  disagreeing quietly once they stopped. A pulled-in row keeps its
  entry and stops being addable, so the pull-in is followed by a
  re-read rather than by striking the row off. Its last section is
  the log kept for the next edit of the shift data model, which
  belongs to no run and has nothing to remove on it: a title leaves
  that log when the model matches it (D20), which is the edit
  somebody notes one in order to make.
  `js/collect/` is the drawer a run is asked for in and the screen
  that follows the job doing it. The drawer is where the two
  conversions live that no other screen makes: a window preset is
  worked out from **today in the server's zone**, never the browser's
  (D16), and the inclusive last day a person types becomes the
  exclusive `end` a request takes. Collect and recollect carry no
  `Idempotency-Key`, so the drawer disables every control from the
  moment one is in the air -- that is the whole of what stops a
  double-clicked button becoming two runs. The collecting screen draws
  **five** steps (D22), listed in `collect/steps.js` and bound to what
  a collection really reports by a test in
  `tests/collecting/test_collect.py`. It marks the running step failed
  when the job reports a failure, because `step_failed` is called
  nowhere in the core and the collection stops at the first thing that
  raises, so there is never more than one. It offers no Cancel: the run
  is minted by the request and the contract publishes no way to stop a
  job, so the only honest offer is to stop watching, which "Leave this
  running" already is.
  `js/watching.js` is how a screen follows a job -- one place, because
  a collection and a send follow one identically and what differs is
  what the frames mean. `js/modal.js` is what a dialog and a drawer
  both are -- a panel over
  a scrim that takes focus, keeps Tab inside itself and gives focus
  back. Below both, because that is the part which is easy to get
  subtly wrong and impossible to see in a diff.
  `js/sending/` is the preview, the send confirmation and the send as
  it happens, which are one movement over one answer: the preview says
  what would be created, the confirmation restates it (D11), and the
  request carries its `willCreate` as `expectedShiftCount`, so a
  screen that no longer agrees with Amplify is refused rather than
  acted on. **The preview is the duplicate check** — one request reads
  every opportunity live, so nothing on that screen is worked out from
  the events. **A send is a call and then a stream**: the call answers
  with a job, and the browser follows `GET /v1/jobs/{id}/events`,
  which replays from its first frame for a client that is not
  resuming. That is the whole of what leaving a send running and
  coming back to it means, and it is why the opportunity count comes
  off `sending_started` rather than out of the preview — a reload has
  no preview, and reading one mid-send would ask Amplify about the
  opportunities being written to. A run carrying an `activeJobId` for
  a send opens on that screen rather than on the review screen.
  **A run carrying an `interruptedJobId` does not** (D10): an
  interrupted job stays interrupted until somebody acts on it, so a
  run that opened on one would be a run whose way back came straight
  there again — unlike a job still running, which finishes and stops
  being the run's. It is a banner on the review screen instead, and
  the banner opens the screen for that job's kind. Resuming a send is
  the third way a write to Amplify starts and goes through the same
  confirmation as a retry (D11), reading the preview first: the
  request carries no count, so what the confirmation buys there is
  that somebody read what is about to happen. **A resumed job keeps
  its event log**, so one stream can carry the attempt that was
  interrupted and the one that replaced it — a second
  `sending_started` begins an attempt, and the rows let go of what
  the earlier one reported, because an opportunity the first attempt
  created is one the second is told Amplify already holds. The
  opportunity an interrupted send was working on is drawn as
  `unknown` rather than failed: nothing refused anything, and what
  became of that request is a question for Amplify.
  `js/settings/` is what the deployment was configured with, read
  from `GET /v1/config` and `GET /v1/version`, and it is read only
  because the surface is: **no endpoint writes a credential** (D8),
  so the screen says that rotation happens in the environment rather
  than offering a control that fails. The credential is **not** read
  when the screen opens — the only thing published about it is what
  `POST /v1/credentials/test` answered, which is a real request to
  Amplify and rate-limited for that reason, so the card says it has
  not been checked until somebody asks. The design's Configuration
  table has a source column and this one does not: `_defaults` does
  not record where a value came from, so the column would be this
  page inventing an answer about somebody else's process. The motion
  setting lives here, beside the theme control in the bar, because
  both are kept in this browser and nowhere else.
  `api.js` is the only
  thing that talks to the service, and holds the three rules no screen
  should repeat: the CSRF header on a write, an `Idempotency-Key`
  naming one action on the four operations that need one, and a
  problem document whose reason is withheld at 500 and above.
  Inter and the Phosphor icons are under `assets/` because the
  Content Security Policy is `default-src 'self'` and the deployment
  is meant to work on a tailnet with no route out (D14); the policy
  was not relaxed to load them, and must not be. `phrases.json` holds
  the words the page puts on the identifiers the contract publishes,
  bound to what the core publishes by `tests/test_web_phrases.py` —
  a Python test for a file the browser reads, because there is no
  build step and no JavaScript test runner.
  `tests/test_web_page.py` is there for the same reason and answers a
  different question: every path the page names and every module a
  module imports is a URL a browser fetches, so a misspelled one is a
  screen with no styles or one that never draws, and nothing else in
  the repository would notice. `tests/test_web_routes.py` is the
  third: it holds the route table in `js/router.js` to the frontend's
  `SCREEN_PATHS`, because a path one of them knows and the other does
  not is a screen that works until somebody reloads it — and it tests
  the refusals as well as the answers, since a test that only proved
  the screens are served would pass on the catch-all D28 rejects.
  **Nothing sets a `style` attribute from a script** — the policy
  refuses one, so a size worked out while the page runs is a custom
  property the CSS reads, which is how the send's progress bar is
  drawn. `docs/design` holds a
  prototype of the screens, which is a reference and is not ported.
- `compose.yaml` and `deploy/caddy/` — the deployment (D5, D14, D17).
  Caddy is the only container with a published port; the frontend and
  the API share a network Caddy is not on, so the path to the
  credential-holding service runs through the process that checks a
  write came from its own page. The credential file and the database
  volume are attached to the API service alone. HSTS is not enabled:
  it ships as an example file imported by a glob, to be turned on once
  the domain is settled and not before.
- `docs/api/openapi.json` — the generated OpenAPI 3.1 contract,
  written by `scripts/generate_contract.py`, which also writes the
  client generated from it.
- `docs/architecture.md` — the deployment and the paths a run takes
  across it, in two pictures. The SVG files beside it are generated by
  `scripts/generate_architecture.py` from the boxes and coordinates in
  that script; edit those and run it rather than editing an SVG.
  `tests/test_architecture.py` fails while a committed picture
  disagrees with the generator, and holds the networks drawn to
  `compose.yaml` and the addresses drawn to the contract.
- `app/star_pass_contract/` — the shapes the contract answers with
  (`_schemas.py`, with the preview's five in `_preview_schemas.py`
  beside it, because the preview is one answer with a boundary of its
  own and the file had reached the thousand-line cap) and the shapes a
  caller sends (`_requests.py`, which
  reads the first for the base they share and is read by nothing in
  it: a request is checked on the way in and a view is built on the
  way out), how stored records become them (`_views.py`), what a
  caller is told when a request is refused (`_messages.py`), and the
  refusals themselves (`_deciding.py`, which reads what a decision
  needs and makes it — a half that read one fewer thing would refuse a
  different thing while saying the same words). Nothing there decides
  what a refusal *is* to a caller: a status code belongs to the
  transport, so each half raises its own kind of failure carrying the
  reason. Its
  own package between the core and the two things that speak the
  contract: the service answers over HTTP and the command line client
  answers from the same database in the same process (D2), and both
  must produce the same answer, so the conversion belongs to neither.
  **Nothing here imports the web framework**, and a test holds that
  true — importing anything from `star_pass_api` runs its `__init__`
  and pulls in FastAPI, which would give the command line client a
  server as a dependency to read a run locally.
- `app/star_pass/_reading.py` — which repository reads answer a
  question about a run, and reading them on one connection. Below both
  callers, because the service and the local client ask the same
  questions and a mode that read one fewer thing than the other would
  answer differently with nothing saying so.
- `app/star_pass_cli/` — the commands (`runs list`, `runs show`, `runs
  revisions`, `runs uncollected`, `runs preview`, `runs collect`, `runs
  recollect`, `jobs show`, `jobs watch`, `jobs resume`, `config show`,
  `config credential` and `config unmatched`), which work
  against the local
  database by default and a service when `--api-url` or
  `STAR_PASS_API_URL` names one (D2). Each is a row in
  `_commands.COMMANDS` naming the contract operation to ask and the
  renderer to show its answer with, and the same rows build the
  parser, so a command the command line offers and the dispatcher does
  not answer is not expressible. Separate from
  `__main__.py`, which holds the Slack summary run mode: the
  contract deliberately publishes no summary, so it stays local. A
  command renders the answer a client gave and never knows which mode
  produced it — that is what makes one renderer correct for both.
  **The command line covers what the web interface cannot** — the
  Slack summary, troubleshooting, and the monthly workflow, which has
  to work with no server running. Parity with the web interface is not
  a goal (D2), so an operation whose home is the review screen is
  published by the API and declared unavailable in local mode. Five
  are: editing a run's events, pulling one in, sealing a revision,
  reverting to one, and recording a title the data model did not
  match. Do not add commands for them. Reading what a run left out
  **is** a command, and so is reading the unmatched titles, because
  asking why an event is not in a run is troubleshooting — the line
  falls between reading a list and acting on it.
  One command is **not** one of those rows: `retention sweep`
  (`_maintenance.py`) applies the retention policy to the local
  database. It names no contract operation and takes no `--api-url`,
  because the contract publishes no deletion on purpose — so it could
  not be a `COMMANDS` row without weakening the two tests that hold
  that table to the published surface. It exists because the service's
  timer covers a deployment and not a checkout with a database file,
  where the windows would never be applied at all.
  `_render.py` shows what a run holds and `_sending.py` shows what
  would become of it — the preview, the restatement a send is
  confirmed with, and the job that does it — with the second importing
  its table and label primitives from the first. `_configuration.py`
  shows what the deployment was configured with, which is neither, and
  imports the same primitives.
- `app/star_pass_client/` — the client the command line client uses
  to reach a remote service, and the local half that answers the same
  operations from the database in this process (D2). Both inherit the
  same generated operations, so they cannot offer different methods;
  only how an answer is reached differs. An operation with no local
  answer is listed in `_local.UNAVAILABLE` with the reason, and a test
  holds that list to exactly what the contract publishes and the
  handlers do not cover — which is what keeps a gap deliberate rather
  than forgotten, and what makes adding an endpoint a decision about
  both modes. `_operations.py` is **generated** from
  the committed contract, one method per operation, so an endpoint the
  client cannot reach is a failing test rather than something nobody
  notices (D15). `_client.py` is written by hand and holds everything
  the generated methods call: the session, the credential, and the
  mapping of a problem document onto an exception. Generated code is
  excluded from the duplicate-code check, which one method per
  endpoint would otherwise trip.
- `tests/` — pytest suite.

## Running the workflow

```bash
# 1. Collect a calendar window into a run. --last-day is the last day
#    covered, not the day after it.
./app/__main__.py runs collect \
    --calendar events --start 2026-09-01 --last-day 2026-09-30

# 2. Read what sending it would create, then send it. The send asks
#    first (D11) and refuses where there is no terminal to answer from.
./app/__main__.py runs preview <run_id>
./app/__main__.py runs send <run_id>

# 3. Delete a run that never sent. Asks first, restating what goes
#    (D11), and is refused on a run that has sent or one something is
#    working on (D24).
./app/__main__.py runs delete <run_id>

# 4. Post a Slack sign-up summary (-C true is a dry run). The one run
#    mode flag left: the API deliberately publishes no summary, so
#    nothing replaces it.
#    -d/--days sets the window, counting today as day one; the default
#    is 1 (today only). Nothing in the window means nothing is posted.
#    -N repeats, comma-separates, or takes - to read IDs from stdin;
#    omitting it falls back to SLACK_SUMMARY_NEED_IDS.
./app/__main__.py -s -N <need_id> -C true
./app/__main__.py -s -N <need_id>,<need_id> -d 2 -C true
```

## Development

The environment setup and the test and lint commands are in the
"Development" section of `README.md`; run all of them before pushing.
Do not repeat those commands here, because the duplicate-code check
(jscpd) runs over Markdown and its threshold is zero.

The notes below are the ones that are not obvious from the commands.

### Tests

- Tests must be hermetic: no network calls and no real `.env`.
- `tests/conftest.py` sets dummy credentials before import.
- Mock `Helpers.send_api_request` to avoid live API calls.
  Constructing `GCALData` sends no request on its own.
- A test that asserts a failure should assert the logged message as
  well as the exit, so an error stays actionable.

### Linting

- flake8 enforces a 79-character line limit; pylint allows 100 and caps
  a module at 1000 lines.
- Super Linter also runs Node-based linters that are easy to miss
  locally: markdownlint, textlint (which enforces a terminology list),
  and jscpd. Prose changes can fail continuous integration even when
  the Python linters pass.
- Bandit is a separate workflow and scans the whole repository,
  including `tests/`.

- flake8 enforces a 79-character line limit; pylint allows 100.
- Test files start `test_*` methods, so add
  `# pylint: disable=missing-function-docstring,missing-class-docstring`
  at the top of new test modules.

## Secrets and safety

- `.env` is git-ignored and secret-scanned by gitleaks, both in CI and
  via the local pre-commit hook (`.pre-commit-config.yaml`; install with
  `pre-commit install`).
- `.claude/settings.json` denies reading `.env` from Claude Code
  sessions.
- `Helpers.redact_secrets` scrubs API keys and bearer tokens from error
  output; keep new logging paths routed through it.

## Coding conventions

- Match the existing style: full `Args:` / `Returns:` docstrings and the
  explicit `return None` idiom.
- Put configuration and constants in `_defaults.py`; do not hardcode
  values in logic modules.
- Amplify has no update endpoint for an individual shift (only create,
  and delete by shift ID); design shift changes around that constraint.
- Check mode (`-C true`) does not create or send anything, but it is not
  request-free: the shift preview reads each opportunity title with a
  `GET /needs/{id}`, so `AMPLIFY_TOKEN` is required in both modes.
- The core neither prints nor exits. It returns values and raises the
  typed exceptions above; display and process control belong to the
  client. Do not add a `print`, a `sys.exit`, or argument parsing under
  `app/star_pass/`.
- Stored state is reached through `app/star_pass/_repository/` and
  nowhere else. A caller passes records in and gets records back; do
  not write SQL, open a connection, or import `sqlite3` outside that
  package and `_database.py`.
- A database failure reaches a caller as one of the three exceptions
  above, chosen by what the caller can do: a database that cannot be
  opened is a `ConfigurationError`, a violated constraint or a write
  that matched no row is a `ValidationError`, and anything else is an
  `UpstreamError`.
- The schema version lives in the database's own `user_version`
  pragma, and `_database.py` carries an earlier database forward by
  running its `CREATE ... IF NOT EXISTS` statements. That handles an
  **additive** change only. A column whose type changed, one that was
  removed, or data that has to be rewritten needs a step in
  `MIGRATIONS` written for it; bumping `SCHEMA_VERSION` alone would
  record that the change happened without doing it. Every step of a
  version is asked whether it still has something to do **before any
  of them runs**, which is what lets a step that fills a column be
  gated on the column it fills. Do not rebuild a table to change it:
  `events` points at `revisions` with a cascade, so the copy, drop
  and rename that is the portable answer elsewhere would delete every
  event in the database.
- A SQLite connection belongs to the thread that opened it, so
  anything working on another thread is given a way to open one, not a
  connection to share. `JobRunner` opens one per job and closes it.
- A job that fails records the reason only when it came from one of
  the core's own exceptions, which are written for a person and
  already redacted. Anything else records a fixed sentence and the
  reason goes to the log, because what a job stores is read back over
  the API.
- A job left `queued` or `running` when the service stops is marked
  `interrupted` at startup, never resumed automatically. Resuming is a
  human action, because a send that resumed itself would write to a
  live volunteer system from state rebuilt after a crash. **A run
  names the one it was left with**, as `interruptedJobId` beside
  `activeJobId`: a human action is one somebody has to be able to
  ask for, and an interrupted job is *finished*, so it is never the
  active one and nothing else published it. Only the run's most
  recent job is reported, because a send a later one has since
  carried out is not something to go on offering to resume — so the
  newest job is read whatever state it is in and answered only when
  that state is `interrupted`.
- Times the repository layer records are ISO-8601 UTC, and window
  bounds are plain local dates. Convert for display; never use the
  host clock to decide a calendar day.
- Log a value by building the message first and passing the variable.
  A format string with arguments fails pylint, which is configured for
  `{}` style, and an f-string passed directly fails it as well.
- Every failure the service returns is a problem document
  (RFC 9457), assembled by `app/star_pass_api/_problems.py`. Do not
  return an error body from a route; raise, and let the handlers shape
  it.
- A response with a status of 500 or above never carries the reason.
  The reason is logged against the same `reference` the caller is
  given, because an internal failure can carry a credential, a
  volunteer's name, or an upstream body holding either. A 4xx does
  carry its reason: the caller is the one who can act on it.
- The window crosses the wire with an exclusive `end` and is *spoken
  about* by the last day it covers. **The answer carries both**: `end`
  is authoritative and stays unconverted everywhere it is stored, sent
  or compared, and `lastDay` beside it is the same window said the way
  a reader means it, worked out once in `star_pass_contract/_views`.
  Published rather than left to each client because every client that
  shows a window has to say it that way, and one subtraction per
  client is a client that can disagree with the server about which
  days a run covers. The **other** direction stays in
  `star_pass_cli/_render.py`: `after` takes the day `runs collect
  --last-day` was given and hands the contract the day after, because
  that is a request, and no request takes an inclusive day.
- Endpoints live under `/v1`. Changes within a version are additive;
  a breaking change is served at a new prefix alongside the old one.
  A route's own path is written **without** the prefix, because the
  routers are included under it; writing it twice produces a working
  service and a contract describing `/v1/v1/...`.
- An idempotency key names an **operation**, one of
  `IDEMPOTENT_OPERATIONS`, which is wider than `JOB_KINDS`: an edit, a
  seal and a revert are answered in the request that asked for them,
  so not every keyed write starts a job. What a key remembers is the
  request's own fingerprint, which is why a seal is fingerprinted by
  the operation — it carries nothing else — and a revert by the
  revision asked for. Where a write claims its key is part
  of the decision, not an implementation detail — the run is read
  before the key is claimed, the key claimed before the write, and the
  answer recorded after it. Reading the run last spends a reservation
  on a run that is not there and reports a foreign key violation as a
  malformed request. That sequence is written once, in
  `star_pass_contract._deciding.keyed_write`; a write supplies a
  `KeyedWrite` saying which operation it is and what carrying it out
  means, and each half supplies its own `WriteRefusals`.
- Field names are camelCase on the wire and snake_case in Python.
  Every published shape inherits from `ApiModel` in
  `star_pass_contract`, which does the translation once.
- A route decides what to read and what a failure looks like. What an
  answer *contains* is decided once, in `star_pass_contract._views`,
  because the command line client shows the same answers from the same
  database and two copies of that conversion would drift (D2).
- A run's window crosses the wire as a `start` and an **exclusive**
  `end`, the pair the repository stores, plus the zone they are read
  in. The server's zone is authoritative: a client displays those
  dates and never works a window out in the zone of whoever is looking
  at it (D16). It carries an inclusive `lastDay` as well, added when
  the web interface became a second client having to say it that way;
  a client displays that field and does not subtract a day of its
  own.
- **`GET /v1/config` publishes the categories each calendar offers**,
  because that is the list a `set_category` edit may name and no
  reading of a run produces it: a run holds the opportunities its own
  events reached, and the event that needs the chooser is the one that
  matched nothing. The fallback the data model falls back to is not
  among them — its need IDs are empty on purpose, so an event under it
  could not become a shift, and offering it would be offering a choice
  the write refuses. A category configured with no usable need ID is
  left out for the same reason. **Unassigned is not one of them** and
  must not become one: it is the absence of a category rather than a
  category, and it is reached by the `unassign` operation, which is
  refused for any row the collection did match (D29).
- The job event stream reads the job's status *before* its events.
  The other order loses an event written between the two reads: the
  events read would not hold it, and the status read after it would
  end the stream.
- The service never holds a connection across a request: a connection
  belongs to the thread that opened it, and a synchronous dependency
  and the endpoint using it can run on different threads. Pass the
  work to `_storage.read` instead, which opens, uses and closes one
  inside a single call.
- **How often something may be asked for is the service's to decide**,
  not the core's: `_limiting.py` holds the count, in memory, because
  what it protects is this process's own upstream requests and a count
  that survived a restart would describe requests nothing is making.
  The window slides rather than resetting, since a fixed one lets
  twice the allowance through across its edge, and a refused attempt
  is not counted — counting it turns a limit into a lockout. Local
  mode is not limited: that is the operator asking their own machine.
- **A write reaching the frontend has to prove it came from its own
  page**, and three things say so rather than one: the cookie is
  `SameSite=Strict`, the token derived from the session arrives in a
  header an off-site form cannot set, and `Origin`/`Sec-Fetch-Site`
  are checked. The origin check compares hosts and not whole origins,
  because TLS is terminated in front of the service (D6) and the
  scheme the browser used is not the scheme this process sees.
- **What makes that host comparison trustworthy is Caddy, not
  `FORWARDED_ALLOW_IPS`.** The two are easily confused. uvicorn's
  proxy-header handling reads `X-Forwarded-For` and
  `X-Forwarded-Proto` and rewrites the client address and the scheme;
  it never touches `Host`. `Host` is trustworthy because a Caddy site
  is matched by name, so a request naming any other one is answered
  with nothing rather than passed on. Scope the setting to the
  proxy's address anyway and never to `*` — it is what the first
  thing to read a client address will depend on.
- **The frontend forwards an allowlist of headers, never what
  arrived.** What the API receives is what the frontend decided to
  send plus the credential, so a page cannot choose what the API is
  asked with. `Idempotency-Key` is on the list because the contract
  requires it on the keyed writes.
- `app/star_pass_api/_security.py` is the only module that reads the
  API token or the `Authorization` header. A route declares the scopes
  it needs with `requires(...)` and receives a `Principal`; it never
  decides for itself whether a caller is allowed in. Keeping that in
  one place is what makes replacing the static token with an identity
  provider a change to that module rather than to every route.
- Compare a credential with `secrets.compare_digest`, never `==`: a
  comparison that stops at the first wrong character reports, in how
  long it took, how much of the value was right.
- 401 with a `WWW-Authenticate` challenge means the service cannot
  identify the caller. 403 without one means it can, and the request
  was outside their scopes.
- `docs/api/openapi.json` is generated, never edited. After changing a
  route, a model, a scope or the version, run
  `python scripts/generate_contract.py` and commit the result;
  `tests/test_api_spec.py` fails while it and the service disagree.
  A version bump changes this file, which is intended: the contract
  records which release it describes. The same command writes
  `app/star_pass_client/_operations.py`, which is generated from the
  contract: one command, because writing the contract without the
  client generated from it would leave a client describing the service
  as it used to be.
- An operation's identifier in the contract is the name of the
  function serving the route, not FastAPI's default built from the
  method and path. The generated client names its methods after it, so
  `get_run` reads as a method and `get_run_v1_runs__run_id__get` does
  not. Two routes may not share a function name; a test fails if they
  do.
- **Retention's axis is the question, not the clock.** A job log and a
  revision expire by age; an unmatched title expires when the data
  model matches it, because the count *is* its value. A single window
  over all three would delete the thing one of them measures. The
  service sweeps at startup and on a timer, the command line sweeps by
  hand, and no endpoint sweeps at all.
- Prefer failing loudly over dropping data. A row that cannot become a
  correct shift stops the run and is named, rather than being skipped:
  a missing shift is invisible, and the operator only discovers it when
  volunteers cannot sign up.
