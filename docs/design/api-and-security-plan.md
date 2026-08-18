# Star Pass — API-first architecture and security plan

Status: agreed direction, not yet implemented. Written for handoff to Claude Code.
Companion to `CLAUDE.md` (design conventions) and `github.md` (source repo).

---

## 1. The inversion

**Previous decision:** the CLI is the API; the web UI shells out to it.

**Current decision:** the API is the contract; the CLI is one of its clients.

Everything the web UI can do is reachable over the HTTP API, and the CLI can do
anything the web UI can do. New functionality is added to the core and exposed
through the API — never wired directly into the web UI.

### Three layers

| Layer | Responsibility |
| --- | --- |
| `star_pass` core (Python package) | All domain logic: calendar collection, title matching, shift timing, editing, Amplify writes, sent record. No HTTP, no argv, no printing. |
| API service (FastAPI) | The only *remote* surface over the core. Owns credentials, SQLite state, job lifecycle, authn/authz. Its own container; the CLI ships in this image. |
| Clients | The CLI and the web BFF. Neither contains domain logic. The BFF is a separate container with no credential mount (D17). |

**The CLI keeps working with no server running.** It calls the core package
in-process by default; `--api-url` (or `STAR_PASS_API_URL`) switches it to the
generated remote client. Same command surface either way. This is why the core
package is the single source of truth and the API is the single *remote*
contract — those are two different claims and both need to hold.

### What this deletes

- The web UI no longer shells out, so **argv/shell injection stops being a
  surface**. The API calls Python functions with typed, validated arguments.
- The browser never touches Amplify credentials — only the API service does.
- Run identity, idempotency and duplicate checks move server-side, where they
  belong, instead of being minted in JavaScript.

---

## 2. Authentication

### Now: static bearer token, built for migration

- Token from the environment (`STAR_PASS_API_TOKEN`), never a file, never a flag.
- `secrets.compare_digest` — constant time. Never `==`.
- Verification lives in **exactly one** FastAPI dependency that returns a
  `Principal(id, scopes)`. No other module reads the token or the header.
- Every route declares required scopes from day one, even with one principal
  (`runs:read`, `runs:write`, `send:execute`, `config:read`).
- Correct semantics: 401 with `WWW-Authenticate: Bearer` for missing/invalid
  credentials, 403 for authenticated-but-insufficient-scope.
- No token in a query string, ever — it lands in access logs.

### Later: OIDC, without a rewrite

Because authentication is one dependency producing a `Principal`, the migration
is: replace token comparison with JWT validation against the issuer's discovery
document and map claims to scopes. Routes don't change. The BFF becomes the OIDC
client. The CLI gains a device-authorization flow — the only genuinely new work,
and the reason not to do it now.

### Browser → API: the BFF pattern

```
browser ──httpOnly session cookie──> front-end (BFF, same origin) ──bearer token──> API
```

- The browser holds **no** API credential. XSS cannot exfiltrate a token that
  isn't there.
- Session cookie: `HttpOnly`, `Secure`, `SameSite=Strict`, `Path=/`, no
  long-lived remember-me.
- CSRF: `SameSite=Strict` plus a required custom header on every state-changing
  request; reject cross-origin `Origin`/`Sec-Fetch-Site` on writes.
- Same origin means **no CORS configuration at all** on the API. If you find
  yourself adding CORS for the browser, the boundary has leaked.
- The BFF is a thin proxy: authentication, session, CSRF, request shaping. Zero
  domain logic.

---

## 3. Transport

- TLS terminated at **Caddy** in front of both services. Automatic Let's Encrypt
  issuance and renewal, HTTP→HTTPS redirect, HSTS.
- Public DNS name with 80/443 reachable → HTTP-01. Not publicly reachable →
  DNS-01 with the provider module. Pure localhost → Caddy's internal CA.
- **No ACME code in the application.** TLS is the platform's job (twelve-factor:
  the app is behind a routing layer).
- The app listens on plain HTTP on the internal network and trusts forwarded
  headers from exactly one known hop — `FORWARDED_ALLOW_IPS` scoped to the
  proxy, never `*`.
- HSTS with a long max-age once the domain is settled; not before.

---

## 4. Documentation

- FastAPI generates **OpenAPI 3.1**. Nothing is hand-written.
- Swagger UI at `/docs` for try-it; **Scalar** (or Redoc) for readable reference.
  Docs UI is open; every endpoint requires authentication. Docs are not secrets.
- The generated spec is **committed to the repo**, and CI fails when code and
  spec drift.
- The CLI's remote client is **generated from the spec**. This is what makes
  "the CLI can do anything the web UI can" structural rather than a discipline.
- Path-versioned: `/v1`. Additive changes only within a version.

---

## 5. v1 API surface

### In

| Resource | Notes |
| --- | --- |
| `GET /v1/health`, `GET /v1/version` | Unauthenticated health; version behind auth. |
| `GET /v1/runs`, `GET /v1/runs/{id}` | Runs by **server-minted id**, never file path. |
| `GET /v1/runs/{id}/revisions` | Revision list; superseded revisions deleted per policy. |
| `POST /v1/runs` → `202` + job | Collect. Async. Identified by calendar + window + time. |
| `POST /v1/runs/{id}/recollect` → `202` | Replaces the run. Returns a change count for the warning. |
| `GET /v1/runs/{id}/preview` | Dry run; totals grouped by Amplify opportunity title. |
| `POST /v1/runs/{id}/send` → `202` + job | Idempotent. See §6. |
| `GET /v1/jobs/{id}`, `GET /v1/jobs/{id}/events` | Status + SSE progress. Reattachable. |
| `GET /v1/runs/{id}/uncollected` | Second unfiltered calendar read. |
| `POST /v1/runs/{id}/events` | Pull a search-missed event in. Rejects cancelled events server-side. |
| `GET /v1/config` | Read-only. |
| `POST /v1/credentials/test` | Returns ok + last-four only. Rate-limited. |
| `GET`/`POST /v1/unmatched-titles` | Append-only log for later model updates. |
| `PATCH /v1/runs/{id}/events` | **Edit the current revision** — opportunity, times, slots, nudge, reset, remove, undo, singly or over a selection. One call per user action, returning the updated events and the log entries it produced. The most used endpoint in the product; missed in the first pass and found by sketching the surface against the real screens. |
| `POST /v1/runs/{id}/revisions`, `…/revisions/{n}/revert` | Seal a revision; revert to one. Neither is destructive, so a revert opens **one** revision: the one it leaves stays readable at its own number and has nothing to be saved from. Reverting to revision 1 also drops hand-added events and returns them to Not collected. |
| `POST /v1/jobs/{id}/resume` | Resume an interrupted job, by explicit request only (D10). |

Four more findings from that same sketching, all additive:

- **The change log belongs server-side.** It is built in the client today, so it
  dies on reload and the CLI cannot show it. Since every edit is now an API call,
  the log is the natural response to those calls.
- **Opportunity titles are resolved during collection and stored on the run**, not
  looked up at preview time — the review rows label every role with an Amplify
  title, so a preview-only lookup leaves the main screen unable to label anything.
- **`uncollected` is served from stored collection data**, never a live calendar
  read: the Not collected tab shows a count on every page load.
- **`expectedChangeCount` on recollect and `expectedShiftCount` on send.** Both
  let the server refuse when what the user was shown no longer matches reality,
  which closes the stale-tab case a confirmation dialog otherwise invites.

### Deliberately out

- **`PUT /credentials` — credential replacement.** Rotation is a platform
  operation: change the env/secret, restart. An endpoint that can overwrite the
  service's own Amplify credential is the highest-value target in the system for
  the least benefit. *Design consequence: Settings loses the replace flow and
  keeps test + last-four.*
- **Any generic escape hatch** — no endpoint taking CLI arguments, no Amplify
  passthrough proxy. One of these undoes the whole model.
- **Anything addressed by file path** — no download taking one.
  Ids only; path traversal shouldn't be expressible.
- **Config writes** — read-only, as decided.
- **Anything touching code or `shift_info.yml`** — kept out of the spec so it
  can't drift back in.
- **Run/revision deletion** — retention policy does this, not a caller.

---

## 6. Idempotency and duplicate safety

- Run ids are **server-minted**. The current design mints `run-<Date.now()>` in
  the browser; that must go.
- `POST /v1/runs/{id}/send` requires an `Idempotency-Key` header. Key is stored
  in SQLite with the response; a replay returns the original result rather than
  writing again.
- Per-shift idempotency, not per-run: the unit is
  `(run_id, need_id, start, end)`. Partial send and retry-only-what-failed
  follow from this.
- Duplicate detection uses **row identity from Amplify** — need id + start + end
  — not a count. *The current design compares a count and skips "the first N by
  date," which can skip the wrong shifts and still create duplicates.*
- Checked twice: when a run is opened, and again inside the send transaction.

---

## 7. Input validation

Validated at the API boundary with Pydantic, mirroring the CLI's schema so both
clients fail the same way:

- Window: two dates, end exclusive, end > start, one-day windows allowed. Parsed
  in `LOCAL_TIMEZONE` (America/Los_Angeles) — **the server's zone is
  authoritative**. The browser must send dates, never compute presets in its own
  zone. *This is a live bug in the current design.*
- No 60-day cap. An earlier design invented one; it isn't real.
- Calendar identifiers: allowlisted from config, not free text.
- `need_id` 6 digits, `duration` 1–4 digits, `slots` 1–3 digits. Duration ≤ 0 is
  a hard reject; duration over `max_length` is capped, and the API reports the
  cap rather than capping silently.
- Empty need id blocks the run — reject at validation with a clear message
  instead of failing mid-send.

---

## 8. Errors, logs and secrets

- Error responses are `application/problem+json` (RFC 9457): `type`, `title`,
  `status`, `detail`, plus a `reference` id.
- **Raw upstream bodies are never returned to a client.** They can carry tokens
  and volunteer PII. The client shows a sanitized summary and the reference id.
- Full detail goes to the server log, through a redaction filter (bearer tokens,
  `Authorization` headers, API keys, email addresses) before it is written.
- Structured JSON logs to stdout. No log files, no log rotation in the app.
- Secrets appear in exactly one place: the process environment of the API
  service. Not in SQLite, not in job records, not in the BFF's
  session store.
- `POST /credentials/test` is rate-limited so the endpoint can't be used as a
  credential oracle.

---

## 9. Configuration (twelve-factor)

- All config from the environment; no config files read at runtime except the
  domain's own `shift_info.yml`, which is read-only input.
- Fail fast at startup on missing or malformed required config — never a
  half-configured service that fails at send time.
- Backing services (SQLite path, Amplify base URL, calendar ids) are attached
  resources named by env var.
- The API service is stateless apart from its attached SQLite volume; it must
  survive being killed mid-job (jobs resume or are marked failed on boot, never
  left "running" forever).
- Same image for CLI and API; the entrypoint differs. Guarantees identical core.

---

## 10. Work order

1. Extract the core package out of the CLI. No behavior change, tests pin
   current behavior. Everything else depends on this.
2. FastAPI skeleton: auth dependency + `Principal`, problem+json handler,
   `/health`, generated spec committed, CI drift check.
3. Job model: SQLite-backed jobs, SSE progress, resume-on-boot.
4. Read endpoints (runs, revisions, preview) and the generated client.
5. CLI dual mode — local by default, `--api-url` remote — proving the contract.
6. Write endpoints: collect, recollect, send with idempotency keys.
7. BFF: session cookie, CSRF, proxy. Web UI stops holding anything.
8. Caddy in front, HSTS, forwarded-header trust scoped to the proxy.
9. Retention policy job for job logs and revisions, and the command
   that applies the same policy to a local database. `unmatched_titles`
   is answered by the data model rather than by a window: a sighting is
   forgotten once the model matches its title, with a year as a
   backstop for one nobody ever acted on. Three axes, because the
   question has three different answers (D20).

Steps 1–3 are the ones that create or prevent technical debt. The rest is
mechanical once they're right.

---

## 11. Settled and still open

Every decision, with its rationale and a revisit trigger, is recorded in
`decisions.md` (D1–D21). Settled since this plan was first written:

- Credentials arrive as a **read-only mounted secret file**, path from an env var,
  0400, read once at startup, fail fast (D9). Replacement stays out of the API (D8).
- State access goes through a **repository layer**; SQLite behind it (D7).
- Interrupted jobs are **marked interrupted with a one-click resume** (D10).
- Send is gated by a **two-step confirmation** restating count and window (D11).
- Retention: sent record forever, **job logs 90 days**, superseded revisions
  deleted immediately; both windows are config values (D12).
- Writes record **principal id, timestamp and idempotency key** (D13).
- Access via **Tailscale-style device-level networking**; Caddy internal CA while
  building (D14).
- **No Kubernetes** — Compose on one host (D5); **no app-level TLS between the
  services** (D6).
- The front-end and API are **separate containers**, with the credential mount
  attached to the API service only; the CLI ships in the API image (D17).
- The browser's session is an **opaque id with a derived CSRF token**, no session
  library and no server-side store while a session carries nothing (D18).
- The web page is served by the **front-end container at its root**, because it
  is the only origin it can work from; the prototype stays design-side and is not
  ported (D19).
- Retention runs on **three axes rather than one window**, and the unmatched
  titles are removed by the model coming to match them rather than by age
  (D20). This supersedes D12's "superseded revisions deleted immediately",
  which predates revisions being revertible.
- **No 2.x release** until the web interface can be exercised end to end
  (D21).

Still open:

- Auth boundary in front of the whole system. Deferred by decision: single user,
  controlled tokens, network-level access control standing in.

## 12. UI changes this implies

Design-side follow-ups in `Create Shifts v2.dc.html`:

- Settings: remove credential replacement; keep test + last-four, and say that
  rotation happens in the environment.
- Run ids come from the server; the collecting screen shows one and is
  reattachable, with an in-progress entry in the runs list.
- Window presets stop being computed in the browser's timezone; show the
  authoritative zone.
- Failure states for collect, the Amplify read and send — currently absent.
- Duplicate warnings phrased per shift rather than as a count.
- Errors show a sanitized summary plus a copyable reference id.
