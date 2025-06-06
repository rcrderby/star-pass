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
3. Create a file named `.env` at the root directory with the following variables and their corresponding values:

    ```text
    AMPLIFY_TOKEN=abcdefg1234567890              ## Amplify API Token
    GCAL_TOKEN=abcdefg1234567890                 ## Google Calendar API Token
    GCAL_TIME_MIN = '2099-01-10T00:00:00-00:00'  ## "From" date for Google Calendar shift searches
    GCAL_TIME_MAX = '2099-01-30T00:00:00-00:00'  ## "To" date for Google Calendar shift searches
    ```

## Usage

1. Collect Google Calendar Shift data and save shift data in a formatted CSV file:

    ```bash
    # Get events from the "Practices" calendar
    ./app/__main__.py --mode=get_gcal_events gcal_name=practices

    # Get events from the "Events" calendar
    ./app/__main__.py --mode=get_gcal_events gcal_name=events
    ```

2. Create Amplify Shifts using formatted CSV file data:

    ```bash
    ./app/__main__.py --mode=create_create_amplify_shifts --input_file=gcal_shifts_2099-01-01T00_00_00_000000.csv check_mode=False
    ```
