# CARBONWISE frontend

React + TypeScript + Vite client for the CARBONWISE Go API.

## Local development

```powershell
cd frontend
npm install
Copy-Item .env.example .env
npm run dev
```

Set `VITE_API_BASE_URL` to the Go API origin (for example,
`http://127.0.0.1:8080`). The deployed frontend origin must also be included in
the Go API's `ALLOWED_ORIGINS` setting. The client uses the API's HttpOnly
refresh cookie and never reads it from JavaScript.

Vite's development server is pinned to `http://localhost:3000` to match the Go
development example's `ALLOWED_ORIGINS` value. If that port is occupied, stop
the other process or update the local Go allowlist to the exact Vite origin;
Vite will not silently move to a different port.

### Separate-host production deployments

When the Vercel frontend and Render Go API use separate provider hostnames, the
refresh cookie is cross-site. Configure the Go service with
`APP_ENV=production`, `COOKIE_SAME_SITE=none`, and `COOKIE_SECURE=true`, and set
`ALLOWED_ORIGINS` to the exact HTTPS Vercel origin (no path). Configure the frontend's public
`VITE_API_BASE_URL` to the HTTPS Go API origin. Keep FastAPI private as described
in the Go service deployment documentation. The Go configuration explicitly
requires `COOKIE_SECURE=true` when `COOKIE_SAME_SITE=none`; do not use this
cross-site setting for local HTTP development. Browser third-party-cookie
policies may still block refresh cookies, so verify the flow in supported browsers.
