# star-pass

<!-- GitHub Actions status badges -->
[![Build](https://github.com/rcrderby/star-pass/actions/workflows/build.yml/badge.svg)](https://github.com/rcrderby/star-pass/actions/workflows/build.yml)
[![Super-Linter](https://github.com/rcrderby/star-pass/actions/workflows/lint-files.yml/badge.svg)](https://github.com/marketplace/actions/super-linter)
[![Static Code Analysis: bandit](https://github.com/rcrderby/star-pass/actions/workflows/static-code-analysis.yml/badge.svg)](https://github.com/rcrderby/star-pass/actions/workflows/static-code-analysis.yml)

<!-- Test tool badges -->
[![Linting: Super Linter](https://img.shields.io/badge/linting-Super_Linter-blue.svg)](https://github.com/super-linter/super-linter)
[![Static Code Analysis: bandit](https://img.shields.io/badge/security-bandit-blue.svg)](https://github.com/PyCQA/bandit)

## Overview

`star-pass` automates Amplify volunteer shift management using events in the
League Calendar, a set of public Google Calendars.

The public calendars list practices, scrimmages, and games. Volunteers sign up for shifts to support events in the Amplify volunteer management platform.
`star-pass` gathers events from a date range in the League Calendar, identifies the volunteer shifts that each event requires,
and allows you to bulk-create shifts in Amplify.

## How It Works

### Volunteer Shift Management

`star-pass` uses a concept of **runs**. A run contains events collected from the League Calendar within a date range.
A run attempts to match League Calendar events to Amplify volunteer shifts, allowing you to review and bulk-create shifts.
Each run goes through four steps:

1. **Collect.** Read the League Calendar events within the date range and match each title
   to a category in the data model. The categories prepare Amplify
   opportunities, their shift times, and the volunteer count.
2. **Review.** Check each event. Change the Amplify opportunities `star-pass` assigned, their start and end times,
   their volunteer count, or remove them. Each change is tracked, and you may revert to any saved revision.
3. **Preview.** Compare the run's shifts with the volunteer shifts already in Amplify, to avoid creating duplicates.
4. **Send.** Create the shifts in Amplify. `star-pass` sends volunteer shifts to Amplify and displays the shifts it creates.

Each function is available in the web UI. Collecting, previewing, and sending are also available from the CLI.

### Slack Summary Posts

`star-pass` posts summaries of volunteer sign-ups to Slack. It reads
volunteer shift data from Amplify and runs in scheduled GitHub Actions.

## Terms

| Term | Meaning |
| --- | --- |
| Event | An entry on the League Calendar |
| Category | A type of event, such as an adult game, defined in a data model |
| Alias | A keyword that identifies a category in an event title |
| Opportunity | An Amplify listing volunteers sign up through, such as "Adult Games - NSOs". Amplify's API calls it a "need", and its ID a "need ID" |
| Shift | One date and time in an opportunity, with a specific volunteer count |
| Run | The events from one calendar and date range, converted to Amplify shifts |
| Revision | A saved version of a run |

## The Data Model

A data model for volunteer shifts determines the opportunity or opportunities each event from the League Calendar should match, plus certain details that apply to those shifts. The data model is at `models/shift_info.yml`.

### Data Model Example

```yaml
adult_game:
  description: Adult Games
  aliases:
    - axles
    - wheels
  need_ids:
    - description: NSOs
      id: 879609
      offset_start: -15
      offset_end: 30
      max_length: 165
      slots: 12
```

An event with `axles` or `wheels` in its title is in the `adult_game` category. It
gets a volunteer shift in opportunity 879609 with a volunteer count of 12. The shift starts 15
minutes before and ends 30 minutes after the League Calendar event times. It has a maximum length of 165 minutes, from its start time.

| Field | Meaning |
| --- | --- |
| `aliases` | Title keywords for each category. When a title contains aliases from more than one category, the longest alias match wins |
| `need_ids[].id` | The Amplify need ID |
| `offset_start`, `offset_end` | Minutes added to the event's start and end times. A negative number moves the time earlier |
| `max_length` | The maximum length of a shift, in minutes |
| `slots` | A shift's volunteer count |

## Requirements

- Docker with Compose v2
- Python 3, to run the setup script
- An Amplify API token
- A Google API key that can read the League Calendar, and the IDs of
  the `events` and `practices` calendars

## Setup

### 1. Write `.env`

```bash
git clone https://github.com/rcrderby/star-pass.git
cd star-pass
python3 scripts/setup_env.py
```

The script asks for an Amplify token, a Google API key for the League Calendar, and
the applicable calendar IDs. It also generates two secrets the application services use to
authenticate each other. You may run the script again to fill in a missing value. It
does not overwrite existing values.

If `id -g` does not print `1000`, add `STAR_PASS_ENV_GID=` followed by
what it prints to `.env`.

Every other setting has a default, listed in `.env.example`.

### 2. Start `star-pass`

```bash
docker compose build
docker compose up -d
docker compose ps
```

`star-pass` is ready when the `api` and `frontend` containers show
`healthy`.

### 3. Open It

Open `https://localhost`. Your browser displays a warning about the certificate because `star-pass` signs it with its own certificate authority.
[`docs/deployment.md`](docs/deployment.md) explains how to:

- Trust the certificate
- Use a certificate from a public certificate authority
- Connect to `star-pass` from another device

Before your first run, in the web UI, navigate to **Settings** to test the
Amplify and League Calendar credentials.

## Command Line Interface

The command line interface allows you to collect, read, and send runs:

```bash
docker compose exec api python /app/__main__.py --help
```

See [`docs/cli.md`](docs/cli.md).

## Documentation

| Document | Contents |
| --- | --- |
| [`docs/cli.md`](docs/cli.md) | Every command |
| [`docs/slack-summary.md`](docs/slack-summary.md) | The Slack sign-up summary |
| [`docs/deployment.md`](docs/deployment.md) | The application containers and networks, TLS configuration, the web UI addresses, and the API specification |
| [`docs/architecture.md`](docs/architecture.md) | Diagrams of the deployment and of a run |
| [`docs/api/openapi.json`](docs/api/openapi.json) | The API specification |

## Development

The repository includes a development container
(`.devcontainer/devcontainer.json`) for Visual Studio Code. If you prefer to use your own development environment, install Python 3.14 or later and run these commands:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements/requirements_dev.txt
pre-commit install
```

To locally run the tests and the checks that GitHub Actions performs:

```bash
python -m pytest
python -m flake8 --config .github/linters/.flake8 app tests
python -m pylint --rcfile .github/linters/.python-lint app tests
python -m bandit -rc .bandit.yml app tests
python scripts/check_prose.py --changed origin/main
```

The tests make no network calls and do not require a `.env` file.

### Code Layout

| Path | Contents |
| --- | --- |
| `app/__main__.py` | The command line entry point |
| `app/star_pass/` | The core: collecting, reviewing, previewing, and sending runs, and the SQLite database |
| `app/star_pass_api/` | The API service (FastAPI) |
| `app/star_pass_bff/` | The frontend service. Serves the web UI and forwards its requests to the API |
| `app/star_pass_cli/` | The command line commands |
| `app/star_pass_client/` | The API client the CLI uses. Its operations are generated from the API specification |
| `app/star_pass_contract/` | The data shapes the API and the command line both return |
| `web/` | The web UI |
| `models/` | The data model and Slack role labels |
| `deploy/caddy/` | The Caddy configuration |
| `scripts/` | Setup, code generation, and comment style check |
| `tests/` | Repository tests |

### Generated Files

The files listed in the table below are generated by the scripts in `scripts/` and stored in the Git repository.
If you want to make changes to the contents of the generated files, do so by making changes to the "Generated From" files.
After making changes, run each file's corresponding command and commit the resulting changes to Git.
Automated tests will fail if a committed file does not match what its command generates.

| File | Contents | Generated From | Command |
| --- | --- | --- | --- |
| `docs/api/openapi.json` | The API specification | Routes, models, scopes, and version in the API | `python scripts/generate_contract.py` |
| `app/star_pass_client/_operations.py` | The command line's API client | `docs/api/openapi.json` | `python scripts/generate_contract.py` |
| `docs/architecture/*.svg` | The diagrams in `docs/architecture.md` | `scripts/generate_architecture.py` and `scripts/_drawing.py` | `python scripts/generate_architecture.py` |
