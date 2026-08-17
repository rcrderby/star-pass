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
  `change_log` of edits made to them, the jobs
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
- `app/star_pass/_derived.py` — the four things the `Event` record
  deliberately leaves out, worked out from what it does hold: how long
  the shift is, whether an opportunity's maximum shortened it, whether
  another event in the revision would create the same shift, and
  whether the event blocks the run for want of a match. Pure functions
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
  stores them (`edit`). Operations apply in order, each seeing what
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
  category's offsets rather than storing a copy of it. A maximum does
  not pull a hand-set end time back in — a maximum shortens what the
  offsets produced, and a person setting a time has overridden that.
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
  `_storage.py` (how it reaches the database), and a module per group
  of endpoints. The shapes that cross the wire are not here: they are
  in `star_pass_contract`, because the command line client sends and
  receives the same ones. A separate
  package from `star_pass`, because the core knows nothing about HTTP
  and this package holds no domain logic. Run it with
  `uvicorn --factory star_pass_api:create_app`.
- `docs/api/openapi.json` — the generated OpenAPI 3.1 contract,
  written by `scripts/generate_contract.py`, which also writes the
  client generated from it.
- `app/star_pass_contract/` — the shapes the contract publishes
  (`_schemas.py`), how stored records become them (`_views.py`), what a
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
  recollect`, `jobs show`, `jobs watch`, `jobs resume` and `config
  show`), which work
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
  published by the API and declared unavailable in local mode. Editing
  a run's events is the first of those; do not add commands for it.
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

# 3. Post a Slack sign-up summary (-C true is a dry run). The one run
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
  removed, or data that has to be rewritten needs a migration step
  written for it; bumping `SCHEMA_VERSION` alone would record that the
  change happened without doing it.
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
  live volunteer system from state rebuilt after a crash.
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
  about* by the last day it covers — displayed as one by `last_day`,
  and taken as one by `runs collect --last-day`, which `after` turns
  back. Both conversions are in `star_pass_cli/_render.py` and nowhere
  else, so the authoritative value stays unconverted everywhere it is
  stored, sent or compared.
- Endpoints live under `/v1`. Changes within a version are additive;
  a breaking change is served at a new prefix alongside the old one.
  A route's own path is written **without** the prefix, because the
  routers are included under it; writing it twice produces a working
  service and a contract describing `/v1/v1/...`.
- An idempotency key names an **operation**, one of
  `IDEMPOTENT_OPERATIONS`, which is wider than `JOB_KINDS`: an edit is
  idempotent and answered in the request that asked for it, so not
  every keyed write starts a job. Where a write claims its key is part
  of the decision, not an implementation detail — the run is read
  before the key is claimed, the key claimed before the write, and the
  answer recorded after it. Reading the run last spends a reservation
  on a run that is not there and reports a foreign key violation as a
  malformed request.
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
  at it (D16). `openapi-v1-sketch.yaml` shows an inclusive `lastDay`
  instead; adding one is an additive change to make when a client
  needs it, not a reason to convert on the way out.
- The job event stream reads the job's status *before* its events.
  The other order loses an event written between the two reads: the
  events read would not hold it, and the status read after it would
  end the stream.
- The service never holds a connection across a request: a connection
  belongs to the thread that opened it, and a synchronous dependency
  and the endpoint using it can run on different threads. Pass the
  work to `_storage.read` instead, which opens, uses and closes one
  inside a single call.
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
- Prefer failing loudly over dropping data. A row that cannot become a
  correct shift stops the run and is named, rather than being skipped:
  a missing shift is invisible, and the operator only discovers it when
  volunteers cannot sign up.
