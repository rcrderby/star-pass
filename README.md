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
league's public Google Calendars.

The public calendars list practices, scrimmages, and games. Volunteers sign up for shifts to support events in the Amplify volunteer management platform.
`star-pass` gathers events from a date range in the League Calendar, identifies the volunteer shifts that each event needs,
and allows you to bulk-create shifts in Amplify.

## How It Works

### Volunteer Shift Management

`star-pass` uses a concept of **runs**, which contain events collected from the League Calendar within a date range.
A run attempts to match League Calendar events to Amplify volunteer shifts, allowing you to review and bulk-create shifts.
Each run goes through four steps:

1. **Collect.** Read the League Calendar events within the date range and match each title
   to an Amplify Shift category using a data model. The categories prepare Amplify
   opportunities, their shift times, and the number of volunteer slots.
2. **Review.** Check each event. Change the Amplify opportunities `star-pass` assigned, their start and end times,
   their number of volunteer slots, or remove them. Each change is logged, and you can revert to any saved revision. of your edits.
3. **Preview.** Compare the run with the shifts already in Amplify. `star-pass` compares a run's shifts with the volunteer shifts in Amplify to avoid creating duplicates.
4. **Send.** Create the shifts in Amplify. `star-pass` sends volunteer shifts to Amplify and displays the shifts it creates.

Each step is available in a web UI and at the CLI.

### Slack Summary Posts
`star-pass` posts summaries of volunteer sign-ups to Slack. It reads
volunteer shift data from Amplify and runs in scheduled GitHub Actions.

## Terms

| Term | Meaning |
| --- | --- |
| Event | An entry on the League Calendar |
| Category | A kind of event, such as an adult game, defined in a data model |
| Alias | A keyword that identifies a category in an event title |
| Opportunity | An Amplify listing volunteers sign up through, such as "Adult Games - NSOs". Amplify's API calls it a "need", and its ID a "need ID" |
| Shift | One volunteer shift within an opportunity, with a specific number of volunteer slots |
| Run | The events from one calendar and date range, converted to Amplify shifts |
| Revision | A saved version of a run |

## The Data Model

A data model for volunteer shifts determines the opportunity each event from the league calendar should match. The model is at `models/shift_info.yml`.

### Data Model Eample

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

An event with `axles` or `wheels` in its title is an "adult game" in Amplify. It
gets a volunteer shift in opportunity/need ID 879609 for 12 volunteers.  The shift starts 15
minutes before and ends 30 minutes after the League Calendar event times. It has a maximum length of 165 minutes, from its start time.

| Field | Meaning |
| --- | --- |
| `aliases` | Title keywords for each category. When a title contains aliases from more than one category, the longest alias match wins |
| `need_ids[].id` | The Amplify opportunity ID |
| `offset_start`, `offset_end` | Minutes added to the event's start and end times. A negative number moves the time earlier |
| `max_length` | The maximum length of a shift, in minutes |
| `slots` | How many volunteer slots for a shift needs |

## Requirements

- Docker with Compose v2
- Python 3, to run the setup script
- An Amplify API token
- A Google API key that can read the League Calendar, and the IDs of
  the `Events` and `Practices` calendars

## Setup

### 1. Write `.env`

```bash
git clone https://github.com/rcrderby/star-pass.git
cd star-pass
python3 scripts/setup_env.py
```

The script asks for an Amplify token, a Google API key for the League Calendar API, and
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

Open `https://localhost`. Your browser warns about the certificate.
the application signs it with its own certificate authority.
[`docs/deployment.md`](docs/deployment.md) explains how to trust the certificate, or
use a certificate from a public CA, or reach `star-pass` from another machine.

Before your first run, in the web UI, navigate to to **Settings** to test your
Amplify and Google API credentials.

## Command Line Interface

The command line interface allows you to perform the same actions available in the web UI:

```bash
docker compose exec api python /app/__main__.py --help
```

See [`docs/cli.md`](docs/cli.md).

## Documentation

| Document | Contents |
| --- | --- |
| [`docs/cli.md`](docs/cli.md) | Every command |
| [`docs/slack-summary.md`](docs/slack-summary.md) | The Slack sign-up summary |
| [`docs/deployment.md`](docs/deployment.md) | The containers and networks, TLS, the web page's addresses, and the API specification |
| [`docs/architecture.md`](docs/architecture.md) | Diagrams of the deployment and of a run |
| [`docs/api/openapi.json`](docs/api/openapi.json) | The API specification |

## Development

The repository includes a development container
(`.devcontainer/devcontainer.json`) for Visual Studio Code. If you prefer to your own development environment, install Python 3.14 or later and run these commands:

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

The tests make no network calls and need no `.env` file.

Two sets of files are generated. Regenerate them after a change, or the
tests fail:

| File | Command | Regenerate after changing |
| --- | --- | --- |
| `docs/api/openapi.json` | `python scripts/generate_contract.py` | An API route, model or version |
| `docs/architecture/*.svg` | `python scripts/generate_architecture.py` | `scripts/generate_architecture.py` |

### Code Layout

| Path | Contents |
| --- | --- |
| `app/__main__.py` | The command line entry point |
| `app/star_pass/` | The core: collecting, reviewing, previewing and sending runs, and the SQLite database |
| `app/star_pass_api/` | The API service (FastAPI) |
| `app/star_pass_bff/` | The frontend service. Serves the web page and forwards its requests to the API |
| `app/star_pass_cli/` | The command line commands |
| `app/star_pass_client/` | The API client the command line uses, generated from the application's specification |
| `app/star_pass_contract/` | The data shapes the API and the command line both return |
| `web/` | The web UI. |
| `models/` | The data model and Slack role labels |
| `deploy/caddy/` | The Caddy configuration |
| `scripts/` | Setup, code generation, and comment style check |
| `tests/` | Repo tests |

### Generated Files

The files listed in the table below are generated by the application and stored in the Git repo.
If you want to make changes to the contents of the generated files, do so by making changes to the "Generated From" files.
After making changes, run its corresponding command and commit the resulting changes to Git.
Tests will fail if a committed file does not match what its command generates.

| File | Contents | Generated From | Command |
| --- | --- | --- | --- |
| `docs/api/openapi.json` | The API specification | The API's routes, models, scopes and version | `python scripts/generate_contract.py` |
| `app/star_pass_client/_operations.py` | The command line's API client | `docs/api/openapi.json` | `python scripts/generate_contract.py` |
| `docs/architecture/*.svg` | The diagrams in `docs/architecture.md` | `scripts/generate_architecture.py` and `scripts/_drawing.py` | `python scripts/generate_architecture.py` |
