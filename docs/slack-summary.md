# Slack Sign-Up Summary

`star-pass` posts a summary of volunteer sign-ups to Slack, with a count
for each role in each shift. The summary only reads Amplify. It uses the
`-s`/`--post-slack-summary` flag, not a command. The other commands are
in [`docs/cli.md`](cli.md).

A GitHub Actions workflow, `.github/workflows/slack-summary.yml`, posts
the summary on Wednesdays and Fridays.

## Commands

By default, the summary covers today:

```bash
# Check mode (the default): build and print the message without posting it
./app/__main__.py -s -N 879610

# Several opportunities in one message: repeat -N or separate with commas
./app/__main__.py -s -N 879610,879611 -N 879612

# Today and tomorrow
./app/__main__.py -s -N 879610 -d 2

# Saturday and Sunday, posted on a Friday
./app/__main__.py -s -N 879610 -D 1 -d 2

# Read the need IDs from another command
printf '879610 879611' | ./app/__main__.py -s -N -

# Post to Slack
./app/__main__.py --post-slack-summary \
    --need-id 879610 \
    --slack-channel C0123ABC456 \
    --check-mode false
```

| Option | Sets | Default |
| --- | --- | --- |
| `-N`, `--need-id` | The need IDs to summarize. Repeat it, separate need IDs with commas, or pass `-` to read them from standard input | `SLACK_SUMMARY_NEED_IDS` |
| `-d`, `--days` | How many days to cover, counting the first day as one | `SLACK_SUMMARY_DAYS`, else 1 |
| `-D`, `--start-in-days` | How many days from today the summary starts. `0` is today, and `1` is tomorrow | `SLACK_SUMMARY_START_IN_DAYS`, else 0 |
| `-t`, `--slack-title` | The message title | The summary's dates |
| `-k`, `--slack-channel` | The Slack channel ID to post to | `SLACK_CHANNEL_ID`, else `SLACK_DEV_CHANNEL_ID` |
| `-C`, `--check-mode` | `true` builds the message without posting it. `false` posts it | `true` |

Posting to Slack requires `SLACK_BOT_TOKEN` and a channel ID in `.env`.
See `.env.example`.

## The Message

The message has one row per event and time, with a line for each role:

```text
Juniors Scrimmages 6:00-7:00 p.m.
4 x NSOs
6 x SOs

Adult Scrimmages 7:00-8:00 p.m.
1 x NSO
4 x SOs
```

The event name and the role come from the opportunity's title in
Amplify. The text before `SLACK_TITLE_SEPARATOR` (a colon and a space,
by default) is the event, and the text after it is the role. For
example, "Adult Scrimmages: Skating Officials" adds a "Skating
Officials" line to the "Adult Scrimmages" row. A title with no separator
is the row's heading by itself, and its line only shows a count.

`models/slack_role_labels.yml` shortens role names. For example,
"Non-Skating Officials" becomes "NSOs". The file's entries are keyed by
role, not by opportunity, and a new opportunity with an existing role
does not require a new entry. A role with no entry keeps its full name. A title
with no role uses the file's `default` label. For example, "Officials
Practice" reads `1 x Official`. A count of one uses the singular label.

Rows are in time order. Events at the same time follow the order of the
need IDs in `-N` or `SLACK_SUMMARY_NEED_IDS`. A summary of more
than one day has a date heading for each day. A one-day summary has no
date headings, and its title names the day.

Each opportunity has a sign-up button at the end of the message, in the
same order as the rows. The button opens the opportunity in a browser.
`SLACK_SIGN_UP_BUTTON_STYLE` sets the button's style. To display an
outlined button, set it to an empty value. `SLACK_SIGN_UP_BUTTON_SUFFIX`
sets the arrow at the end of the button's text.

## Dates and Times

Times and dates are in `LOCAL_TIMEZONE`, not the host's time zone.

The summary leaves out shifts that have already started. For example, a
summary posted at noon only lists the rest of the day's shifts. A
summary that starts on a later day covers that entire day.

If no shifts fall in the summary's dates, the summary is not posted,
and the log says so.

## Reading Amplify

Reading recent sign-ups from Amplify takes most of a summary's run
time. When standard error is a terminal, the summary displays its
progress there: `Reading recent sign-ups (page 4)`, then
`Reading opportunity 2 of 5`.

`AMPLIFY_RESPONSES_SINCE_DAYS` (default 90) sets how far back to read
sign-ups, and a sign-up made before then is not counted. This setting is
separate from `-d`. It limits when a sign-up was made, not when its
shift starts. The log reports how close the oldest counted sign-up is to
the limit, and displays a warning when it is close.

## Running the Summary from a Container

The summary has its own image, with only what the summary requires: no API
service, frontend, or database. The scheduled post runs on this image.
To build and run it:

```bash
docker build --target slack -t star-pass:slack .

docker run --rm \
  -e AMPLIFY_TOKEN -e SLACK_BOT_TOKEN -e SLACK_CHANNEL_ID \
  -e SLACK_SUMMARY_NEED_IDS \
  star-pass:slack
```

With no command, the image runs the summary in check mode, without
posting it. To choose the dates or to post, add the command:

```bash
docker run --rm \
  -e AMPLIFY_TOKEN -e SLACK_BOT_TOKEN -e SLACK_CHANNEL_ID \
  -e SLACK_SUMMARY_NEED_IDS \
  star-pass:slack \
  python /app/__main__.py -s -D 1 -d 2 -C false
```

The same Dockerfile builds both images. A build with no target builds
the full image the deployment runs.

The scheduled post pulls `ghcr.io/rcrderby/star-pass:slack`. The build
workflow publishes the image from `main`, with a second tag,
`slack-<commit>`, for the commit it was built from. The package is
private, and pulling it outside a workflow requires a GitHub login with
the `read:packages` scope. Building the image locally requires no login.
