# HermesBench API Deployment Guide

## Status

The checked-in Python HTTP server uses `wsgiref` for local development and CI smoke tests. Do **not** expose it directly to the public internet. The live `https://hermesbench.site` API is served by Vercel functions in `website/api/` and persists sanitized submissions to Vercel Blob.

## Required environment

- `HERMESBENCH_SUBMISSION_TOKEN`: maintainer/promoted-upload token for `POST /v1/results`; required for live production writes to the protected lane.
- `HERMESBENCH_RATE_LIMIT_MAX`: max accepted writes per IP/window for submission endpoints (default `12`; set `0` only for local debugging).
- `HERMESBENCH_RATE_LIMIT_WINDOW_SECONDS`: rate-limit window length (default `600`).
- `HERMESBENCH_STORE_PATH`: local JSONL path for submissions.
- `HERMESBENCH_RATE_LIMIT_STORE_PATH`: local JSON store for dev rate buckets.
- `HERMESBENCH_CORS_ORIGINS`: allowed website origins when browser uploads are enabled.
- `BLOB_READ_WRITE_TOKEN`: Vercel Blob token for the live serverless storage path.

## Storage setup

For local smoke deployments use JSONL. The live Vercel route stores submissions under `submissions/<hash>-<run_id>.json` using a content-hash-prefixed, token-derived path that is deterministic per run_id+token but unguessable to external observers. Never persist `submission_token`; both the Python and Vercel APIs strip it before storage.

### No-overwrite semantics

Vercel Blob `allowOverwrite: false` is always set. If a blob already exists at the computed path, the API re-reads the blob and compares the stored `run_id_hash` and full body. Identical re-submissions are accepted (idempotent 202 with `duplicate: true`). Conflicting content for the same `run_id` is rejected with a 409 error.

### Fail-closed behavior

When `VERCEL=1` and `BLOB_READ_WRITE_TOKEN` is not configured (or Blob SDK is unavailable), the API returns 503. Provider credentials must never enter Vercel or GitHub — only `HERMESBENCH_SUBMISSION_TOKEN` and `BLOB_READ_WRITE_TOKEN` are set in Vercel environment secrets.

### Concurrent write race

The first-write `put()` with `allowOverwrite: false` catches `BlobPreconditionFailedError` thrown by concurrent requests. On collision, it re-reads the existing blob to check for idempotency (identical content → accepted as duplicate) or identifies a conflict (different content → 409). Non-precondition errors produce a fail-closed 503.

### Private blob support

When `HERMESBENCH_SUBMISSION_BLOB_ACCESS=private`, both submission reads (`get`) and leaderboard reads (`get`) use the SDK's authenticated path rather than raw `fetch(blob.url)`.

## Schema/versioning

- CLI uploads use `hermesbench.submission.v1` with a nested `hermesbench.result.v1`; legacy raw result uploads remain accepted locally.
- The local HTTP scaffold advertises `X-Hermesbench-Api-Schema: hermesbench.api.v0-dev` to make the dev-only contract explicit.
- Add migration notes before changing leaderboard fields consumed by `website/data/*.json`.

## Submissions

`POST /v1/results` requires `HERMESBENCH_SUBMISSION_TOKEN` in production. Use it for maintainer-reviewed/promoted submissions or internal smoke tests. Keep this token out of source control, rotate on disclosure, and avoid posting it in issues, logs, screenshots, or docs. A future larger launch should use per-submitter or per-run scoped credentials and log token IDs, not raw secrets.

## CORS policy

Default to no wildcard browser writes. Allow the official website origin for `GET /health` and `GET /v1/leaderboard`; enable browser `POST` only for trusted forms.

## Rate limiting

`POST /v1/results` enforces a per-IP write window in the API route. Tune `HERMESBENCH_RATE_LIMIT_MAX` and `HERMESBENCH_RATE_LIMIT_WINDOW_SECONDS` in the deployment environment; the current default is 12 accepted writes per 10 minutes. Vercel stores hashed-IP buckets under `ratelimits/`, while local/dev runs use `HERMESBENCH_RATE_LIMIT_STORE_PATH`.

Keep platform/body-size limits enabled too:

- `POST /v1/results`: low burst, per token/IP, with body-size caps.
- `GET /v1/leaderboard`: cache at the edge and allow higher read rates.
- Rejected validation/auth attempts: log and alert on spikes.

## Official-run admin process

Official results are not accepted through public upload. Maintainers run private/fresh packs, create an official manifest, review score hashes and evidence archives, and publish only approved outputs. Public uploads that set `metadata.official=true` are rejected.

## Token rotation

1. Generate a new token in the deployment secret manager.
2. Deploy/restart the API.
3. Update internal maintainer tooling if needed.
4. Remove the old token and audit logs for rejected attempts.
