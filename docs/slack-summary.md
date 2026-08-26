# Posting the Slack sign-up summary

Live counts per shift, posted to Slack. This is the one thing star-pass
does that the API deliberately does not publish: it is selected by a run
mode flag, `-s`/`--post-slack-summary`, rather than by a command word.

The command line reference is in [`cli.md`](cli.md); this file covers
the summary alone.

## The commands

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

## Running the summary from a container

The summary has a container image of its own, carrying what the `-s`
path imports and nothing else: no API service, no frontend, no
database, and no page to serve. It is what the scheduled post runs
on, and it is the way to run a summary by hand without bringing a
deployment up.

```bash
docker build --target slack -t star-pass:slack .

docker run --rm \
  -e AMPLIFY_TOKEN -e SLACK_BOT_TOKEN -e SLACK_CHANNEL_ID \
  -e SLACK_SUMMARY_NEED_IDS \
  star-pass:slack
```

Given no command it builds the message and posts nothing, because
check mode is the default. Name a command to choose the window or to
post it for real:

```bash
docker run --rm \
  -e AMPLIFY_TOKEN -e SLACK_BOT_TOKEN -e SLACK_CHANNEL_ID \
  -e SLACK_SUMMARY_NEED_IDS \
  star-pass:slack \
  python /app/__main__.py -s -D 1 -d 2 -C false
```

One Dockerfile builds both images, so they cannot drift apart on the
base image or the Python version. A build naming no target gets the
full one, which is what the deployment runs.

The scheduled post does not build anything. It pulls
`ghcr.io/rcrderby/star-pass:slack`, which the build workflow publishes
from `main` alongside a second tag naming the commit it came from, so
a post can be traced to what produced it. The package is private, so
pulling it outside a workflow needs a login with `read:packages`;
building the target locally, as above, needs nothing.
