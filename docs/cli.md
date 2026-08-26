# The command line

Every command word here selects something the API publishes, and each
works two ways: against the local database in the same process, or
against a running star-pass service. What is displayed is identical
either way, because both modes answer with the same document.

```bash
./app/__main__.py --help
```

Add `--api-url`, or set `STAR_PASS_API_URL`, to read a service instead
of the local database. That also needs `STAR_PASS_API_TOKEN`, and the
command says so rather than failing with a 401.

The Slack sign-up summary is the one thing selected by a flag rather
than a command word, and it has its own file:
[`slack-summary.md`](slack-summary.md).

## Collected runs

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

`runs show` gives one run, the events its current revision holds, the
Amplify opportunities they are created under, and every change made to
it. `runs uncollected` gives what the run's window held that did not
become one of its events, grouped by the reason for each. `runs
preview` gives what sending it would create, per opportunity, the
shifts Amplify already has, and every reason an event cannot be sent.

## Collecting a run

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

## Deleting a run

```bash
./app/__main__.py runs delete <run_id>
```

Asks first, restating the run and what it holds, and takes the run's
revisions, events, opportunities, `change_log` rows and jobs with it.
The titles its window did not match stay: what the shift data model is
missing outlives the run that found it.

**A run that has sent cannot be deleted** (D24). The record of what it
created is the only account of that anything here holds. A run
something is working on is refused too, with a different reason: that
one becomes deletable when the work finishes. The runs list draws its
delete control from the run's own answer, so a run that may not go is
offered nothing rather than offered something that fails.

## Sending a run

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

## Watching and resuming a job

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

## Reading the configuration

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

It also reports how long what a run leaves behind is kept, which is
where to look before wondering whether something has been removed.

Read only. Changing any of these means changing the environment and
restarting: no endpoint and no command writes a setting (D8), and the
same goes for credentials, which are rotated the same way and are
never displayed.

## Testing the Amplify credential

```bash
./app/__main__.py config credential
```

Sends one small read to Amplify and says whether it was accepted, with
the last four characters of the credential so two can be told apart.
The credential itself is never shown and nothing replaces it: rotation
is changing the secret and restarting (D8). A credential Amplify will
not take is an answer rather than a failure, so the command succeeds
and prints what it found.

The endpoint behind it is rate-limited per caller, because every call
spends a request on somebody else's service. Locally there is no
limit: that is the operator asking their own machine.

## Retention

Three windows, because the question "is this still worth keeping" has
three different answers (D12, D20). The driver throughout is the
volunteer names and schedules this data holds, not disk:

- A **job's event log** expires 90 days after the job finished. The job
  survives it, so a run's history still says a send happened without
  still saying who it was for.
- A run's **middle revisions** go once the run has gone untouched for
  90 days. The first revision and the current one are never removed:
  reverting to the first is a published operation, and the current one
  is what the run holds now.
- An **unmatched title** is forgotten as soon as the data model matches
  it, which is what recording one is for. Age is only a backstop, at a
  year, for a title nobody ever acted on. A title goes whole rather
  than sighting by sighting, because the count means the runs a title
  turned up in and a smaller count would read as a title that had
  stopped recurring.

**The record of what a send created is never removed.** Duplicate
safety reads it, so a window there would eventually have a run offering
to create shifts Amplify already holds.

The API service applies the policy once at startup and then daily. To
apply it to a local database by hand:

```bash
./app/__main__.py retention sweep
```

That covers the arrangement the service does not: a checkout and a
database file, where the windows would otherwise never be applied at
all. It takes no `--api-url`, because there is nothing remote to ask -
the contract publishes no deletion on purpose, since retention removes
what a run leaves behind and a caller does not.

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

A title that blocked a run is only visible while that run is. So the
titles worth an alias are kept in a log of their own, which belongs to
no run and outlives every one of them:

```bash
./app/__main__.py config unmatched
```

One line per title in a calendar, with how many sightings have been
recorded and when the most recent was, newest first. The count is what
tells the two cases apart: a title that turns up every month is a
category the model is missing, and one seen once is an event that
happened once. Read it before editing `models/shift_info.yml`.

Collections fill the log themselves, so nothing depends on anybody
remembering to record a title. A run counts once per title however
many events carry it and however often you collect its window again -
so fixing the model and recollecting does not read as the title coming
back.

The log is append-only: nothing updates an entry and nothing deletes
one, and it outlives the runs the titles were seen in.
