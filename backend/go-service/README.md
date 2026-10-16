# CARBONWISE Go API

The supplied Compose file is a local-development stack, not a production deployment.
Production requires an HTTPS ingress to Go, private FastAPI and PostgreSQL networking,
externally managed secrets, and database backups/recovery. Those infrastructure controls
are not implemented by this repository.

This service provides authenticated accounts and calculation history. It delegates every
emissions calculation to the existing FastAPI endpoint at `POST /api/v1/calculate`; FastAPI
remains the calculation source of truth. The Go API does not protect direct access to FastAPI,
so deploy FastAPI on a private network or restrict its ingress at the network/proxy layer.

## Requirements and local start

Use Go 1.24 or newer and Docker Compose. The recommended local path is the
containerized stack from this directory:

```powershell
docker compose config --quiet
docker compose up --build -d
docker compose ps
```

Set `JWT_SECRET` in the current shell to a private random value of at least 32 characters.
The example secret and PostgreSQL password are for local development only. The service loads
environment variables directly; it does not read `.env` automatically. For PowerShell:

```powershell
$env:DATABASE_URL = "postgres://carbonwise:local-development-only@127.0.0.1:5433/carbonwise?sslmode=disable"
$env:JWT_SECRET = "replace-this-with-a-private-random-secret-value"
$env:FASTAPI_URL = "http://127.0.0.1:8000"
go run ./cmd/api
```

For manual, non-containerized development, start FastAPI separately from `backend/`:

```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

At startup the Go service pings PostgreSQL and applies ordered SQL files in
`internal/store/migrations/` transactionally. `GET /health` is a liveness check and
`GET /readyz` checks the database. Do not expose port 5433 outside a development machine.

Compose uses `postgres:5432` and `http://fastapi:8000` for internal service URLs and publishes
development-only host ports 5433, 8000, and 8080 on loopback. PostgreSQL and FastAPI healthchecks
must pass before Compose starts Go. The Go container applies the embedded migrations at startup.
Check the stack with:

```powershell
docker compose ps
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8080/health
Invoke-RestMethod http://127.0.0.1:8080/readyz
```

Stop normally with `docker compose down`; this preserves the named PostgreSQL volume. Use
`docker compose down -v` only for intentional deletion of all local development data.

## Configuration

| Variable | Required | Default / purpose |
|---|---:|---|
| `APP_ENV` | No | `development`; production requires secure cookies and allowed origins |
| `LISTEN_ADDRESS` | No | `:8080` |
| `DATABASE_URL` | Yes | PostgreSQL connection URL |
| `JWT_SECRET` | Yes | HMAC secret, at least 32 characters; keep private |
| `JWT_ISSUER`, `JWT_AUDIENCE` | No | `carbonwise-go-api`, `carbonwise-client` |
| `ACCESS_TOKEN_TTL`, `REFRESH_TOKEN_TTL` | No | `15m`, `720h` |
| `FASTAPI_URL` | No | `http://127.0.0.1:8000` |
| `REFRESH_COOKIE_NAME` | No | `carbonwise_refresh` |
| `COOKIE_DOMAIN` | No | Host-only cookie when empty |
| `COOKIE_SECURE` | No | `true`; set `false` only for local HTTP development |
| `COOKIE_SAME_SITE` | No | `lax`; `none` requires secure cookies |
| `ALLOWED_ORIGINS` | Production | Comma-separated exact browser origins; refresh/logout validate Origin |
| `DB_MAX_OPEN_CONNS`, `DB_MAX_IDLE_CONNS` | No | `20`, `5` |

Compose supplies `DATABASE_URL` and `FASTAPI_URL` using internal service names. If a database
password contains URL-reserved characters, provide a complete URL through the Compose
`DATABASE_URL` override instead of relying on the interpolated default. Compose's default
PostgreSQL password and JWT secret are for local development only; override them before
sharing the stack or deploying it.

In production, terminate TLS at a trusted reverse proxy, set `COOKIE_SECURE=true`, configure
exact `ALLOWED_ORIGINS`, and use a private database and FastAPI network. The in-memory login
and registration rate limiter is per process and uses the direct network peer address. When
the service sits behind a reverse proxy, requests may share the proxy address; use a trusted
gateway rate limiter for client-specific limits across replicas. Forwarded IP headers are not
trusted by this service.

## API

Authentication responses contain a short-lived bearer access token. The refresh token is only
sent in an HttpOnly cookie. Browser refresh and logout requests must include credentials and
come from a configured origin. Do not put the refresh token in JavaScript storage.

```powershell
# Register. Save the access_token from the response; the refresh cookie is returned separately.
$register = Invoke-WebRequest -Method Post http://127.0.0.1:8080/api/auth/register `
  -ContentType 'application/json' -Body '{"email":"user@example.com","password":"a-long-local-password"}' -SessionVariable session
$access = ($register.Content | ConvertFrom-Json).access_token

# Current user
Invoke-RestMethod http://127.0.0.1:8080/api/auth/me -Headers @{ Authorization = "Bearer $access" }

# Calculate and persist the FastAPI response
$saved = Invoke-RestMethod -Method Post http://127.0.0.1:8080/api/calculations `
  -Headers @{ Authorization = "Bearer $access" } -ContentType 'application/json' `
  -Body '{"electricity_kwh_per_month":150,"lpg_kg_per_month":14.2}'

# List history, then fetch an owned calculation
Invoke-RestMethod 'http://127.0.0.1:8080/api/calculations?limit=20&offset=0' -Headers @{ Authorization = "Bearer $access" }
Invoke-RestMethod "http://127.0.0.1:8080/api/calculations/$($saved.id)" -Headers @{ Authorization = "Bearer $access" }

# Rotate the HttpOnly cookie; cookie is not copied into the JavaScript-visible response.
Invoke-WebRequest -Method Post http://127.0.0.1:8080/api/auth/refresh -WebSession $session
Invoke-WebRequest -Method Post http://127.0.0.1:8080/api/auth/logout -WebSession $session
```

Routes: `POST /api/auth/register`, `/login`, `/refresh`, `/logout`; `GET /api/auth/me`;
`POST /api/calculations`; `GET /api/calculations?limit=20&offset=0` and
`GET /api/calculations/{uuid}`. History is always scoped to the bearer-token user, ordered
by `created_at DESC, id DESC`. Pagination allows limits 1–100. The API stores the exact
validated request snapshot, full upstream response snapshot, and numeric total. It saves no
calculation if FastAPI returns an error, times out, or responds with an invalid contract.

## Verification

### Containerized smoke test

With the stack running, inspect health and recent logs:

```powershell
docker compose ps
docker compose logs --tail 100 postgres fastapi go-api
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8080/health
Invoke-RestMethod http://127.0.0.1:8080/readyz
```

The Go `/readyz` endpoint verifies PostgreSQL. Compose startup ordering separately verifies
FastAPI's `/health`; it does not make FastAPI public in a production deployment, where it should
remain on a private network.

Run Go unit and HTTP tests with `go test ./...`. Run PostgreSQL repository/migration tests
against a dedicated, disposable PostgreSQL database (the test applies migrations and creates
and removes uniquely named rows):

```powershell
docker compose up -d postgres
docker compose exec -T postgres createdb -U carbonwise carbonwise_test
$env:CARBONWISE_TEST_DATABASE_URL = "postgres://carbonwise:local-development-only@127.0.0.1:5433/carbonwise_test?sslmode=disable"
go test ./internal/store -run TestPostgres -v
go test ./internal/httpapi -run TestPostgres -v
```

The named test database is separate from the local application database. Create it once per
PostgreSQL volume; the integration tests apply migrations idempotently and remove their test
users (and dependent rows). The integration tests are skipped when
`CARBONWISE_TEST_DATABASE_URL` is unset. For a full local E2E run, point `DATABASE_URL` at
that same disposable test database while starting Go, and start FastAPI separately as shown
above. Do not point test variables at production or private survey databases.

Troubleshooting:

- If Go exits with a database or JWT configuration error, inspect `docker compose config` and
  verify local `.env` or shell overrides.
- If Go reports `database unavailable`, inspect `docker compose logs postgres`; do not delete the
  volume as a first response.
- If calculations return `502 CALCULATOR_UNAVAILABLE`, inspect `docker compose logs fastapi go-api`
  and verify the FastAPI health endpoint.
- Use a separate test database for disposable integration tests; do not reset the normal
  `carbonwise-postgres` volume.
