# Running a deployment

How star-pass runs: two application processes and a reverse proxy, the
networks between them, and the addresses each serves. The shape of it is
drawn in [`architecture.md`](architecture.md), which is the quickest way
to see it before reading any of this.

Getting a deployment up for the first time is in the
[Readme](../README.md); this file is what the arrangement is and why.

## Running the services

```bash
uvicorn --factory star_pass_api:create_app     # the API
uvicorn --factory star_pass_bff:create_app     # the frontend
```

Two processes, and in a deployment two containers: only the API holds
the Amplify credential, and the frontend is the one facing a browser.
The browser talks to the frontend, which attaches the API credential
to what it forwards - so no credential is ever in the page, and there
is nothing for a script injected into it to steal. Writes have to
carry a token the frontend put in a readable cookie, in a header,
which is what an off-site page cannot do.

The frontend needs `STAR_PASS_SESSION_SECRET` as well as
`STAR_PASS_API_TOKEN`, and refuses to start without either. Both are
commented out in `.env.example`, so a checkout that predates them has
them commented out too; `docker compose` stops with the name of
whichever is missing. It also refuses to start with no page to serve:
it exists to give a browser one and to carry its session, so a proxy
with nothing behind it would be reachable and unusable.

## Running both behind Caddy

```bash
docker compose up
```

One command, three containers, and the arrangement the plan has
assumed since D5 and D17. It is drawn in
[`architecture.md`](architecture.md). Caddy is the only one
with a published port:
it terminates TLS, redirects plain HTTP to it, and passes the request
to the frontend. Neither application service is reachable from outside
the host.

They sit on two networks rather than one. Caddy and the frontend share
the first; the frontend and the API share the second. Caddy is
deliberately absent from the second, so the path to the service
holding the Amplify credential runs through the process that checks a
write came from its own page -- and through nothing else. The
credential file and the database volume are attached to the API
service alone (D9, D17), and the frontend is handed the two values it
needs by name, neither of which is an Amplify credential.

Out of the box the site is `https://localhost`, served with Caddy's
internal certificate authority, which is what D14 asks for while
building. Your browser will not know that authority; either accept the
warning or trust the root Caddy writes to its `caddy_data` volume.
Set `STAR_PASS_SITE_ADDRESS` to serve a different name.

Real certificates are a deployment concern and there is no ACME code
in the application. Setting `STAR_PASS_TLS` to an email address
switches Caddy to Let's Encrypt, which needs a publicly resolvable
name -- a deliberate step, since D14 decided against putting an
unauthenticated-by-design system on the public internet.

**HSTS is deliberately off.** It is a promise a browser will not let
you take back, so `deploy/caddy/conf.d/hsts.caddy.example` ships as an
example and is copied to `hsts.caddy` once the domain is settled and
not before. The Caddyfile imports that directory with a glob, and a
glob matching nothing is not an error.

Forwarded headers are trusted from exactly one hop: the frontend is
started with `--forwarded-allow-ips` naming the address Caddy is
pinned to on the shared network, never `*`. The API is started with
`--no-proxy-headers`, because nothing proxies to it -- the frontend
forwards an allowlist of headers that does not include the
`X-Forwarded-*` pair. Note what that setting does and does not cover:
uvicorn reads `X-Forwarded-For` and `X-Forwarded-Proto` and rewrites
the client address and the scheme, and never touches `Host`. `Host` is
what the frontend compares `Origin` against on a write, and what makes
that comparison trustworthy is Caddy answering a request whose `Host`
matches no named site rather than passing it on.

Because nothing but Caddy is published, the documentation addresses
the API serves are reachable only from inside the deployment. Read
them with `docker compose exec` or by forwarding a port, not by adding
a route: a second way in to the credential-holding service is the
thing this arrangement exists to prevent.

Copy `.env.example` to `.env` before the first `docker compose up`.
Docker creates a directory where the credential file is mounted if the
file is not there.

Both application containers run as an unprivileged account rather than
as root, and the database volume is created owned by it. Two things
follow. The credential file has to be readable by something other than
its owner -- what `cp .env.example .env` produces is, and a file
tightened to `0600` is not. And a volume that already holds a database
keeps the ownership it was created with, because Docker copies the
image directory's ownership onto an empty volume only: a deployment
that predates this either discards its volume with `docker compose
down -v` or changes the ownership by hand.

## The page it serves

`web/` is the interface, and there is **no build step**: the ES
modules and the CSS committed there are what a browser is given,
and the image copies the directory as it is. Nothing needs installing
to work on it, and `STAR_PASS_WEB_ROOT` points the service somewhere
else when a checkout wants to serve a working copy instead.

Inter and the Phosphor icons are served from `web/assets/` rather than
from a content delivery network. The Content Security Policy is
`default-src 'self'`, so a font or an icon set from another origin is
refused by the browser, and the deployment is meant to work on a
tailnet with no route out - where it would never arrive at all. Both
are redistributable and their licences are beside them.

**Every screen has an address** (D28). The page opens on the runs
list, and a run, what it left out and its preview each have a path:

| Path | What it draws |
| --- | --- |
| `/`, `/runs` | Every run, with its window, counts and status |
| `/runs/{id}` | One run's shifts to create |
| `/runs/{id}/uncollected` | What that run's window left out |
| `/runs/{id}/preview` | What sending it would create |
| `/settings` | What the service resolved at start up |

So a run can be reloaded, bookmarked, or opened in a second tab, and
Back goes to the runs list rather than out of the application. The
frontend answers those paths, and only those, with the page: anything
else that is not a file is still a 404, because a blanket fallback
would answer a mistyped module path with the page and a 200, and the
screen would silently never draw.

A run being worked on opens on the work, so `/` goes to that run while
a collection or a send is running. The session cookie is
`SameSite=Strict`, so a run link followed from another site arrives
without it and the frontend mints a fresh session - harmless while
there is no login.

## Reading the API specification

The service describes itself at three paths, and **none of them is
reachable from outside a deployment**. The Caddyfile calls Caddy "the
only process in this deployment with a published port" and passes
everything to the frontend; the API publishes no port and sits on a
network a browser never touches (D5, D6, D17). That is deliberate, and
these paths are not a reason to change it.

| Path | What it serves |
| --- | --- |
| `/docs` | Swagger UI |
| `/redoc` | ReDoc |
| `/v1/openapi.json` | The specification itself |

**The specification is also a file in this repository**, at
`docs/api/openapi.json`, written by `scripts/generate_contract.py` and
regenerated whenever a route, model, scope or version changes. It is
the same document the running service serves, which is what makes the
next command worth knowing: it needs no deployment, no port and no
credential.

```bash
docker run --rm -p 8080:8080 \
  -e SWAGGER_JSON=/spec/openapi.json \
  -v "$PWD/docs/api:/spec:ro" \
  swaggerapi/swagger-ui
```

Then open `http://localhost:8080`. Swagger UI ships inside that image,
so nothing is fetched from anywhere once it has been pulled, and what
it renders is the committed contract rather than a copy that could
have drifted from it.

To reach the running service's own pages instead, run the API outside
the deployment and visit them on its port:

```bash
uvicorn --factory star_pass_api:create_app --port 8000
```

**`/docs` and `/redoc` fetch Swagger UI and ReDoc from a content
delivery network**, which is FastAPI's default and the one place this
application reaches another origin. On a machine with no route out
they render as an empty page. Vendoring those assets the way
`web/assets/` vendors Inter and Phosphor is worth doing and is not
done; until it is, the container above is the offline way to read the
same specification.
