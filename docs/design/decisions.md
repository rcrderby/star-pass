# Star Pass — decision record

One entry per decision, with why, what was rejected, and **what would make us
revisit it**. Append new entries; don't rewrite old ones — supersede them.

Companion to `api-and-security-plan.md` (the plan these decisions produced).
Last updated: 2026-08-13.

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

**Revisit if:** local mode and remote mode start behaving differently — that
would mean the core boundary has leaked, and HTTP-only becomes the honest fix.

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

## D12 — Retention: sent record forever, CSVs and logs 90 days

**Decided:** The sent record is never purged. CSVs and job logs expire after 90
days. Superseded revisions are deleted immediately. Both windows are config
values.

**Why:** Duplicate safety depends on the sent record, so it can't expire. The
driver for expiring the rest is PII, not disk — stale CSVs hold volunteer names
and schedules.

**Rejected:** keep everything (unbounded PII at rest with no expiry); 30-day logs
(shorter than the monthly feedback loop — a problem found at next collection
would have no evidence left).

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

## Deferred, on purpose

- **An authentication boundary in front of the whole system.** Deferred: single
  user, controlled tokens, network-level access control (D14) standing in.
  Revisit the moment a second person needs in, or public exposure is considered.
- **Slack summary mode.** Out of scope.
