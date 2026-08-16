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
- `app/__main__.py` — CLI entry point and run-mode dispatch.
- `app/star_pass/gcal_data.py` — collect and transform Google Calendar
  events (`GCALData`).
- `app/star_pass/amplify_shifts.py` — build and upload Amplify shifts
  (`CreateShifts`).
- `app/star_pass/_helpers.py` — shared helpers (`Helpers`), including
  `send_api_request`.
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
  `EventRole`, `LogEntry`).
- `app/star_pass/_repository/` — runs, their revisions, the events in
  each revision, the `change_log` of edits made to them, and the jobs
  that long operations are watched through. Every
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
- `app/star_pass/_validation.py` — shift input file checks, run before
  the transformation pipeline.
- `models/shift_info.yml` — shift data model: per calendar, `categories`
  (need IDs, slots, timing) each with an `aliases` list of title
  keywords. Add a team by adding its keyword to a category's `aliases`.
  `Helpers.search_shift_info` matches an event title to a category by the
  longest alias whose words all appear in the title, falling back to a
  fuzzy match (`FUZZY_MATCH_THRESHOLD`); an unmatched title logs a
  warning and uses the `default` category, whose need IDs are empty. An
  empty need ID cannot become a shift, so the `-c` run stops and names
  the affected rows rather than dropping them. See the "Unmatched event
  titles" section of `README.md` for the operator workflow.
- `app/star_pass_api/` — the remote surface over the core: the
  application factory (`create_app`), the service's own `_defaults.py`,
  `_problems.py`, `_schemas.py` (the shapes that cross the wire),
  `_storage.py` (how it reaches the database), and a module per group
  of endpoints. A separate
  package from `star_pass`, because the core knows nothing about HTTP
  and this package holds no domain logic. Run it with
  `uvicorn --factory star_pass_api:create_app`.
- `docs/api/openapi.json` — the generated OpenAPI 3.1 contract,
  written by `scripts/generate_openapi.py`.
- `app/schema/amplify.shifts.schema.json` — JSON Schema for shift
  payloads.
- `tests/` — pytest suite.

## Running the workflow

```bash
# The run mode is a flag: -g/--get-gcal-events,
# -c/--create-amplify-shifts, or -s/--post-slack-summary. Use --help
# for the full option list.

# 1. Collect Google Calendar events into a timestamped CSV.
./app/__main__.py -g -n practices
./app/__main__.py -g -n events

# 2. Create Amplify shifts from a CSV (-C true is a dry run).
./app/__main__.py -c -i gcal_shifts_<timestamp>.csv -C true

# 3. Post a Slack sign-up summary (-C true is a dry run).
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
- Construct `GCALData` / `CreateShifts` with `auto_prep_data=False`, and
  mock `Helpers.send_api_request`, to avoid live API calls.
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
- Endpoints live under `/v1`. Changes within a version are additive;
  a breaking change is served at a new prefix alongside the old one.
- Field names are camelCase on the wire and snake_case in Python.
  Every published shape inherits from `ApiModel` in `_schemas.py`,
  which does the translation once.
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
  `python scripts/generate_openapi.py` and commit the result;
  `tests/test_api_spec.py` fails while it and the service disagree.
  A version bump changes this file, which is intended: the contract
  records which release it describes.
- Prefer failing loudly over dropping data. A row that cannot become a
  correct shift stops the run and is named, rather than being skipped:
  a missing shift is invisible, and the operator only discovers it when
  volunteers cannot sign up.
