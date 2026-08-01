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

Select the run mode with a flag: `-g`/`--get-gcal-events`, `-c`/`--create-amplify-shifts`, or `-s`/`--post-slack-summary`. Every input has a short and long form. Run `./app/__main__.py --help` for the full list.

1. Collect Google Calendar Shift data and save shift data in a formatted CSV file:

    ```bash
    # Get events from the "Practices" calendar
    ./app/__main__.py -g -n practices

    # Get events from the "Events" calendar
    ./app/__main__.py --get-gcal-events --gcal-name events
    ```

    Set `GCAL_WINDOW_START` and `GCAL_WINDOW_END` in your `.env` to the date
    range you are collecting, as plain local dates (`2099-01-01`). They
    are required, and deliberately have no defaults: the window moves
    with every run, so a default would go stale and silently collect
    zero events. The run stops with an error if either is missing,
    malformed, or does not move forward in time. Only this run mode
    reads them.

    Each date means midnight local time, and the UTC offset in effect
    on that date is applied automatically, so Daylight Saving needs no
    attention. Use the first day of the next month to collect a whole
    month:

    ```bash
    GCAL_WINDOW_START=2099-01-01
    GCAL_WINDOW_END=2099-02-01
    ```

    Local time means `GCAL_TIMEZONE`, which defaults to
    `America/Los_Angeles`; set it to any IANA time zone name. A value
    that carries its own UTC offset
    (`2099-01-01T00:00:00-08:00`) is honored as written. Prefer plain
    dates: writing the window in UTC shifts it eight hours earlier
    during Pacific Standard Time, which silently drops evening events
    on its final day. The resolved window is logged at the start of
    each run.

    Events are filtered before shifts are built. An event is skipped,
    with a logged reason, when its title contains a term in
    `GCAL_PREFIX_FILTERS` (cancelled events, derby daze, summer camp),
    when it is an all-day event, or when it has no title. Review the
    generated CSV file before step 2.

2. Create Amplify Shifts using formatted CSV file data:

    ```bash
    # Dry run (default); add -C false to send live requests
    ./app/__main__.py -c \
        -i gcal_shifts_2099-01-01T00_00_00_000000.csv \
        -C false
    ```

    A dry run (`-C true`, the default) does not create anything, but it
    is **not** entirely request-free: it reads each opportunity title
    from Amplify with a `GET /needs/{id}` so the preview can name the
    opportunity. `AMPLIFY_TOKEN` is therefore required in both modes.

    The run stops before sending anything if any row has no need ID.
    That happens when an event title matched no category in the shift
    data model, so the review fallback assigned an empty ID. See
    [Unmatched event titles](#unmatched-event-titles) below.

3. Post a shift sign-up summary to Slack (live counts per **upcoming** shift):

    ```bash
    # Dry run (default): build and print the Block Kit message, no send
    ./app/__main__.py -s -N 879610

    # Post live (needs SLACK_BOT_TOKEN); -k overrides the default
    # channel (SLACK_CHANNEL, else SLACK_DEV_CHANNEL)
    ./app/__main__.py --post-slack-summary \
        --need-id 879610 \
        --slack-channel C0123ABC456 \
        --check-mode false
    ```

    Requires `SLACK_BOT_TOKEN` and a destination channel (`SLACK_CHANNEL` or `SLACK_DEV_CHANNEL`, or `-k`) in your `.env`; see `.env.example`.

    The summary lists only shifts that start in the future, with a live
    sign-up count for each. Counts come from the Amplify `/responses`
    endpoint, which has no server-side filter for a need or for a shift's
    date, so the run reads the domain's recent responses and filters them
    to the need. `AMPLIFY_RESPONSES_SINCE_DAYS` (default 90) bounds how far
    back that read goes: a sign-up cannot predate the shift it is for, so a
    90-day window comfortably covers sign-ups for upcoming shifts. Each run
    logs how much margin the window had, and warns when it gets thin.

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

An empty need ID cannot become a shift, so the `-c` run refuses to send
anything and names every affected row and its line in the CSV file. To
resolve it:

1. Find the category the event belongs to in `models/shift_info.yml`.
2. Add a distinguishing keyword from the title to that category's
   `aliases` list.
3. Re-run the `-g` collection so the CSV file is regenerated, or edit
   the `need_id` column in the existing file by hand.

Alternatively, delete the row from the CSV file if the event should not
produce shifts at all. Adding the alias is preferable: it fixes every
future run as well.

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
