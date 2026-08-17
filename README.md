# Star Pass Repository

<!-- GitHub Actions status badges -->
[![Build](https://github.com/rcrderby/star-pass/actions/workflows/build.yml/badge.svg)](https://github.com/rcrderby/star-pass/actions/workflows/build.yml)
[![Super-Linter](https://github.com/rcrderby/star-pass/actions/workflows/lint-files.yml/badge.svg)](https://github.com/marketplace/actions/super-linter)
[![Static Code Analysis: bandit](https://github.com/rcrderby/star-pass/actions/workflows/static-code-analysis.yml/badge.svg)](https://github.com/rcrderby/star-pass/actions/workflows/static-code-analysis.yml)

<!-- Test tool badges -->
[![Linting: Super Linter](https://img.shields.io/badge/linting-Super_Linter-blue.svg)](https://github.com/super-linter/super-linter)
[![Static Code Analysis: bandit](https://img.shields.io/badge/security-bandit-blue.svg)](https://github.com/PyCQA/bandit)

## Overview

This tool automates bulk operations on the Galaxy Digital Amplify volunteer management platform.

## Capabilities

- Collect practice, scrimmage, and game activities from Google Calendars.
- Format activities for consumption by Amplify.
- Create volunteer shifts for activities.

## Requirements

1. Git SCM
2. Docker Desktop
3. Visual Studio Code

## Setup

1. Clone the GitHub repository.
2. Open the Development Container in Visual Studio Code.
3. Create a `.env` file at the root directory by copying the tracked template and filling in your values:

    ```bash
    cp .env.example .env
    ```

    Only `AMPLIFY_TOKEN` and `GCAL_TOKEN` are required. Deployment values such as the API URLs, HTTP timeout, and Google Calendar IDs and query strings are optional overrides; when unset, the defaults in `app/star_pass/_defaults.py` apply. Every supported variable is documented in `.env.example`.

## Usage

Two ways in. A **command word** -- `runs collect`, `runs send`, `jobs
watch` -- selects something the API publishes, and works against the
local database or a service (see [Collected runs](#collected-runs)
below). One **run mode flag**, `-s`/`--post-slack-summary`, selects the
Slack sign-up summary, which the API deliberately does not publish. Run
`./app/__main__.py --help` for the full list.

The two CSV run modes, `-g`/`--get-gcal-events` and
`-c`/`--create-amplify-shifts`, are retired. `runs collect` collects a
calendar window into a run, and `runs send` creates its shifts in
Amplify -- addressing a run by its identifier rather than a file, and
skipping a shift Amplify already has rather than trusting a count.

### Posting the Slack sign-up summary

Live counts per shift, for **today** by default:

```bash
# Dry run (default): build and print the Block Kit message, no send
./app/__main__.py -s -N 879610

# Several opportunities in one message; repeat -N or comma-separate
./app/__main__.py -s -N 879610,879611 -N 879612

# Cover today and tomorrow instead of just today
./app/__main__.py -s -N 879610 -d 2

# Posted on a Friday, covering Saturday and Sunday only
./app/__main__.py -s -N 879610 -D 1 -d 2

# Read the IDs from another command
printf '879610 879611' | ./app/__main__.py -s -N -

# Post live (needs SLACK_BOT_TOKEN); -k overrides the default
# channel (SLACK_CHANNEL_ID, else SLACK_DEV_CHANNEL_ID)
./app/__main__.py --post-slack-summary \
    --need-id 879610 \
    --slack-channel C0123ABC456 \
    --check-mode false
```

**Which opportunities.** `-N`/`--need-id` may be repeated,
comma-separated, or given as `-` to read IDs from stdin. With no `-N`
at all the IDs come from `SLACK_SUMMARY_NEED_IDS` in `.env`, so an
unattended run needs no arguments.

**How the message reads.** One row per event and time, with a line
per role beneath it:

```text
Juniors Scrimmages 6:00-7:00 p.m.
4 x NSOs
6 x SOs

Adult Scrimmages 7:00-8:00 p.m.
1 x NSO
4 x SOs
```

Role labels are shortened using `models/slack_role_labels.yml`, so
a summary reads `4 x NSOs` rather than
`4 x Non-Skating Officials`. Entries are keyed on the **role**, not
the opportunity, so a new opportunity using an existing role needs
no change there. A role with no entry keeps its full text. An
opportunity whose title has no role at all uses that file's
`default` label, so "Officials Practice" reads `1 x Official`.

Each opportunity gets a sign-up button at the end, filled rather
than outlined so it reads as a control on a phone, and ending in an
arrow because it opens the opportunity in a browser rather than
acting inside Slack. Set `SLACK_SIGN_UP_BUTTON_STYLE` to change the
style, or to empty for outlined buttons, and
`SLACK_SIGN_UP_BUTTON_SUFFIX` to change the arrow. Slack truncates
a button that outgrows its width, which is why the role is
shortened there too.

A count of exactly one reads as a singular label ("1 x NSO"). Rows appear in chronological order, and so do the
sign-up buttons at the end, so the message reads top to bottom as
the day happens. When two events run at the same time, they follow
the order their IDs were given in `-N` or `SLACK_SUMMARY_NEED_IDS`.

When the window covers more than one day, each day's rows sit under
a date heading. A single-day summary has none, because the title
already names the day.

Most of a run is spent waiting on Amplify, because the responses
endpoint has no server-side need or shift-date filter and the whole
domain's recent sign-ups have to be paged. A spinner reports
progress while that happens (`Reading recent sign-ups (page 4)`,
then `Reading opportunity 2 of 5`). It writes to stderr and only
when stderr is a terminal, so a scheduled run's log stays clean.

The event heading and the shortened role labels are derived from the
opportunity titles themselves, with no mapping file to maintain:
everything before `SLACK_TITLE_SEPARATOR` (a colon and a space by
default) becomes the
event, and what follows becomes the role label, so "Adult
Scrimmages: Skating Officials" contributes a "Skating Officials"
line to an "Adult Scrimmages" row. An opportunity whose title has no
separator keeps its full title as the row heading, and its lines
report a bare count.

Requires `SLACK_BOT_TOKEN` and a destination channel (`SLACK_CHANNEL_ID` or `SLACK_DEV_CHANNEL_ID`, or `-k`) in your `.env`; see `.env.example`.

Times, and the calendar day the window covers, are read in
`LOCAL_TIMEZONE` rather than from the host clock: a container or a
CI runner usually runs in UTC, where a Portland evening is already
the next day, which would summarize the wrong day.

**The day window.** `-d`/`--days` sets how many calendar days the
summary covers, counting today as day one: `1` (the default) is today
only, `2` adds tomorrow. Set `SLACK_SUMMARY_DAYS` in `.env` to change
the default. Shifts that already started never appear, so a summary
posted at noon lists only what is still to come that day.

`-D`/`--start-in-days` moves where the window begins: `0` (the
default) starts today, `1` starts tomorrow. This is what a notice
posted ahead of its shifts needs, so a Friday post covering the
weekend uses `-D 1 -d 2` and lists Saturday and Sunday without
Friday's own shifts. A window that starts on a later day carries
that day whole, from midnight. Set `SLACK_SUMMARY_START_IN_DAYS` in
`.env` to change the default.

When nothing falls inside the window, the run logs that and posts
nothing. A day with no shifts is routine, so an empty summary is not
an error and does not produce a message.

Counts come from the Amplify `/responses`
endpoint, which has no server-side filter for a need or for a shift's
date, so the run reads the domain's recent responses and filters them
to the need. `AMPLIFY_RESPONSES_SINCE_DAYS` (default 90) bounds how far
back that read goes: a sign-up cannot predate the shift it is for, so a
90-day window comfortably covers sign-ups for upcoming shifts. Each run
logs how much margin the window had, and warns when it gets thin.
Note this is unrelated to `-d`/`--days`: it bounds when a *sign-up*
was created, not when a *shift* starts, so narrowing the day window
does not shorten that read.


### Collected runs

The commands that work with collected runs. They are selected by a word
rather than by a mode flag:

```bash
./app/__main__.py runs list
./app/__main__.py runs show <run_id>
./app/__main__.py runs revisions <run_id>
./app/__main__.py runs uncollected <run_id>
./app/__main__.py runs preview <run_id>
./app/__main__.py jobs show <job_id>
```

Each reads the local database in the same process, so none of them
needs a service to be running. Add `--api-url`, or set
`STAR_PASS_API_URL`, to read a star-pass service instead; that also
needs `STAR_PASS_API_TOKEN`, and the command says so rather than
failing with a 401. What is displayed is identical either way, because
both modes answer with the same document.

`runs show` gives one run, the events its current revision holds, the
Amplify opportunities they are created under, and every change made to
it. `runs uncollected` gives what the run's window held that did not
become one of its events, grouped by the reason for each. `runs
preview` gives what sending it would create, per opportunity, the
shifts Amplify already has, and every reason an event cannot be sent.

### Reading the configuration

```bash
./app/__main__.py config show
```

The settings a collection is carried out under: the zone a window's
dates are read in, the score a fuzzy title match has to reach, the
terms a title is never collected under, and which calendars a
collection may name with the query strings each is searched for. A
calendar shown as searched for everything in the window is one
configured with an empty query string, so nothing in it can be left
out for want of a term.

Read only. Changing any of these means changing the environment and
restarting: no endpoint and no command writes a setting (D8), and the
same goes for credentials, which are rotated the same way and are
never displayed.

### Collecting a run

```bash
./app/__main__.py runs collect \
  --calendar events --start 2026-09-01 --last-day 2026-09-30
```

`--last-day` is the last day to cover, not the day after it. The
contract takes a window whose end is exclusive; the command line speaks
about the last day it covers, the same way it displays one.

Collecting again replaces what a run holds with what the calendar has
now, so any editing done since it was collected is left behind:

```bash
./app/__main__.py runs recollect <run_id> --expected-changes 0
```

`--expected-changes` is how many changes that would discard, which
`runs revisions` reports against the current revision. A number that no
longer matches is refused, which is what stops a run that has moved on
being replaced from a stale reading of it.

### Sending a run

```bash
./app/__main__.py runs send <run_id>
```

This is the one thing star-pass does that cannot be undone, so it asks
first (D11). It reads what a send would create, restates the count, the
window and the opportunities, and waits for a yes; anything else, an
empty line included, sends nothing. Where there is no terminal to
answer from -- a script, a scheduled job, a pipe -- it refuses, and no
flag turns that into a yes.

The count it confirms is the one it just read, and it is the one the
send is made with, so the service refuses if the run or Amplify moved
between the question and the answer.

### Watching and resuming a job

```bash
./app/__main__.py jobs watch <job_id>
./app/__main__.py jobs resume <job_id>
```

`jobs watch` holds a stream open and writes what the job reports as it
reports it, so it needs `--api-url`: nothing is serving in local mode,
where a job runs inside the command that asked for it and is over by
the time it answers.

`jobs resume` runs an interrupted job again. A job is left interrupted
when the process holding it stopped part way through, and resuming is a
deliberate act: nothing writes to Amplify without somebody asking.

## Unmatched event titles

`Helpers.search_shift_info` maps a Google Calendar event title to a
category in `models/shift_info.yml`. It first looks for a category whose
`aliases` all appear in the title (longest alias wins), then falls back
to a fuzzy match that must score at least `FUZZY_MATCH_THRESHOLD`
(default 80).

When neither matches, the title is not guessed at. The event is assigned
the calendar's `default` category, whose need IDs are deliberately
empty, and a warning names the title:

```text
No confident shift-info match for "Jet City vs Cherry City" in the
"events" calendar; assigning the review fallback
```

An empty need ID cannot become a shift. The event is still collected,
named as unmatched, so a reviewer sees everything the calendar held
rather than a run with holes in it -- and it stops the **send** instead,
which `runs preview` names with every reason. To resolve it:

1. Find the category the event belongs to in `models/shift_info.yml`.
2. Add a distinguishing keyword from the title to that category's
   `aliases` list.
3. Run `runs recollect` so the run picks up the corrected model.

Adding the alias is preferable to any one-off correction: it fixes
every future run as well.

## Development

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
