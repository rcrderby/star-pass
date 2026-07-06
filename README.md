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

2. Create Amplify Shifts using formatted CSV file data:

    ```bash
    # Dry run (default); add -C false to send live requests
    ./app/__main__.py -c \
        -i gcal_shifts_2099-01-01T00_00_00_000000.csv \
        -C false
    ```

3. Post a shift sign-up summary to Slack (live counts per shift):

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
