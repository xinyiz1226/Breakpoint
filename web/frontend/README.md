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
| `BREAKPOINT_S3_BROWSER_ENDPOINT_URL` | Yes when API and browser use different storage hosts | Browser-reachable S3/MinIO origin used by the API while generating signatures. Compose defaults to `http://localhost:9000`; do not rewrite signed URLs after generation. |
| `BREAKPOINT_UPLOAD_PART_PRESIGNED_URL_TTL_SECONDS` | No | Multipart-part URL lifetime. Defaults to 86400 seconds and is capped by the remaining 24-hour upload session; short playback/download URLs keep their separate one-hour default. |

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
on 9000/9001, Postgres, Redis, the Celery worker, and Beat. The MinIO API CORS
configuration permits local direct multipart uploads and exposes `ETag`.

For a real deployment, set `NEXT_PUBLIC_API_URL` at image build time, configure
`BREAKPOINT_CORS_ALLOW_ORIGINS` and `BREAKPOINT_APP_BASE_URL` to the public
frontend HTTPS origin, keep `BREAKPOINT_REFRESH_COOKIE_SECURE=true`, and apply
equivalent storage CORS at the object-storage provider.
Keep `BREAKPOINT_S3_ENDPOINT_URL` pointed at the API/worker network endpoint
(for Compose, `http://minio:9000`) and set
`BREAKPOINT_S3_BROWSER_ENDPOINT_URL` to the browser-reachable storage origin.
Keep the upload-part TTL at least as long as the multipart session so uploads
can resume for the full session without URL renewal.

## Quality checks

```powershell
npm test
npm run typecheck
npm run lint
npm run build
```
