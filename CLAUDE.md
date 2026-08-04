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
- `app/star_pass/_defaults.py` — central configuration and constants.
- `app/star_pass/_logging.py` — package logger setup (`get_logger`);
  level via the `LOG_LEVEL` environment variable. Diagnostics and status
  flow through `logging`; report data still uses `Helpers.printer`.
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
- Prefer failing loudly over dropping data. A row that cannot become a
  correct shift stops the run and is named, rather than being skipped:
  a missing shift is invisible, and the operator only discovers it when
  volunteers cannot sign up.
