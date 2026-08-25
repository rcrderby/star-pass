# Star Pass — decision record

One entry per decision, with why, what was rejected, and **what would make us
revisit it**. Append new entries; don't rewrite old ones — supersede them.

Companion to `api-and-security-plan.md` (the plan these decisions produced).
Last updated: 2026-08-24.

---

## D1 — The API is the contract, not the CLI

**Decided:** A `star_pass` core Python package holds all domain logic. A FastAPI
service is the only *remote* surface over it. The CLI and the web BFF are both
clients containing no domain logic.

**Supersedes:** the earlier "the CLI is the API; the web UI shells out to it."

**Why:** Guarantees anything the web UI can do, the CLI can do. Removes shell-out
from the web path entirely, which deletes argv injection as a surface.

**Rejected:** web UI shelling out to the CLI (injection surface, no remote story);
duplicating logic in a web backend (drift).

**Revisit if:** the core package starts growing HTTP or presentation concerns, or
a client needs something the API can't express.

---

## D2 — The CLI keeps working with no server running

**Decided:** CLI calls the core in-process by default; `--api-url` /
`STAR_PASS_API_URL` switches it to the generated remote client.

**Why:** The CLI must not acquire a server as a hard dependency. Two modes over
one core is cheaper than a mandatory service.

**Rejected:** HTTP-only CLI (server becomes required); CLI booting an ephemeral
local server (worst of both).

**Scope (2026-08-17):** this decision is about *availability*, not coverage.
The command line exists for what the web interface cannot do — the Slack
summary the API deliberately does not publish, troubleshooting (`jobs
show`/`watch`/`resume`, `runs revisions`, `runs preview`), and the monthly
workflow, which has to work with no server running. **Parity with the web
interface is not a goal.** An operation whose natural home is the review
screen may be published by the API and declared unavailable in local mode,
with its reason, in `star_pass_client/_local.UNAVAILABLE`; the test binding
that list to the contract is what keeps the gap deliberate rather than
forgotten. Editing a run's events is the first such operation.

**Revisit if:** local mode and remote mode start answering the *same* operation
differently — that would mean the core boundary has leaked, and HTTP-only
becomes the honest fix. An operation only one mode offers is not that.

---

## D3 — Static bearer token now, OIDC later

**Decided:** Token from the environment, `compare_digest`, verified in exactly
one FastAPI dependency returning `Principal(id, scopes)`. Scopes declared on
every route from day one.

**Why:** Single user with controlled tokens. The migration cost to OIDC is low
*because* of the single dependency and the scope declarations; doing OIDC now
would require a device-authorization flow for the CLI.

**Rejected:** OIDC now (device flow is real work for one user); API keys in
SQLite (moving parts, no benefit at one user); mTLS as primary auth (awkward from
a laptop).

**Revisit if:** a second person needs access, the tool leaves your control, or
you want revocation without a restart. Migration = swap token comparison for JWT
validation against a discovery document; routes unchanged.

---

## D4 — Browser reaches the API only through a same-origin BFF

**Decided:** httpOnly, Secure, SameSite=Strict session cookie between browser and
front-end; the front-end holds the API token server-side.

**Why:** No API credential in JavaScript, so XSS can't exfiltrate one. No CORS
config at all. The BFF is also where OIDC lands later.

**Rejected:** browser holding the API token (exfiltratable); no browser auth at
all (nothing to migrate from).

**Revisit if:** never, realistically — but if a native or third-party client
appears, it authenticates to the API directly rather than through the BFF.

---

## D5 — No Kubernetes; Docker Compose on one host behind Caddy

**Decided:** Two containers, Compose, single host.

**Why:** Kubernetes is justified by multi-node availability, autoscaling, or team
deploys. None apply to a single-user tool doing one operation at a time.

**Rejected:** Kubernetes (operational surface for two containers).

**Revisit if:** multi-node availability is needed. Note the real coupling: SQLite
is single-writer and fights k8s (one replica, RWO volume, no rolling deploys), so
"move to k8s" means "move to Postgres" — see D7.

---

## D6 — No application-level TLS between BFF and API

**Decided:** Services speak plain HTTP on a private Docker network. TLS is
terminated at Caddy at the edge only. The API's URL is a config value so
encryption is always a deployment change, never a code change.

**Why:** On one host that traffic never touches a wire; reading it requires host
root. The real risk on a shared network is another container bypassing the BFF,
which is answered by network segmentation plus the bearer token.

**Rejected:** mTLS between services now (certificate lifecycle for internal
services = the debt, without a matching threat today).

**Revisit if:** the services land on different hosts. Then get it from the
platform — WireGuard/Tailscale overlay, or mTLS at a proxy — and prefer mTLS
specifically, since it also authenticates the BFF to the API.

---

## D7 — Repository layer in the core, SQLite behind it

**Decided:** State access goes through a thin repository layer; SQLite on a
mounted volume is the implementation.

**Why:** The only item on the list where the cheap option has a clearly
identifiable future cost. Keeps SQL out of API handlers, makes the core testable
without a database, and keeps Postgres a contained change.

**Rejected:** direct SQL in handlers (the debt we're explicitly avoiding);
Postgres from the start (a database server, backups and pooling for a few rows a
week).

**Revisit if:** concurrent writers, multiple replicas, or k8s (D5). The change
should touch only the repository implementations.

---

## D8 — Credential replacement is out of the API

**Decided:** No endpoint can overwrite the service's Amplify credential.
Rotation is a platform operation: change the secret, restart. The API keeps
`POST /credentials/test`, returning ok + last-four, rate-limited.

**Why:** An endpoint that can rewrite the service's own production credential is
the highest-value target in the system for the least benefit.

**Rejected:** a `PUT /credentials` the UI drives (the original design).

**Design consequence:** Settings loses the replace flow and keeps test +
last-four, plus a line saying rotation happens in the environment.

**Revisit if:** rotation becomes frequent enough to be painful — and then prefer
a secret manager (D9) over an API that writes secrets.

---

## D9 — Credentials arrive as a read-only mounted secret file

**Decided:** A read-only file, path supplied by an environment variable, owned by
the service user at 0400. Read once at startup, fail fast if missing or malformed.

**Why:** Keeps the secret out of process metadata — `docker inspect`,
`/proc/<pid>/environ`, crash dumps, child process environments — which is the one
concrete advantage over pure env vars. Same shape as Docker and k8s secrets.

**Rejected:** env var only (defensible second choice; twelve-factor's own answer,
but the value is visible in process metadata); secret manager now (a dependency
and a chicken-and-egg auth problem for one credential); a "seam for later"
(abstraction for a hypothetical).

**Revisit if:** more than one or two secrets accumulate, rotation gets frequent,
or access auditing is needed → move to a secret manager, keeping the same
`get_credential()` call site.

---

## D10 — Interrupted jobs are marked interrupted, with one-click resume

**Decided:** On boot, any job left running is marked interrupted. The UI offers a
resume, which reuses the retry-only-what-failed path. Nothing writes to Amplify
without a human action.

**Why:** Less new code than it sounds — it's the retry path pointed at a
different trigger. Automatic resume would mean unattended irreversible writes
based on state reconstructed after a crash.

**Rejected:** mark failed and re-run (safe and cheap, but a large partial send
gives the user no help finding its place); automatic resume (most dangerous code
in the system); refuse to start until acknowledged (a 2am crash means downtime
until you log in).

**Revisit if:** resumes become routine and the extra click is friction, or if
per-shift idempotency proves reliable enough that automatic resume is provably
safe.

**Found in the interface (2026-08-19):** three things, none of which change
the decision.

- **Nothing published the identifier.** `POST /jobs/{id}/resume` takes one,
  and `activeJobId` is derived from the two statuses a job is *in hand* under
  — an interrupted job is finished, so a run said nothing about it, and there
  is no listing of jobs. The command line worked because a person pastes an
  identifier out of the service log; a screen had nowhere to get one, and the
  browser cannot remember it, because the case this decision exists for is a
  job interrupted by a restart the browser may never have witnessed. Runs now
  publish `interruptedJobId` beside `activeJobId`.
- **It is a banner, not a screen the run opens on.** A job still running
  finishes and stops being the run's, so opening on it is safe. An interrupted
  one stays interrupted until somebody acts, so a run that opened on it was a
  run whose "Back to the run" came straight back — found by pressing it. The
  review screen carries the banner and the banner opens the job.
- **The resume request carries no `expectedShiftCount`.** The confirmation in
  front of it (D11) therefore buys attention rather than a staleness check: a
  run edited in another tab between the preview and the click would create
  rows nobody previewed. Not duplicates — the live read per opportunity
  prevents those whatever happens. Worth a field on the request if it ever
  matters.

The mechanism this decision chose survives; its stated *reason* has been
overtaken. "A large partial send gives the user no help finding its place" is
no longer why: a resumed send reads every opportunity immediately before
writing to it, so where the interrupted attempt got to is answered by Amplify
rather than by the job. What resuming buys now is that the run's history shows
one send that was interrupted and then finished, rather than two sends.

---

## D11 — Send is gated by a two-step confirmation

**Decided:** A confirm dialog restating the shift count, the date window and the
opportunities, on a different surface from the button.

**Why:** The confirmation's job is to make you read the summary. A typed number
tests typing, not attention, and gets habituated.

**Rejected:** typed confirmation (habituation, friction on a routine monthly
task); hold-to-send (reads as a gimmick; poor keyboard and motor accessibility);
no gate (one click writes irreversibly to a live volunteer system).

**Revisit if:** a mis-send happens anyway — then escalate to typed confirmation.

---

## D12 — Retention: sent record forever, job logs 90 days

**Decided:** The sent record is never purged. Job logs expire after 90 days.
Superseded revisions are deleted immediately. Both windows are config values.

**Why:** Duplicate safety depends on the sent record, so it can't expire. The
driver for expiring the rest is PII, not disk — a job log holds volunteer
names and schedules.

**Rejected:** keep everything (unbounded PII at rest with no expiry); 30-day logs
(shorter than the monthly feedback loop — a problem found at next collection
would have no evidence left).

**Narrowed (2026-08-17):** this decision named CSVs as the first thing to
expire, because a run's product was a file on disk. Nothing writes a CSV any
more — the CSV run modes were retired and what only they reached was deleted —
so the CSV half of this decision describes a file the tool no longer produces.
The PII rationale is unchanged and now applies to the job logs alone. Work-order
step 9 was amended to match.

**Revisit if:** an investigation needs evidence older than 90 days, or PII policy
tightens.

---

## D13 — Writes record principal id, timestamp and idempotency key

**Decided:** Every write carries those three fields, even while the principal is
always the static token.

**Why:** One column now, free later. The sent record is already an audit trail
with a missing column; adding it later means backfilling nulls on exactly the
rows that matter.

**Rejected:** timestamp and action only (honest today, incomplete tomorrow); full
request audit log with inputs (duplicates CSVs and revisions, another PII store);
skip until multi-user.

**Revisit if:** OIDC lands (D3) — the field starts carrying real subjects with no
schema change, which is the point.

---

## D14 — Access via Tailscale (or equivalent); internal CA while building

**Decided:** No public exposure. Caddy's internal CA for local development;
Tailscale-style device-level access for real use.

**Why:** Authentication as a boundary is deliberately deferred, so network-level
access control is doing that job. This is the option where deferring auth stays a
reasonable decision rather than becoming the vulnerability.

**Rejected:** public DNS with 80/443 open and HTTP-01 (simplest certs, but puts
an unauthenticated-by-design system on the internet); DNS-01 with a provider
token (real certs, nothing exposed — but a new credential that can prove domain
ownership); localhost only (not a deployment).

**Revisit if:** someone needs access from a device that can't join the tailnet,
or a real auth boundary lands — then public + DNS-01 becomes reasonable.

---

## D15 — Generated API docs, committed spec, generated CLI client

**Decided:** OpenAPI 3.1 generated by FastAPI; nothing hand-written. Swagger UI
at `/docs` for try-it, Scalar or Redoc for reference. Docs UI open, all endpoints
authenticated. Spec committed; CI fails on drift; the CLI's remote client is
generated from it. Path-versioned `/v1`.

**Why:** Makes "the CLI can do anything the web UI can" structural rather than a
discipline.

**Rejected:** hand-written docs; live spec only, uncommitted (no drift check).

**Revisit if:** a breaking change is needed → `/v2` alongside `/v1`.

---

## D16 — Server owns identity, time and idempotency

**Decided:** Run ids are server-minted. Sends require an `Idempotency-Key`, keyed
per `(run_id, need_id, start, end)`. Duplicate detection uses row identity from
Amplify, not a count. The window is parsed in `LOCAL_TIMEZONE`; the browser sends
dates and never computes presets in its own zone.

**Why:** All four were client-side in the design and all four were wrong: browser
`Date.now()` ids, a count-based duplicate check that can skip the wrong shifts,
and presets computed in the visitor's timezone.

**Corrected (2026-08-17):** this decision named `LOCAL_TIMEZONE`, and the code
reads `GCAL_TIMEZONE` — the zone a calendar bound without a UTC offset is read
in, which `.env.example` documents setting when the calendar keeps a different
clock from the league. `GCAL_TIMEZONE` defaults to `LOCAL_TIMEZONE`, so the two
agreed until a deployment separated them, and a run then reported a zone its
own dates had not been read in. The window is parsed in **`GCAL_TIMEZONE`**,
that is what a run and `GET /v1/config` both publish, and the server's zone
being the authoritative one is unchanged.

**Extended (2026-08-18):** the window now crosses the wire as `start`,
the exclusive `end` **and** an inclusive `lastDay`. The exclusive end is
still the authoritative value and is what is stored, sent and compared;
`lastDay` is the same window said the way a reader means it, worked out
once on the server. `CLAUDE.md` had named a client needing one as the
trigger, and the web interface is that client — every client that shows
a window has to say it that inclusive way, and a subtraction written
once per client is a client that can disagree with the server about
which days a run covers. The direction that has no published field is
the request one: `runs collect --last-day` still converts locally,
because no request takes an inclusive day.

**Revisit if:** never — these are correctness, not preference.

---

## D17 — Front-end and API are separate containers

**Decided:** Two services under Compose on one host: the API service and the web
BFF, on an internal network, with Caddy in front. The credential mount (D9) is
attached to the **API service only**. The CLI ships in the API image.

**Why:** Blast radius, not scaling. The internet-facing process never has the
Amplify secret on its filesystem — in a single container that separation is a
code convention rather than a boundary. It also lets the BFF be restarted for
session or OIDC changes without interrupting a running send, and shipping the CLI
in the API image means the core and the API can never drift out of step.

**Rejected:** one container running both (simpler local dev, but the secret is
reachable from the web process and a BFF restart takes the API with it).

**Cost:** one more Compose service and one internal network — roughly fifteen
lines. `docker compose up` keeps local development a single command.

**Revisit if:** the two services need to share in-process state, which would
itself be a sign the BFF has acquired domain logic it should not have.

---

## D18 — The browser's session is an opaque id with a derived token

**Decided:** The front end mints a random opaque session id in an httpOnly,
Secure, SameSite=Strict cookie, and puts an HMAC of it in a second, readable
cookie. A write must send that token back in a custom header. No session
library, no server-side store, nothing signed into the cookie but the id.

**Why:** A session carries *nothing* today. There is no login — a single person
reaches this over a network that controls access (D14), and an authentication
boundary in front of the whole system is deferred on purpose. A session library
serialises a dictionary we have no contents for, so it would be a dependency
holding an empty dict. Deriving the CSRF token instead of storing it means the
front end can be restarted, or eventually run twice, without logging anybody
out.

Three things make a write safe rather than one, because any single one can be
argued around: `SameSite=Strict` (a browser sends the cookie on nothing an
off-site page initiated), the token in a **header** (which an off-site form
cannot set), and a check on `Origin`/`Sec-Fetch-Site`.

**Rejected:** Starlette's `SessionMiddleware` with `itsdangerous` (a dependency
for an empty session; and at OIDC time a server-side store may be the better
answer anyway, which would make adopting it now waste rather than saving);
double-submit with no derivation (needs a store, or trusts a cookie the page set
itself).

**Revisit if:** OIDC lands (D3) and the session starts carrying an identity.
Then it holds a subject, an expiry and possibly tokens, and the choice is a
signed payload or a server-side store — the second being likely, because
revocation and keeping tokens out of the browser are the reasons to have one.
The migration is contained because everything asks `_sessions.py` two questions
and nothing else knows what a session is, which is the same arrangement that
makes D3 cheap.

---

## D19 — The page is served by the front-end container, at its root

**Decided:** The web interface is served at `/` by the front-end service, from
`web/` in this repository. The prototype in `docs/design` stays where it is and
is not ported.

**Why:** It is the only origin the page can work from, and that follows from
decisions already made rather than from taste. The CSRF token is a cookie the
page has to *read* (D18); the session cookie is `SameSite=Strict`, so a browser
sends it on nothing another site initiated (D4); and a write whose `Origin` host
is not this host is refused. A page on a second origin fails all three, and the
only way to make it work would be CORS on the boundary — which the plan names as
the signal that the boundary has leaked rather than moved (section 2).

So the repository stops being purely a back end. That cost was already paid when
`star_pass_bff` landed in it; what changes is that the page ships with the
service that holds its session, which is also what makes a session usable without
a round trip to fetch a token first.

**Rejected:** serving the page from the design project or any second origin (no
write could succeed without CORS); serving it from Caddy as static files beside
the proxy (same origin, so it would work, but the page and the session would then
be configured in two places and a deployment could update one without the other);
porting the prototype (its own README says it is a reference with mock data and
must not be ported).

**Consequence:** `web/` currently holds a placeholder that checks those three
things from a browser and says the interface is not built. Building the screens
is its own work, against `docs/api/openapi.json` and the design handoff.

**Revisit if:** the interface acquires a build step whose output belongs
somewhere else — the service reads `STAR_PASS_WEB_ROOT`, so that is a mount
rather than a code change — or a native or third-party client appears, which
authenticates to the API directly rather than through this service (D4).

---

## D20 — Retention is applied on three different axes, not one window

**Decided:** Three rules, because "is this still worth keeping" has three
different answers:

- A **job's event log** expires 90 days after the job finished. The job row
  survives it.
- A run's **middle revisions** are removed once the run has gone untouched for
  90 days. Revision 1 and the current revision are never removed.
- An **unmatched title** is forgotten as soon as the data model matches it, and
  otherwise 365 days after its most recent sighting.

The sent record is never purged, unchanged from D12. Every window is a config
value, and `GET /v1/config` publishes all three.

**Supersedes:** D12's "superseded revisions are deleted immediately", which does
not survive contact with the code. That line was written before a revision could
be reverted to. Every revision is reachable now — a caller can list them and go
back to any — so there is no moment at which one becomes superseded, and
deleting immediately would break the operation that makes them worth having. The
PII rationale is unchanged; only the trigger is.

**Why the unmatched titles are not on a window at all.** Their value *is* their
age: the count means the runs a title turned up in, so a title that turns up
every month is a category the model is missing and one that turned up once is an
event that happened once. Any expiry short enough to protect a person's name
would destroy the thing being measured. That is a sign the axis is wrong rather
than a trade-off to split down the middle: a sighting exists to prompt an edit to
`shift_info.yml`, so what should remove it is that edit happening. The check is
the same one that decided to record it, so nothing new has to be agreed on — a
title the model matches produces no fresh sighting either. The 365 days is only a
backstop for the title nobody ever acted on, and it is a year because the
calendar repeats annually.

A title is forgotten **whole**, never sighting by sighting. Removing some rows
would leave the same title reporting a smaller count, and a smaller count reads
as a title that has stopped recurring — the opposite of true.

**Where it runs:** the API service, at startup and then daily, and the command
line by hand (`retention sweep`). Both, because the service covers a deployment
and does not cover the arrangement this tool started as — a person with a
checkout and a database file — where the windows would otherwise never be
applied at all. A policy nothing applies has been written down rather than
adopted. The command names no contract operation and takes no `--api-url`,
because the contract publishes no deletion on purpose (plan section 5): retention
removes what a run leaves behind, a caller does not.

**Rejected:** one window for everything (does what the unmatched-title count
exists to prevent); resolution with no backstop (a title nobody ever fixes is
kept forever, which is the unbounded-PII case D12 rejected); exempting unmatched
titles entirely (records the tension as accepted rather than resolved); deleting
whole job rows rather than their logs (that a send ran on a date and how it ended
is not what the window is protecting, and a run's history would lose it); an
endpoint to trigger a sweep (a caller that can delete a run's leavings is the
thing plan section 5 rules out).

**Revisit if:** an investigation needs evidence older than 90 days, PII policy
tightens, or somebody wants to revert to a revision older than the window — the
last of which would mean the middle revisions are worth more than this assumes.

---

## D21 — No 2.x release until the web interface can be tested end to end

**Decided:** `__version__` is 2.0.0 and the contract records it, but no tag and
no GitHub release until there is a working web interface to exercise the whole
system through. The newest release stays v1.16.4 in the meantime.

**Why:** 2.0.0 is the release that inverts the architecture — the API became the
contract, state moved into SQLite, the CSV run modes went. Every part of it has
tests and the deployment now runs, but nothing has yet used it the way a person
will: collect a window, review it on a screen, preview, send. A version number is
a claim about what somebody can rely on, and making that claim before anybody has
run the thing end to end would put the claim ahead of the evidence.

**Consequence:** work-order step 9 is the last back-end step, so what stands
between here and the release is the interface itself (D19) rather than anything
in this document.

**Rejected:** tagging now and fixing forward in 2.0.1 (the point of waiting is
to find what only end-to-end use finds, and a release nobody has used is exactly
where that goes unnoticed); waiting for a *complete* interface (the review screen
and a send are enough to exercise the system; the rest can ship in 2.1).

**Revisit if:** the interface slips far enough that something else needs the tag
— a deployment that has to pin a version, for instance.

---


## D22 — The job stream publishes data, and a collection is five steps

**Decided:** Nothing the core reports carries rendered English. A step
crosses the wire as an identifier from `STEPS` plus, where a step works on
one thing, what it is working on; each client words it. `sending_started`
carries how many opportunities the send will work through, and one
`opportunity_sent` is reported per opportunity whether or not it needed
anything. The collecting screen shows **five** steps, not four.

**Supersedes:** the design handoff's screen 5, which names four steps
(read, filter, match, write).

**Why:** Three things about the sending screen, found by reading the
stream against what screen 6 draws. It shows "N of M opportunities" and M
was nowhere in the stream, so a browser reattaching after a reload had no
total — and the only other source is the preview, which would mean a live
Amplify read while the send is writing. Which opportunity a step was about
existed only inside an interpolated sentence, so a row could be addressed
only by parsing English. And an opportunity Amplify already held every
shift for was reported not at all, so its row could never leave "sending"
and the count of what is done would stop short of the total.

The step identifiers follow from the rule the rest of the contract already
keeps: values cross the wire and each client words them, which is what
stops a screen quietly inventing a category. A job's event log is read
back over the API by the same clients.

Five steps rather than four because the design's four do not survive
contact with the code twice over: the Amplify read has no home among them,
and their fourth is "Writing the CSV", which describes an artefact the
tool stopped producing when the CSV run modes were retired (D12,
narrowed). Reading the calendar and reading the Amplify opportunities are
separate upstream services and either can fail on its own, so which of
them stopped a collection is exactly what the screen exists to say.

**Rejected:** the opportunity count on `JobView` (a stored column null for
every collect job, filled by the endpoint from its own preview rather than
by the send, and stale after a resume — D10 re-reads Amplify and may touch
a different set); re-reading the preview mid-send (a live read of a run
being written to); folding the Amplify read into the design's "write"
step (hides the failure the step exists to show); leaving `step_started`
carrying a label (the one place the contract published rendered text, and
the send needs the need ID as a value regardless).

**Not changed:** a send still stops at the first opportunity Amplify
refuses, rather than carrying on. The design's "Retry the N that failed"
reads as though several rows can fail; in practice one does and the rest
stay waiting, and a retry resends the run, which per-shift identity makes
safe. Amplify refusing one opportunity is rarely a fact about that
opportunity, and continuing would write irreversibly after an unknown
outcome.

**Revisit if:** a step needs to carry more than one value, which would
mean the subject should be a mapping rather than a string.

---


## D23 — A revision is named by an identifier, not a stored sentence

**Decided:** A revision publishes `kind` — one of `collected`,
`recollected`, `continued`, `reverted` — and `sourceRevision`, the revision
it was made from. Each client words it: `_render.REVISION_PHRASES` and
`web/phrases.json`, both bound to the core's tuple by a test. Which kind a
revision is is worked out by the repository from what it already knows, not
passed in by a caller.

**Supersedes:** `RevisionView.label`, which carried sentences the core
wrote — "Continued from revision 1", "Reverted to revision 2", "As
collected", "As recollected".

**Why:** D22 named this rule for the job stream and the plan states it for
the contract, but a label survived both, and it was the worse case of the
two. It was not merely *returned* as English, it was **stored** as English:
changing the wording would have left every revision already recorded saying
the old thing beside a new one saying the new, in the same list, with no
way to reconcile them short of rewriting rows. A sentence returned by a
service is a wording mistake; a sentence written into a row is a wording
mistake with a migration attached.

Deriving the kind rather than accepting it removes a whole class of
disagreement: a caller that named the kind could name one that did not
match what actually happened. Whether a revision replaces what was there
and whether the run held anything are both known where the row is written,
and they decide three of the four kinds between them. The fourth, a revert,
is the one that also records a number, because which revision a run went
back to is not derivable from anything else — which is exactly why it is
the field worth publishing.

**Consequence:** schema version 7, and the first migration in this
repository that rewrites data rather than adding a column. It adds the two
columns, reads the four sentences back into what they were saying, and
drops the sentence — which it must, since an insert now names `kind` and
`source` and a `NOT NULL` column left behind would refuse every revision
written afterwards. **A column and not the table:** `events` references
`revisions` with `ON DELETE CASCADE` and `foreign_keys` is on, so the
copy-drop-rename that is the portable way to change a SQLite table would
delete every event in the database.

**Rejected:** keeping the sentence and publishing the identifier beside it
(two ways to say one thing, and the stored copy stays wrong); deriving the
kind at read time by parsing the stored English (a migration that runs
forever instead of once); leaving it alone as too small to be worth a
schema version (it is the wording that is small — the stored copy is not).

**Revisit if:** never for the direction, but a kind that needs to carry
more than one number would mean `sourceRevision` should be a mapping, which
is the same trigger D22 records.

---


## D24 - A run that never sent may be deleted

**Decided:** `DELETE /v1/runs/{id}` removes a run and everything that hangs
off it. It is refused when `runs.sent_at` is set, and refused separately,
with its own reason, when the run has a job in hand. `runs delete` joins the
command line beside it, because housekeeping has to work with no server
running (D2).

**Supersedes:** plan section 5's "Run/revision deletion - retention policy
does this, not a caller." Revision deletion stays where it was: a superseded
revision is swept by retention (D20) and no caller names one.

**Why:** What section 5 was protecting is the evidence that shifts reached
Amplify. A run that never sent has no such evidence to destroy. What it does
have is the ability to become permanent litter - a failed collection leaves
a run behind, retention sweeps by age rather than by state, and nothing
else can remove one. The runs list becomes the page's home in the same
release, which puts that litter on the first screen there is.

One condition covers both statuses that mean shifts were written, because
`mark_sent` (`_repository/_runs.py:432`) sets `sent_at` for `sent` and for
`partly_sent` alike. Reading the timestamp rather than the status is also
what keeps the refusal correct for a status this list has not thought of.

A job in hand is refused separately because it is a different answer to the
caller: a running send or collection finishes, and the run can be deleted
afterwards. A run that has sent never becomes deletable.

**Consequence:** deleting a run does not delete its unmatched-title
sightings. `unmatched_titles.run_id` names the run that saw a title and
declares no foreign key (`_database.py:295`), so no cascade reaches it. That
is deliberate and stays: what the data model is missing outlives the window
that revealed it.

**Rejected:** leaving every run to retention (a run created today survives
the retention window, so a failed collection sits on the home screen for
months); a soft delete or an archive flag (a second state for every list to
filter, carried for a run that holds nothing worth keeping).

**Revisit if:** a run that never sent acquires something worth keeping after
it is gone, or an authentication boundary makes "who deleted this" a
question the change log has to answer.

---


## D25 - Shift timing belongs to the event's role, not to the run's opportunity

**Decided:** `offset_start`, `offset_end`, `max_length` and `default_slots`
move from `opportunities` to `event_roles`, which is already keyed
`(run_id, revision, event_id, need_id)` (`_database.py:145`). What remains
on `opportunities` is what Amplify says about the listing: `need_id`,
`title`, `url`. Both conflict checks go - `_collect._require_one_timing`
(`_collect.py:391`) and `_adding._agrees` (`_adding.py:188`).

**Supersedes:** the assumption behind `opportunities`' key, `(run_id,
need_id)` (`_database.py:109`): that one Amplify listing implies one set of
offsets per run.

**Why:** The Rose City Rollers data model does not work that way. Need
905196 ("Junior Games - NSOs") is named by two categories on the `events`
calendar, with two different timings (`models/shift_info.yml:63-122`); need
905197 ("Junior Games - SOs") is named by the same two, the same way.

| Category | Offsets | Maximum |
| --- | --- | --- |
| `junior_game_petals` | -15 / +30 | 135 |
| `junior_game_buds` | 0 / +75 | 165 |

Each names its home teams as well as its group, so the aliases are the
category's to list and are not repeated here.

Any window holding two of them is refused whole by `_require_one_timing`,
which is why the `events` calendar has never been collected successfully.
The refusal is correct given the schema; the schema is what is wrong.

A role is where the timing was decided in the first place: `role_timings`
reads it off the category the event matched (`_event_edits.py:271`), and
`event_roles` is the row that already knows which event and which need it
belongs to. Moving the columns there records what the collection worked out
instead of averaging it into a per-run claim that cannot be true.

`default_slots` goes with the offsets rather than staying behind, because it
is read off the category the same way. The two categories agree about slot
counts today, so leaving it would work until the first pair that does not,
and then produce this same bug with a second migration attached.

**Rejected:** making the timings agree in `shift_info.yml` (they are
genuinely different, so this would create shifts at the wrong times); a
separate Amplify listing per category (volunteers would see two listings
where they see one).

**Consequence:** schema version 8, and the review table's offset notes,
`_derived.maximum` (`_derived.py:208`), `_building`, `_event_edits` and
`_repository/_runs` all read the timing from the role. The contract is
regenerated.

**Revisit if:** two events of the same category in one window need different
timings, which would mean the timing belongs to neither the listing nor the
category but to the event alone.

---


## D26 - The event remembers what collection matched it to

**Decided:** `events` gains a column holding the category the collection
matched. `_undo` restores it and `was_edited` compares against it.
`_set_category` computes the new category's times directly rather than by
calling `as_collected`.

Where the collection matched nothing the column is empty, and an undo puts
the row back to unassigned - which D29 makes a state a person can see and
choose. Undo therefore means "back to collection" on every row, with none
it means something else on.

**Why:** A category change is, by construction, invisible to both.
`_editing._set_category` (`_editing.py:212`) builds its result by calling
`as_collected` on the event it has just changed, so the result is a fixed
point of `as_collected`. `was_edited` (`_event_edits.py:546`) asks whether
`as_collected(event) != event`, so for a category change it is
**necessarily** false - not sometimes, always - and the row is offered no
undo. And `_undo` (`_editing.py:363`) is `as_collected(event)` as well,
reading the event's *current* category through `timings_for`
(`_event_edits.py:268`), so even if the control were offered it could not
restore the collected category.

Changing an opportunity is the most common edit on the review screen, and it
is the one edit that can be neither seen nor taken back.

Storing what the collection matched makes undo mean "back to collection"
uniformly, for every operation. That is also what makes a bulk undo honest:
a control that puts a selection back as collected has to do that for every
row in the selection, including the rows whose opportunity was changed.

**Rejected:** re-matching the title through the data model inside
`as_collected`. No schema change, but it answers with the model as it is
**now** rather than with what the run did, so a model corrected between
the day a run was collected and the day it is reviewed would have undo
move rows to categories the collection never chose, and would report rows
nobody has touched as edited. A run stores the match it actually made for
exactly this reason already: `match_shift_info` records the kind and the
keyword, not just the answer.

**Consequence:** schema version 9.

**Revisit if:** an operation appears that a person should not be able to
undo, which would make "back to collection" the wrong thing for undo to
mean.

---


## D27 - The change log publishes data, not sentences

**Decided:** A change-log entry stores the operation it recorded and the
values that operation carried. Each client words it, beside
`_render.REVISION_PHRASES` and `web/phrases.json`, bound to the core's tuple
by a test the way the others are.

**Supersedes:** `change_log.entry` (`_database.py:180`), the full English
sentence `_editing.py` writes into a column.

**Why:** D22 established this rule for the job stream and D23 for revisions.
The change log survived both, and it is D23's case again rather than D22's:
the English is not merely returned, it is **stored**. Changing the wording
would leave every entry already recorded saying the old thing beside a new
one saying the new, in the same list, with no way to reconcile them short of
rewriting rows. A sentence returned by a service is a wording mistake; a
sentence written into a row is a wording mistake with a migration attached.

The sentence is also already wrong in the one place a stored sentence cannot
be corrected: it carries a raw internal key. `Set the category of "X" to
"junior_scrimmage"` (`_editing.py:234`), where the screen everywhere else
calls that category "Junior Scrimmages".

**Consequence:** schema version 10, and no migration that reads the stored
sentences back. D23's could, because four fixed sentences map onto four
kinds; these are interpolated with event names, times and categories, and
recovering the fields would be a migration written against English. The
change lands against an empty database instead.

**Rejected:** keeping the sentence and publishing the values beside it (two
ways to say one thing, and the stored copy stays wrong); parsing the stored
sentences into fields (a migration that runs against prose, for data that is
being discarded anyway).

**Revisit if:** an operation needs to record something that is not one of
its own values - which would mean the entry carries context, not just what
was asked for.

---


## D28 - The page has addressable URLs

**Decided:** The page routes with the History API, over `/`, `/runs`,
`/runs/{id}`, `/runs/{id}/uncollected`, `/runs/{id}/preview` and
`/settings`. The BFF answers those paths, and only those, with `index.html`;
anything else that is not a real file still 404s. A test binds the page's
route table to the BFF's fallback list, the way `tests/test_web_phrases.py`
binds `phrases.json` to the core.

**Extends:** D19, which says the page is served by the front-end container
at its root and says nothing about the paths below it.

**Why:** The page has no router. Every screen is drawn into one `<main>` and
nothing is addressable, so a reload always returns to whatever `listRuns()`
implies, Back leaves the application entirely, and remembering scroll
position per run and view is not merely unbuilt but impossible. Once the
runs list is home, a reload during a twenty-eight-event review drops the
reviewer back to the list - a regression introduced by that change, and one
that has to be answered in the same work.

**The fallback enumerates, and does not catch all.** `web/` is mounted
through `StaticFiles(html=True)` at `/` (`star_pass_bff/_app.py:94`), which
returns 404 for any path that is not a real file. A blanket catch-all would
answer a mistyped module path with `index.html` and a 200, turning the loud
404 that `tests/test_web_page.py` exists to catch into a screen that
silently never draws. Enumerating costs one list; the test holds the two
lists together.

**Note:** the session cookie is `SameSite=Strict` (D18). A run link the
operator types or bookmarks sends it normally; one followed from another
site arrives without it and the front end mints a fresh session. Harmless
while there is no login, and written down here rather than rediscovered.

**Rejected:** hash routing (no server change and immune to the catch-all
hazard, but the fragment never reaches the server and it is the legacy
pattern); a routing library (it would need a CDN, which the CSP and D14
forbid, or a build step, which `web/` rejects by design).

**Revisit if:** a screen needs state a path cannot carry, or a login
appears - a cross-site arrival minting a fresh session stops being
harmless the moment a session means someone is signed in.

---


## D29 - Unassigned is a state, not the absence of one

**Decided:** An event the collection matched no category for is shown as
**Unassigned**, and a person may put a row back to it. The option is
offered only on rows the collection matched nothing for; a row that
matched a category has no way to unassign it, and asking for one is
refused. Unassigning is its own operation, `unassign`, and the core
answers whether a row may be unassigned (`may_unassign`) the way it
already answers whether one may be undone.

**Why:** The state existed and had no name. The row drew a prompt reading
"Select an opportunity", which is an instruction rather than a state, and
nothing could return a row to it - so the one edit a reviewer makes on a
row that matched nothing was the one edit with no way back, and D26's
undo had to carve out an exception for those rows to avoid stranding
somebody in a state they could not leave. Naming the state and making it
choosable removes the exception instead of accommodating it.

**Nothing new is stored, and the data model does not change.** Unassigned
is the name for the category being absent, which is what the row already
holds. A category in `shift_info.yml` yielding no need IDs would be a
special case for every reader that walks a category, and an event stored
under a category the model no longer defines makes its whole run
unreadable - `category_named` refuses on the path every read takes, which
is how the officiating-practice merge broke a run mid-phase. The absence
is already handled correctly everywhere: `blocks_the_run`, `timings_for`,
the preview and the send all read it.

**A matched row is refused rather than merely not offered the option.**
The API is the contract (D1), so a rule the screen keeps and the service
does not is a rule the system does not have. What a matched row that
should create no shift wants is **Remove**, which takes it out of the
revision; unassigning it would leave a row behind that blocks the whole
run, which is a worse Remove.

**Rejected:** a category in the data model (above); letting `set_category`
carry no category instead of a separate operation - the field is already
optional in the request shape, so an omitted category and a deliberate
one would be the same request, and forgetting the field would silently
unassign a row rather than being refused; offering Unassigned in the bulk
toolbar - a selection mixing matched and unmatched rows would be refused
whole, for a reason the person selecting could not have predicted.

**Consequence:** `unassign` joins `OPERATIONS`, `EventView` publishes
`mayUnassign`, and the contract is regenerated. No schema change. The
chooser offers the option where the core says it may, which refines D26's
companion change: the prompt was drawn on rows whose category is null,
and the option is drawn on rows whose *collected* category is null, so an
assigned row keeps its way back.

**Revisit if:** a matched row ever needs to stop creating shifts without
leaving the revision, which would mean Remove and Unassigned are answering
different questions after all.

---


## D30 - The calendar note is stored as text, and the calendar says whether there is one

**Decided:** An event on a calendar configured to carry notes keeps its
Google Calendar description, converted to plain text at collection and
stored with the event. `events` and `uncollected_events` each gain
`calendar_note`. The review screen draws a control beside the calendar
times on every row of such a calendar, whether or not the event has a
note, and says so when it has none. Whether a calendar carries notes is a
property of the calendar's configuration, published on `CalendarView`.

**Why:** The `events` calendar puts the two times a volunteer needs in the
description - "G2: Doors at 1 PM, Game at 1:30 PM" - and nothing in the
interface showed it, so the only way to read it was to open Google
Calendar beside the review screen.

**Stored as text, never as markup.** The description arrives as HTML about
as often as not, and its shape is not predictable:

```html
<br><table><tbody><tr><td>Doors at 6 PM, Game at 7 PM</td></tr></tbody></table>
```

The conversion runs once, at collection, through the standard library's
own parser. Block ends become line breaks, entities are unescaped, runs of
whitespace collapse, and every tag is dropped, so both shapes of the
example above store the same sentence. Storing text rather than markup is
what makes the value safe wherever it is read: a client renders it as
text, and a client that one day rendered it as markup would still have
nothing to render. The Content Security Policy (D14) is a third line
behind those two, not the argument.

**The note is truth about the calendar, so an edit never moves it**, in
the same way and for the same reason that the calendar times never move.
It is not part of what `as_collected` compares, because a row whose note
differed from its collected note would be a row the reviewer could not
have changed.

**A cap of 1000 characters.** A description may hold an agenda, and this
value crosses the wire on every read of every row of a run. The cap is on
the stored text, so what a reader sees and what the run holds are the same
thing.

**The calendar answers whether there is a control, not the browser.** A
client deciding it by the calendar's name would be a client second-
guessing configuration it is handed, and the calendars are configured
rather than fixed. `GCAL_CALENDARS` gains `notes` beside `query_strings`,
and a calendar without it stores no note and draws no control.

**Rejected:** reading the description live when the control is opened (what
a run did not collect is stored, never read live, and a note read later
would describe the calendar as it is now rather than what the run saw);
storing the HTML and sanitizing in the browser (two sanitizers, one of
them in the place where getting it wrong executes); naming the `events`
calendar in `web/` (above).

**Consequence:** schema version 11, one migration adding a nullable column
to two tables, `EventView` and `UncollectedEventView` publish
`calendarNote`, `CalendarView` publishes `notes`, and the contract is
regenerated. An event collected before this version has no note and reads
as having none until its run is collected again.

**Revisit if:** a second calendar carries notes in a shape the converter
mangles, or a note ever needs to be edited - it is the calendar's text
today, and editing it would make it the run's.

---


## D31 - A collection that fails leaves a state somebody can act on

**Decided:** A collection that raises no longer leaves its run saying it is
being collected. A run whose **first** collection failed is `failed`, a new
terminal status. A run whose **recollection** failed goes back to `unsent`,
which is the only status it could have held. A `failed` run may be
collected again, which is how it is recovered, and may not be sent.

**Why:** `set_status` was reached only inside the transaction that stores a
successful collection, so anything raising before it - the calendar
unreachable, a window that cannot be resolved, an opportunity that cannot be
read - left the run in `collecting` for ever. Retention does not sweep runs,
so before D24 nothing could remove one either.

**The two cases are not the same state, and the plan's "a terminal state"
is right for only one of them.** A recollection that fails has done no harm
to what the run already holds: its previous revision is complete and
sendable. Putting that run into a failure state would strand work that is
still good. Worse, `why_not_send` refuses a run whose status is
`collecting`, so today a failed recollection makes an otherwise sendable run
**permanently unsendable**.

**Which case it is, is answered by the run and not by the caller.** A run
that has never completed a collection has no revision, so
`current_revision` is 0; a recollection is working over at least one. The
caller cannot answer it - by the time the work runs, the status has already
been set to `collecting` - and threading the previous status through the
job would be a second copy of something the run already says.

**`unsent` is not a guess.** `why_not_recollect` refuses any run in
`RUN_STATUSES_SENT`, so `unsent` is the only status a recollection can begin
from.

**A failed run is refused a send.** It holds no revision and so no shifts,
and a send of nothing would still stamp `sent_at` - which under D24 makes
the run undeletable for ever. The refusal is the core's, not the screen's
(D1).

**Rejected:** reusing `unsent` for both (a first collection that failed
would be indistinguishable from one that legitimately collected an empty
window, and the run's own status is the only place that distinction can
live); leaving the first case in `collecting` (the state it is being fixed
for); a `failed` column beside the status rather than a status (two fields
answering "what is this run" is the shape D22, D23 and D27 each removed).

**Consequence:** `failed` joins `RUN_STATUSES`, which is no longer a
sequence a run walks in order. Each client words it, bound to the core's
tuple by the tests that already hold the others. No schema change: the
column is text and already holds any status the core names.

**Revisit if:** a collection ever fails part way through having written a
revision, which would make "has a revision" the wrong question. It cannot
today - the revision and the events are written in one transaction.

---


## Deferred, on purpose

- **An authentication boundary in front of the whole system.** Deferred: single
  user, controlled tokens, network-level access control (D14) standing in.
  Revisit the moment a second person needs in, or public exposure is considered.
- **Slack summary mode.** Out of scope.
