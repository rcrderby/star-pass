# Deployment

A `star-pass` deployment is three containers: a reverse proxy (Caddy),
the frontend, and the API. To set up a deployment for the first time,
follow the [Readme](../README.md). [`docs/architecture.md`](architecture.md)
has diagrams of the deployment.

## The Services

The API and the frontend are the two application services:

```bash
uvicorn --factory star_pass_api:create_app     # the API
uvicorn --factory star_pass_bff:create_app     # the frontend
```

The API reads the League Calendar, reads and writes Amplify, and owns
the database. The frontend serves the web UI and forwards its requests
to the API with the API token. The browser does not receive any
credentials.

Every request through the frontend requires a session. The frontend
creates a session when it serves the web UI. A write request also
requires the session's CSRF token in the `X-Star-Pass-CSRF` header, and must
come from the same site.

The frontend sets a Content-Security-Policy and two other security
headers on every response. The Caddyfile sets the same three headers,
and an automated test checks that the two copies match.

These six values in `.env` are required:

| Value | Required By |
| --- | --- |
| `STAR_PASS_API_TOKEN` | The API and the frontend |
| `STAR_PASS_SESSION_SECRET` | The frontend |
| `AMPLIFY_TOKEN` | The API |
| `GCAL_TOKEN` | The API |
| `GCAL_EVENTS_CAL_ID` | The API |
| `GCAL_PRACTICES_CAL_ID` | The API |

If a service is missing a required value, it does not start, and its
log names the missing value. To read the logs:

```bash
docker compose logs api
docker compose logs frontend
```

Set the missing value in `.env`, then run `docker compose up -d` again.
The frontend also does not start if it has no web UI to serve.

## Running Behind Caddy

To start the deployment:

```bash
docker compose up -d
```

Caddy is the only container with a published port. It ends TLS,
redirects HTTP to HTTPS, and passes each request to the frontend. The
frontend and the API are not reachable from outside the host.

Caddy publishes ports 80 and 443 on the address in
`STAR_PASS_BIND_ADDRESS`. The default address, `127.0.0.1`, serves
`star-pass` to the host only. To serve `star-pass` to a tailnet, set
`STAR_PASS_BIND_ADDRESS` to the host's tailnet address and run
`docker compose up -d` again. Setting it to `0.0.0.0` publishes
`star-pass` on every interface. On a host with a public interface, that
includes the internet.

### Networks and Hardening

The containers use two networks:

| Network | Containers |
| --- | --- |
| `edge` | Caddy and the frontend |
| `backend` | The frontend and the API |

Caddy is not on `backend`. Only the API has `.env` and the database
volume. The frontend only receives `STAR_PASS_API_TOKEN` and
`STAR_PASS_SESSION_SECRET`.

Every container drops all Linux capabilities, has a read-only root
filesystem, and has memory and process limits. Caddy keeps
`NET_BIND_SERVICE`, and has a writable `/tmp`. The database is on the
`star_pass_data` volume.

The frontend only trusts forwarded headers from Caddy's address. The API
trusts no forwarded headers. Caddy does not pass on a request whose
`Host` header matches no configured site.

### Certificates

By default, `star-pass` is served at `https://localhost` with a
certificate from Caddy's own certificate authority, and your browser
displays a warning about it. You may accept the warning, or trust
Caddy's root certificate. To copy the root certificate out of the
`caddy` container:

```bash
docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt caddy-root.crt
```

Then add `caddy-root.crt` to your system's trusted certificates. On
macOS:

```bash
sudo security add-trusted-cert -d -r trustRoot \
  -k /Library/Keychains/System.keychain caddy-root.crt
```

To serve a different name, set `STAR_PASS_SITE_ADDRESS`. To use a
certificate from Let's Encrypt, a public certificate authority, set
`STAR_PASS_TLS` to an email address. Let's Encrypt requires a name
that resolves publicly.

HSTS is off by default. To turn it on once the site's name is final,
copy `deploy/caddy/conf.d/hsts.caddy.example` to `hsts.caddy` in the
same directory, and restart Caddy. Browsers remember HSTS, and you may
not turn it off for them afterward.

### The Credential File and the Database

Run `python3 scripts/setup_env.py` before the first `docker compose up`.
If `.env` does not exist, Docker creates a directory in its place, and
the API does not start.

The frontend and the API run as an unprivileged account, UID 1000. The
API reads `.env` through a group. `setup_env.py` writes the file with
mode `0640`, and `STAR_PASS_ENV_GID` sets the group, `1000` by default.
If `id -g` does not print `1000`, set `STAR_PASS_ENV_GID` to the value
it prints.

Docker only sets a volume's ownership when it creates the volume empty.
If the API cannot write to an existing `star_pass_data` volume, change
the volume's ownership to UID 1000, or remove the volume with
`docker compose down -v`. Removing the volume deletes the database.

## The Web UI

`web/` contains the web UI. It has no build step. The browser receives
the JavaScript modules and the CSS in that directory as they are. To
serve a different copy, set `STAR_PASS_WEB_ROOT`.

The Inter font and the Phosphor icons are served from `web/assets/`,
with their licenses. The Content-Security-Policy is
`default-src 'self'`, and the browser refuses fonts, icons, and scripts
from any other origin.

Every screen has its own address:

| Path | Screen |
| --- | --- |
| `/`, `/runs` | **Runs**, with every run's date range, counts, and status |
| `/runs/{id}` | One run's **Shifts to Create** tab |
| `/runs/{id}/uncollected` | One run's **Not Collected** tab |
| `/runs/{id}/preview` | **Preview**, the shifts that sending the run would create |
| `/settings` | **Settings** |

You may reload, bookmark, or open any screen in a second tab. Any other
path that is not a file returns 404.

While a run is being collected or sent, `/` opens that run.

The session cookie is `SameSite=Strict`. A link to `star-pass` from
another site starts a new session.

## The API Specification

The API serves its specification at three paths:

| Path | Contents |
| --- | --- |
| `/docs` | Swagger UI |
| `/redoc` | ReDoc |
| `/v1/openapi.json` | The specification |

These paths are only reachable from inside the deployment. To read
them, use `docker compose exec`, or forward a port.

The same specification is in the repository at `docs/api/openapi.json`.
To read it without a deployment:

```bash
docker run --rm -p 8080:8080 \
  -e SWAGGER_JSON=/spec/openapi.json \
  -v "$PWD/docs/api:/spec:ro" \
  swaggerapi/swagger-ui
```

Then open `http://localhost:8080`. Once Docker pulls the image, it does
not require network access.

To open `/docs` and `/redoc` directly, run the API outside the
deployment:

```bash
uvicorn --factory star_pass_api:create_app --port 8000
```

Then open `http://localhost:8000/docs`. `/docs` and `/redoc` load
Swagger UI and ReDoc from a content delivery network, and display a
blank page on a machine with no internet access. On that machine, use
the container above.
