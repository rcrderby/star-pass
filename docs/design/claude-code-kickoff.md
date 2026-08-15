# Claude Code kickoff — steps 1 to 3

Paste this as the opening prompt in Claude Code, in the `rcrderby/star-pass`
repository. It covers only the first three steps of the work order in
`api-and-security-plan.md`, because those are the ones that create or prevent
technical debt; stop and review before going further.

Bring these four files with you: `api-and-security-plan.md` (the plan),
`decisions.md` (D1–D17, with revisit triggers), `openapi-v1-sketch.yaml` (the
design-side surface sketch — a checking artifact, not the spec: FastAPI generates
the real one and the sketch is deleted then), and this file.

---

## Prompt

> We are turning `star-pass` from a CLI into an API-first application. The API is
> the contract; the CLI and a future web UI are both clients. Read
> `api-and-security-plan.md` and `decisions.md` first — they are decided, not
> suggestions. Do not start on the web UI, and do not add endpoints beyond the
> ones listed below.
>
> Work in three steps and stop after each for review. Do not begin a step until
> the previous one's tests pass.
>
> **Step 1 — extract the core package.** Move all domain logic out of the CLI
> into a `star_pass` core package: calendar collection, title matching, CSV
> build, Amplify writes, the sent record. The core must contain no HTTP server
> code, no argument parsing, and no printing — it returns values and raises typed
> exceptions. The CLI becomes a thin client calling the core in-process, and its
> command surface and output must not change. Before you move anything, write
> characterisation tests that pin current behaviour, including: duration capped
> silently at `max_length`; duration ≤ 0 a hard exit; empty need id blocking the
> run; duplicate rows dropped; the title filter running before the all-day check;
> fuzzy match threshold 80; window end exclusive; dates read in
> `LOCAL_TIMEZONE`. There is no 60-day window cap — do not add one.
> Put state access behind a repository layer over SQLite (D7): no SQL outside it.
>
> **Step 2 — the API skeleton.** FastAPI, path-versioned at `/v1`. Build these
> before any endpoint that does work:
> - One authentication dependency that verifies a bearer token from the
>   environment with `secrets.compare_digest` and returns `Principal(id, scopes)`.
>   Nothing else in the codebase may read the token or the header. 401 with
>   `WWW-Authenticate: Bearer` for bad credentials, 403 for insufficient scope.
> - Scopes declared on every route from day one: `runs:read`, `runs:write`,
>   `send:execute`, `config:read`.
> - An exception handler returning `application/problem+json` (RFC 9457) with a
>   `reference` id. Upstream response bodies are never returned to a client; full
>   detail goes to the log through a redaction filter for bearer tokens,
>   `Authorization` headers and email addresses.
> - Credentials read once at startup from a read-only mounted file whose path
>   comes from an environment variable, 0400, service-account owned; fail fast if
>   missing or malformed (D9). No endpoint may write a credential (D8).
> - `GET /v1/health` unauthenticated; `GET /v1/version` behind auth.
> - Structured JSON logs to stdout. All config from the environment, validated at
>   startup.
> - Commit the generated OpenAPI spec and add a CI check that fails on drift.
>   Swagger UI at `/docs` open, Scalar or Redoc for reference; every endpoint
>   authenticated (D15).
>
> **Step 3 — the job model.** Long operations are resources, not requests.
> `POST` returns `202` with a job id; `GET /v1/jobs/{id}` is status; SSE at
> `GET /v1/jobs/{id}/events` streams progress. Jobs live in SQLite so a closed
> tab or a restart does not lose one. On boot, any job left running is marked
> **interrupted** — never resumed automatically, never left "running" (D10).
> Run ids are server-minted; nothing accepts a client-supplied id or a file path.
> Every write records principal id, timestamp and idempotency key (D13).
>
> Constraints that apply throughout: no endpoint that takes CLI arguments or
> proxies Amplify; no endpoint addressed by file path; nothing that writes
> `shift_info.yml` or code; `POST /v1/credentials/test` returns ok plus last-four
> only and is rate-limited. The CLI must keep working with no server running
> (D2) — `--api-url` / `STAR_PASS_API_URL` selects the remote client, which is
> generated from the spec.
>
> Tell me when a decision in `decisions.md` looks wrong in contact with the code,
> rather than working around it. Note the revisit triggers — several decisions
> have them.

---

## What is deliberately not in this prompt

- Send, collect and preview endpoints (step 4 onward) — they need the job model
  and the idempotency table first.
- The BFF and session cookie (step 7). The browser must never hold an API token,
  so this lands after the write endpoints are stable.
- Caddy, TLS and the Tailscale-style access decision (step 8, D6/D14).
- The retention job (step 9, D12).

## Where the design lives

`Create Shifts v2.dc.html` in the design project is the web UI these endpoints
have to serve, and `openapi-v1-sketch.yaml` is that UI's needs written as a
surface. It already assumes: server-minted run ids, a reattachable collection
with an id, per-shift duplicate identity (need id + date + start + end, never a
count), continuous editing through `PATCH /runs/{id}/events` with a server-side
change log, opportunity titles stored on the run, a two-step confirmation before
an irreversible send, sanitized errors with a copyable reference id, and
league-timezone windows with an inclusive last day. If an endpoint cannot support
one of those, that is a design conversation, not a silent divergence.
