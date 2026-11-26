# Command Line Interface

The command line interface (CLI) allows you to collect, read, and send
runs. You must use the web UI to edit a run, save or revert a revision, note an unmatched
title, and add an event to a run. To list
the commands:

```bash
./app/__main__.py --help
```

In a deployment, run the same commands in the `api` container:

```bash
docker compose exec api python /app/__main__.py --help
```

By default, each command reads the local database. To read a running
`star-pass` API service instead, add `--api-url` or set
`STAR_PASS_API_URL`, and set `STAR_PASS_API_TOKEN`. The output is the
same either way.

The Slack sign-up summary uses the `-s` flag, not a command. See
[`docs/slack-summary.md`](slack-summary.md).

## Reading Runs

These commands display runs and jobs:

```bash
./app/__main__.py runs list
./app/__main__.py runs show <run_id>
./app/__main__.py runs revisions <run_id>
./app/__main__.py runs uncollected <run_id>
./app/__main__.py runs preview <run_id>
./app/__main__.py jobs show <job_id>
```

| Command | Displays |
| --- | --- |
| `runs list` | All runs, newest to oldest |
| `runs show` | One run, its events, its Amplify opportunities, and its changes |
| `runs revisions` | A run's revisions, oldest to newest, and the number of changes in each revision |
| `runs uncollected` | Events in the run's date range that are not in the run, grouped by reason: outside the calendar search, excluded by title, all-day event, or untitled |
| `runs preview` | Shifts a send operation would create in Amplify for each opportunity, the shifts already in Amplify, and reasons any events may not be sent to Amplify |
| `jobs show` | A job's progress |

## Collecting a Run

To collect a calendar's events in a date range into a new run:

```bash
./app/__main__.py runs collect \
  --calendar events --start 2026-09-01 --last-day 2026-09-30
```

`--last-day` is the last day to include.

To replace a run's events with the current League Calendar events,
collect the run again:

```bash
./app/__main__.py runs recollect <run_id> --expected-changes 0
```

Collecting a run again discards any changes made to it since it was
collected. Set `--expected-changes` to the number of changes that
`runs revisions` reports for the current revision. If the number does
not match, the run is not collected again. Check `runs revisions` and
try again.

## Deleting a Run

To delete a run:

```bash
./app/__main__.py runs delete <run_id>
```

The command describes the run and asks you to confirm. Deleting a run
removes its revisions, events, opportunities, `change_log` rows, and
jobs. Any unmatched titles from the run remain in the unmatched title log.

You may not delete a run that:

- Is collecting events
- Is sending shifts to Amplify
- Already sent shifts to Amplify

## Sending a Run

To create a run's shifts in Amplify:

```bash
./app/__main__.py runs send <run_id>
```

Sending creates shifts in Amplify, and it may not be undone. The command
displays the number of shifts it will create, the date range, and the
opportunities. You must confirm the send by answering `y` or `yes` when prompted. Any
other answer, including an empty line, cancels the send.

The command only sends from an interactive terminal. It does not send
from a script, a scheduled job, or a pipe.

If there are changes to the run or Amplify shifts before you respond to the confirmation prompt, the send is refused.
Run `runs send` again to see the current number of shifts.

## Watching and Resuming a Job

Collecting events and sending shifts are jobs. To follow a job's progress, or to
resume an interrupted job:

```bash
./app/__main__.py jobs watch <job_id>
./app/__main__.py jobs resume <job_id>
```

`jobs watch` follows a job until it ends. It requires `--api-url`. In
local mode, a job ends before the command that started it returns.

`jobs resume` runs an interrupted job again. A job is interrupted when
the process running it stops before the job ends. You may only resume an interrupted job.

## Reading the Configuration

To display the current settings:

```bash
./app/__main__.py config show
```

```text
Timezone               America/Los_Angeles
Match threshold        80
Filtered event titles  canceled, cancelled, derby daze, summer camp

CALENDARS

CALENDAR   SEARCHED FOR
events     all events
practices  officials, scrimmage

RETENTION

Job logs          90 days after a job finishes
Revisions         90 days after a run is last changed
Unmatched titles  365 days after a title was last seen, or after the data model matches it
Sent shifts       retained to prevent duplicate shifts
```

An event whose title contains a filtered term is not collected. A
calendar with no search terms collects all events in the date range.
In a calendar with search terms, events that do not match a search term
are not collected. You may add them to a run in the web UI, from the
run's **Not Collected** tab.

To change a setting, edit values in your `.env` file and restart `star-pass`.

## Testing the Amplify Credential

To test `AMPLIFY_TOKEN`:

```bash
./app/__main__.py config credential
```

The command sends one read request to Amplify, and indicates whether or not
Amplify accepted the token. The token's last four characters are visible in the output. A refused token is a result, not an
application error.

The API rate limits this test; local mode does not.

## Testing the League Calendar Credential

To test `GCAL_TOKEN`:

```bash
./app/__main__.py config calendar-credential
```

The command reads one event from each configured calendar, and indicates
whether or not each read was successful. The key's last four characters are visible in the output.
Each calendar produces its own result because Google's API may successfully authenticate a key and determine the key is not authorized for a calendar. A refused key is a result, not an error.

The API rate limits this test; local mode does not.

To change a credential, edit its value in your `.env` file and restart `star-pass`.

## Retention Policy

`star-pass` removes old data on the following schedules:

| Data | Removed |
| --- | --- |
| A job's event log | 90 days after the job finishes. The job itself remains |
| A run's revisions | 90 days after the run was last changed. The first revision and the current revision remain |
| An unmatched title | After the data model matches it, or 365 days after it was last seen |
| Shifts sent to Amplify | Retained indefinitely to prevent duplicate shifts |

The API service applies this policy at startup, and daily while the service runs. To
apply the retention policy manually to the local database:

```bash
./app/__main__.py retention sweep
```

```text
No data was past its retention period.
```

`retention sweep` does not accept `--api-url`.

## Unmatched Event Titles

`star-pass` matches each event title to a category in
`models/shift_info.yml`. A title matches a category when it contains one
of the category's `aliases`. When a title contains aliases from more
than one category, the longest alias match wins. If a title contains no
alias, `star-pass` compares the words in the title with the words in
each alias, and gives each alias a similarity score from 0 to 100. The
alias with the highest score matches if its score is at least
`FUZZY_MATCH_THRESHOLD` (default 80).

If neither method finds a match, the event has no opportunity, and the
collection job logs a warning:

```text
No category matches "Jet City vs Cherry City" in the "events" calendar.
The event has no opportunity.
```

Unmatched events display in `runs preview`, and you must assign an opportunity to all unmatched events in the web UI to send the run to Amplify. To add a keyword to the match criteria:

1. Find the category the event belongs to in `models/shift_info.yml`.
2. Add a keyword for an event's title to that category's `aliases`.
3. Run `runs recollect` to collect the run again.

The new alias persists for future runs.

To display every title the data model has not matched:

```bash
./app/__main__.py config unmatched
```

The log has one line per title and calendar, newest to oldest, with the
number of runs the title appeared in and when it was last seen. A title
that appears routinely is likely a category missing from the data model. A
title seen once may be a one-time event. Check the log before
editing `models/shift_info.yml`.

Collecting a run adds its titles to the log. A run counts each title once, no matter how many events have the title or how many times the
run is re-collected.
