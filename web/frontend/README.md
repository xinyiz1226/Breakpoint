# Breakpoint Web Frontend

Production-oriented Next.js App Router client for the Breakpoint SaaS API. It
implements secure cookie-backed authentication, project/quota management,
direct multipart object-storage uploads, authenticated SSE progress, rally
review/autosave, and immutable export jobs.

## Local development

Requirements: Node.js 22+, npm, and the FastAPI service at
`http://localhost:8000`.

```powershell
Set-Location web\frontend
Copy-Item .env.example .env.local
npm install
npm run dev
```

Open `http://localhost:3000`. Mailpit verification and reset messages are at
`http://localhost:8025` when using the Compose stack.

## Environment contract

| Variable | Required | Description |
| --- | --- | --- |
| `NEXT_PUBLIC_API_URL` | Yes in deployment | Public browser-reachable FastAPI origin, without a trailing slash. Defaults to `http://localhost:8000`. |

The API must allow the frontend origin with credentials. Its refresh cookie
must be `Secure` in HTTPS deployments and may be insecure only for local HTTP
development. S3-compatible storage must allow browser `PUT` requests from the
frontend origin and expose the `ETag` response header; multipart finalization
cannot work without that header.

## Full local stack

From `web\`, set a development JWT secret and start Compose:

```powershell
$env:BREAKPOINT_JWT_SECRET_KEY = "replace-with-a-long-random-local-secret"
docker compose up --build
```

Compose starts the frontend on port 3000, API on 8000, Mailpit on 8025, MinIO
on 9000/9001, Postgres, Redis, the Celery worker, and Beat. The included MinIO
CORS policy permits local direct multipart uploads and exposes `ETag`.

For a real deployment, set `NEXT_PUBLIC_API_URL` at image build time, configure
`BREAKPOINT_CORS_ALLOW_ORIGINS` and `BREAKPOINT_APP_BASE_URL` to the public
frontend HTTPS origin, keep `BREAKPOINT_REFRESH_COOKIE_SECURE=true`, and apply
equivalent storage CORS at the object-storage provider.

## Quality checks

```powershell
npm test
npm run typecheck
npm run lint
npm run build
```
