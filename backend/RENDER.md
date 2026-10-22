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
| `carbonwise-api` | Public Web Service | `backend/go-service/Dockerfile` | `backend/go-service` | `/readyz` |
| `carbonwise-fastapi` | Private Service | `backend/Dockerfile` | `backend` | Render default TCP check |

Render supports configurable HTTP health checks for Web Services; Private Services use
Render's default TCP check. The FastAPI image also defines a Docker `HEALTHCHECK` for its
`/health` route, but do not treat that as a configurable Render HTTP check for the private
service. The application route remains useful for manual or in-network diagnostics.

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
| `COOKIE_SAME_SITE` | `none` when the Vercel frontend and Render API use separate provider hostnames |
| `ALLOWED_ORIGINS` | Exact deployed HTTPS frontend origin(s), comma-separated; no wildcard |
| `ACCESS_TOKEN_TTL` | `15m` or shorter |
| `REFRESH_TOKEN_TTL` | `720h` unless the deployment requires a shorter policy |
| `DB_MAX_OPEN_CONNS` | Start with a conservative value appropriate for the Neon plan |
| `DB_MAX_IDLE_CONNS` | Less than or equal to `DB_MAX_OPEN_CONNS` |

Leave `LISTEN_ADDRESS` unset so Render's injected `PORT` is used. If Render requires an
explicit listen setting, use a listen address such as `:10000` with the port shown in that
service's environment; a numeric port alone is invalid. Do not use a public FastAPI address.

The Go production configuration rejects missing or development secrets, insecure cookies,
non-HTTPS/wildcard origins, excessive access-token TTLs, development database credentials,
and PostgreSQL URLs without TLS.

For the separate Vercel and Render hostnames in this deployment topology, the browser's
refresh request is cross-site. Set `COOKIE_SAME_SITE=none` together with
`COOKIE_SECURE=true`, and restrict `ALLOWED_ORIGINS` to the exact deployed HTTPS frontend
origin(s), with no path or wildcard. Go rejects `SameSite=None` unless the cookie is Secure,
and production validation rejects non-HTTPS or wildcard origins. Browser third-party-cookie
policies can still prevent refresh; verify the flow in supported browsers. Do not loosen the
origin list or use this cookie policy for local HTTP development.

## FastAPI private-service environment variables

Set these in the `carbonwise-fastapi` Render dashboard:

| Variable | Value |
|---|---|
| `APP_ENV` | `production` |
| `DEBUG` | `false` |
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
starts listening. If configuration, database connectivity, or a migration fails, startup
logs an error and exits before opening the HTTP listener. Do not run the migration code
against Neon as part of deployment preparation; review and schedule that operation separately
with an approved backup and recovery plan.

### Migration 001 safety and recovery

`001_initial.sql` creates the `users`, `refresh_sessions`, and `calculations` tables and
their indexes. It is suitable for a fresh empty database. The migration runner records
applied versions in `schema_migrations`; a recorded `001_initial` is skipped on subsequent
starts. If the tables already exist but the migration ledger does not record this version,
the plain `CREATE TABLE` statements can fail. The migration is therefore not a general
adoption migration for an existing schema or an unknown database state. Inspect the schema
and ledger and test against a disposable clone before considering any existing database.

The runner holds a PostgreSQL advisory lock and executes each migration's SQL statements and
its ledger insert in one transaction. If a statement fails, it rolls back that transaction;
the ledger insert is not committed, and startup exits. `schema_migrations` creation itself is
outside that transaction and may remain after failure. If the connection is lost during
commit, inspect the migration ledger and schema before retrying because the commit outcome may
not be known to the client. The current migration has no down migration. Do not manually
drop tables, edit the ledger, or attempt a schema rollback as a recovery shortcut.

Before applying migrations to any database with valuable data, take and verify a recoverable
backup/snapshot, confirm the target and current schema/ledger, and rehearse the operation and
restore procedure on a disposable copy. Keep a known-good application release available;
rolling back application code does not reverse database changes. If migration outcome or
schema state is uncertain, stop and use the database provider's documented restore process
with an authorized operator rather than improvising SQL rollback steps.

## Manual deployment and verification

1. Push the repository to the Render-connected Git branch.
2. Create the private FastAPI service from `backend/Dockerfile`.
3. Create the public Go Web Service from `backend/go-service/Dockerfile`.
4. Set the dashboard environment variables above. Paste the existing Neon URL only into
   Render's secret `DATABASE_URL` field.
5. Set `FASTAPI_URL` only after Render displays the private FastAPI service address.
6. Configure the Go Web Service HTTP health check as `GET /readyz` to gate traffic on database
   readiness. `/health` is a liveness-only check and can remain successful while PostgreSQL is
   unavailable; choosing `/readyz` means a sustained database outage can make the instance
   unhealthy and trigger Render's health-check handling. The private FastAPI service uses
   Render's TCP check.
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
