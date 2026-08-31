# Star Pass Repository

<!-- GitHub Actions status badges -->
[![Build](https://github.com/rcrderby/star-pass/actions/workflows/build.yml/badge.svg)](https://github.com/rcrderby/star-pass/actions/workflows/build.yml)
[![Super-Linter](https://github.com/rcrderby/star-pass/actions/workflows/lint-files.yml/badge.svg)](https://github.com/marketplace/actions/super-linter)
[![Static Code Analysis: bandit](https://github.com/rcrderby/star-pass/actions/workflows/static-code-analysis.yml/badge.svg)](https://github.com/rcrderby/star-pass/actions/workflows/static-code-analysis.yml)

<!-- Test tool badges -->
[![Linting: Super Linter](https://img.shields.io/badge/linting-Super_Linter-blue.svg)](https://github.com/super-linter/super-linter)
[![Static Code Analysis: bandit](https://img.shields.io/badge/security-bandit-blue.svg)](https://github.com/PyCQA/bandit)

## Overview

star-pass automates volunteer shift creation on the Galaxy Digital
Amplify platform. A window of a Google Calendar is collected into a
**run**; the run is reviewed row by row, previewed against what Amplify
already holds, and sent. A send writes one request per opportunity, skips
what Amplify already has, and can be resumed if it is interrupted.

Two pictures in [`docs/architecture.md`](docs/architecture.md) show what
a deployment is made of and what a run does across it. They are the
quickest way to see the shape of the thing before reading any of this.

## Capabilities

- **Collect** practices, scrimmages and games from Google Calendars into
  a run, matching each event title against a category in
  `models/shift_info.yml` to find the Amplify opportunities it serves.
- **Review** a run in a browser or from the command line: change an
  opportunity, move a shift's times, set how many volunteers are wanted,
  act on many rows at once, and undo any of it.
- **Revise** a run. Every edit is recorded, revisions can be saved, and a
  run can be reverted to any of them.
- **Preview** a send against live Amplify data, which is also the
  duplicate check: a shift Amplify already holds is not offered again.
- **Send** the run, creating the shifts. Sending is idempotent, asks
  before it acts, and an interrupted send resumes without duplicating
  anything.
- **Post a Slack sign-up summary** of live shift counts, on a schedule or
  by hand.

The interface has no login and the deployment publishes one port. That is
deliberate, and [`docs/design/decisions.md`](docs/design/decisions.md)
records why.

## Requirements

- Docker Desktop, or any Docker with Compose v2
- Git
- A Google Calendar API token and an Amplify API token

## Getting started

Three steps to a running deployment. No development container is needed:
this is the deployment, not the development environment.

### 1. Clone the repository and write `.env`

```bash
git clone https://github.com/rcrderby/star-pass.git
cd star-pass
python3 scripts/setup_env.py
```

The script writes `.env` from `.env.example`. It **generates** the two
values this deployment signs with, `STAR_PASS_API_TOKEN` and
`STAR_PASS_SESSION_SECRET` - the API authenticates the frontend with the
first, and the frontend signs your browser session with the second and
derives that session's CSRF token from it. **Both services refuse to
start without them**, which is a hard stop rather than a subtle failure.

It then asks for your `AMPLIFY_TOKEN` and your `GCAL_TOKEN`, without
echoing what you type and without printing either back.

It also asks for the two calendar IDs, `GCAL_EVENTS_CAL_ID` and
`GCAL_PRACTICES_CAL_ID`, and **does** echo those: a calendar
identifier is not a secret, and one typed blind is one nobody can
check. Neither has a default, and the API service names whichever is
missing and refuses to start. A default would be one organization's
calendars, so a deployment that left them unset would collect somebody
else's events without anything on any screen to say so.

Give the identifier as Google shows it under the calendar's settings,
with **no leading slash** - the address is built around it. A Google
Workspace resource calendar looks like
`example.com_2d3534@resource.calendar.google.com`.

**Six values in all**, and the API service checks for every one of
them at startup.

Every other setting has a working default; `.env.example` documents all
of them.

Run it again whenever a value is missing: it refuses to overwrite one
already set, and writes the file readable by you and your group.

The group matters: the API container bind-mounts `.env`, which keeps
the host file's mode, and the image runs as UID 1000. Where your
account is not the first on the machine, set `STAR_PASS_ENV_GID` to
the output of `id -g` so the container is in the group that can read
it. A file private to its owner alone cannot be read there, and making
it readable to everyone would give away the thing keeping it a file.

Copying `.env.example` by hand is not a substitute. Every credential
in it is commented out, so a copy starts the service with none and
stops it at the first one, which is the loud failure rather than the
plausible one.

`.env` holds live credentials and is git-ignored. Keep it out of any
directory that synchronises off the machine.

### 2. Build and start

```bash
docker compose build
docker compose up -d
```

One image, built once and run twice, as the API and as the frontend,
which is what stops the two drifting apart. Three containers start in
order, each waiting for the one below it to report healthy:

```bash
docker compose ps
```

### 3. Open it

Open **`https://localhost`**.

Your browser will warn about the certificate, which is expected out of
the box. [`docs/deployment.md`](docs/deployment.md) says why, what to do
about it, and how to serve a real name instead.

**On this host only, until you say otherwise.** Caddy publishes 80 and
443 on the loopback address, so nothing else on the network reaches
star-pass. To serve it to a tailnet, set `STAR_PASS_BIND_ADDRESS` to
that host's tailnet address and bring the stack back up:

```bash
docker compose up -d
```

The deployment is meant to run with no route out, and binding the
address is what enforces that rather than assuming it. `0.0.0.0`
publishes on every interface, which on a host with a public one means
the internet.

Then confirm the Amplify credential before doing anything else, from
**Settings** in the page or from the command line:

```bash
docker compose exec api python /app/__main__.py config credential
```

## Where to go next

| Document | What it covers |
| --- | --- |
| [`docs/cli.md`](docs/cli.md) | Every command line word: collecting, reviewing, previewing, sending, watching a job, retention, and the unmatched-title log |
| [`docs/slack-summary.md`](docs/slack-summary.md) | The Slack sign-up summary, its window, its wording, and running it from its own container |
| [`docs/deployment.md`](docs/deployment.md) | The two processes, the two networks, TLS, the addresses the page serves, and reading the API specification |
| [`docs/architecture.md`](docs/architecture.md) | The deployment and a run, drawn |
| [`docs/design/decisions.md`](docs/design/decisions.md) | Every design decision and its reasoning |

## Development

The repository carries a development container, which is the shortest
way to an environment with the tooling already in it: open the
repository in Visual Studio Code and reopen it in the container
(`.devcontainer/devcontainer.json`, built from `Dockerfile.dev`). It is
for working on the code, and is not how the application is deployed -
`docs/deployment.md` is that.

Without it:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements/requirements_dev.txt
```

Run the tests and the linters that continuous integration runs:

```bash
python -m pytest
python -m flake8 --config .github/linters/.flake8 app tests
python -m pylint --rcfile .github/linters/.python-lint app tests
python -m bandit -rc .bandit.yml app tests
```

Tests are hermetic: they make no network calls and require no `.env`
file. `tests/conftest.py` sets dummy credentials before the package is
imported.

Secrets live in `.env`, which is git-ignored and scanned by gitleaks in
continuous integration and by a pre-commit hook. Install the hook once
with:

```bash
pip install pre-commit && pre-commit install
```
