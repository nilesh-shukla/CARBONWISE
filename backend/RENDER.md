# Render deployment preparation

This document prepares the existing backend for a manual Render deployment. It does not
provision Render resources, connect to Neon, run migrations, or claim that production
infrastructure is configured.

## Intended topology

```text
HTTPS client
    |
    v
Render public Web Service: Go + Chi API
    |
    +--> Render private service: FastAPI calculator
    |
    +--> Neon PostgreSQL (external, TLS connection)
```

Only the Go service should be public. FastAPI is unauthenticated by design and must be
created as a Render private service with no public ingress. Neon remains external; configure
its connection string manually as a secret in the Go service. Do not put the Neon URL in
this repository, a Blueprint, an image, or generated configuration.

## Services

Create both services from the repository's existing Dockerfiles:

| Render service | Type | Dockerfile | Docker context | Health check |
|---|---|---|---|---|
| `carbonwise-api` | Public Web Service | `backend/go-service/Dockerfile` | `backend/go-service` | `/health` |
| `carbonwise-fastapi` | Private Service | `backend/Dockerfile` | `backend` | `/health` |

Use the same Render region for both services. Render supplies `PORT`; the container images
now honor it while preserving local defaults of `8080` for Go and `8000` for FastAPI.
The Go service binds to `:PORT` when `LISTEN_ADDRESS` is not explicitly set.

Do not expose the FastAPI service publicly. Set the Go service's `FASTAPI_URL` to the
private service URL shown by Render, using the private hostname and port assigned by Render.
Do not guess or commit that URL.

## Go service environment variables

Set these in the `carbonwise-api` Render dashboard. Values marked **secret** must be entered
as secret environment variables and must never be committed or printed.

| Variable | Value |
|---|---|
| `APP_ENV` | `production` |
| `DATABASE_URL` | **secret**: existing Neon PostgreSQL connection string |
| `JWT_SECRET` | **secret**: new random value with at least 32 characters; do not reuse the local fallback |
| `JWT_ISSUER` | `carbonwise-go-api` or an explicitly chosen stable issuer |
| `JWT_AUDIENCE` | `carbonwise-client` or the configured client audience |
| `FASTAPI_URL` | **manual private Render URL** for `carbonwise-fastapi` |
| `COOKIE_SECURE` | `true` |
| `COOKIE_SAME_SITE` | `lax` |
| `ALLOWED_ORIGINS` | Exact HTTPS browser origin(s), comma-separated; no wildcard |
| `ACCESS_TOKEN_TTL` | `15m` or shorter |
| `REFRESH_TOKEN_TTL` | `720h` unless the deployment requires a shorter policy |
| `DB_MAX_OPEN_CONNS` | Start with a conservative value appropriate for the Neon plan |
| `DB_MAX_IDLE_CONNS` | Less than or equal to `DB_MAX_OPEN_CONNS` |

Leave `LISTEN_ADDRESS` unset so Render's injected `PORT` is used. If Render requires an
explicit listen setting for a service, set it to the numeric port shown in that service's
environment; do not use a public FastAPI address.

The Go production configuration rejects missing or development secrets, insecure cookies,
non-HTTPS/wildcard origins, excessive access-token TTLs, development database credentials,
and PostgreSQL URLs without TLS.

## FastAPI private-service environment variables

Set these in the `carbonwise-fastapi` Render dashboard:

| Variable | Value |
|---|---|
| `APP_ENV` | `production` |
| `DEBUG` | `false` |
| `HOST` | `0.0.0.0` |
| `PORT` | Leave Render's injected value unless the service requires an explicit port |
| `FACTORS_FILE_PATH` | `data/emission_factors/factors.yaml` |

FastAPI has no database or authentication dependency. Its factors file is copied by the
existing Dockerfile. Keep its service private because the calculator endpoint is not an
authenticated public API.

## Neon compatibility and connection policy

The existing Go service uses `github.com/jackc/pgx/v5/stdlib` with `database/sql`; Neon
PostgreSQL URLs using the standard `postgresql://` or `postgres://` format are supported.
Production validation requires a non-development database user/password and
`sslmode=require`, `verify-ca`, or `verify-full`. Keep the TLS query parameter from the
Neon connection string; never change it to `disable`.

The application already maintains a `database/sql` pool using `DB_MAX_OPEN_CONNS`,
`DB_MAX_IDLE_CONNS`, and a five-minute connection lifetime. Prefer Neon's **direct**
connection string for this long-lived Render service initially: startup migrations acquire
a dedicated connection and hold a PostgreSQL session-level advisory lock while applying
embedded migrations. Do not switch to a pooled/PgBouncer endpoint without validating that
the endpoint preserves this migration-lock behavior and supports the service's transaction
patterns. Pool sizing must remain within the Neon plan's connection limit; reduce
`DB_MAX_OPEN_CONNS` if the chosen plan has a small limit.

The Go process pings the database and applies the existing embedded migrations before it
starts listening. This behavior is unchanged. Do not run the migration code against the
existing Neon database as part of deployment preparation; review and schedule that
operation separately with a backup/recovery plan.

## Manual deployment and verification

1. Push the repository to the Render-connected Git branch.
2. Create the private FastAPI service from `backend/Dockerfile`.
3. Create the public Go Web Service from `backend/go-service/Dockerfile`.
4. Set the dashboard environment variables above. Paste the existing Neon URL only into
   Render's secret `DATABASE_URL` field.
5. Set `FASTAPI_URL` only after Render displays the private FastAPI service address.
6. Configure the Go service health check as `GET /health`.
7. Deploy the FastAPI service first, then the Go service. The Go service will not become
   ready until it can connect to Neon and complete its startup migration check.
8. Verify `/health` and `/readyz` on the Go public URL, then exercise registration,
   authentication, calculation, history ownership, refresh rotation, and logout with
   synthetic data only.

Do not use the local Compose defaults, local JWT fallback, development database credentials,
or `sslmode=disable` in Render.

## Current blockers and operational follow-up

This repository does not implement TLS ingress configuration, managed secret rotation,
Neon backups/point-in-time recovery, Render infrastructure-as-code, centralized logs,
multi-instance rate limiting, or a separate migration job. These remain deployment
responsibilities and must be addressed before treating the service as production-ready.
