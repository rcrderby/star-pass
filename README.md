# Star Pass Repository

<!-- GitHub Actions status badges -->
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

    Set `GCAL_TIME_MIN` and `GCAL_TIME_MAX` in your `.env` to the date
    range you are collecting, in ISO 8601 format
    (`2099-01-01T00:00:00-00:00`). They are required, and deliberately
    have no defaults: the window moves with every run, so a default
    would go stale and silently collect zero events. The run stops with
    an error if either is missing, malformed, or does not move forward
    in time. Only this run mode reads them.

2. Create Amplify Shifts using formatted CSV file data:

    ```bash
    # Dry run (default); add -C false to send live requests
    ./app/__main__.py -c \
        -i gcal_shifts_2099-01-01T00_00_00_000000.csv \
        -C false
    ```

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
