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
- `models/shift_info.yml` — keyword-to-need-ID data model.
- `app/schema/amplify.shifts.schema.json` — JSON Schema for shift
  payloads.
- `tests/` — pytest suite.

## Running the workflow

```bash
# 1. Collect Google Calendar events into a timestamped CSV.
./app/__main__.py --mode=get_gcal_events gcal_name=practices
./app/__main__.py --mode=get_gcal_events gcal_name=events

# 2. Create Amplify shifts from a CSV (check_mode=True is a dry run).
./app/__main__.py --mode=create_amplify_shifts \
  --input_file=gcal_shifts_<timestamp>.csv --check_mode=True
```

## Development

### Environment

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements/requirements_dev.txt
```

Secrets are read from a `.env` file at the repository root. Never commit
`.env`.

### Tests

```bash
python -m pytest
```

- Tests must be hermetic: no network calls and no real `.env`.
- `tests/conftest.py` sets dummy credentials before import.
- Construct `GCALData` / `CreateShifts` with `auto_prep_data=False`, and
  mock `Helpers.send_api_request`, to avoid live API calls.

### Linting

Continuous integration runs Super Linter (flake8, pylint, bandit,
jscpd, markdownlint, yamllint) and a separate bandit workflow. Run these
before pushing:

```bash
python -m flake8 --config .github/linters/.flake8 app tests
python -m pylint --rcfile .github/linters/.python-lint app tests
python -m bandit -rc .bandit.yml app tests
```

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
