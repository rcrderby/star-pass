# Star Pass — decision record

One entry per decision, with why, what was rejected, and **what would make us
revisit it**. Append new entries; don't rewrite old ones — supersede them.

Companion to `api-and-security-plan.md` (the plan these decisions produced).
Last updated: 2026-08-19.

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


## Deferred, on purpose

- **An authentication boundary in front of the whole system.** Deferred: single
  user, controlled tokens, network-level access control (D14) standing in.
  Revisit the moment a second person needs in, or public exposure is considered.
- **Slack summary mode.** Out of scope.
