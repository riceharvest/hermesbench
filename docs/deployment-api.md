# HermesBench API Deployment Guide

## Status

The checked-in Python HTTP server uses `wsgiref` for local development and CI smoke tests. Do **not** expose it directly to the public internet. The live `https://hermesbench.site` API is served by Vercel functions in `website/api/` and persists sanitized unofficial submissions to Vercel Blob.

## Required environment

- `HERMESBENCH_SUBMISSION_TOKEN`: shared unofficial-upload token; required for live production writes and rotated regularly. Replace with scoped tokens/OIDC before a larger public launch.
- `HERMESBENCH_RATE_LIMIT_MAX`: max accepted writes per IP/window for `POST /v1/results` (default `12`; set `0` only for local debugging).
- `HERMESBENCH_RATE_LIMIT_WINDOW_SECONDS`: rate-limit window length (default `600`).
- `HERMESBENCH_RATE_LIMIT_STORE_PATH`: local JSON store for dev rate buckets; Vercel uses private Blob objects instead.
- `HERMESBENCH_STORE_PATH`: JSONL or SQLite path mounted on durable storage.
- `HERMESBENCH_CORS_ORIGINS`: allowed website origins when browser uploads are enabled.
- `BLOB_READ_WRITE_TOKEN`: Vercel Blob token for the live serverless storage path.

## Storage setup

For local smoke deployments use JSONL. For maintainer demos use SQLite and apply `migrations/0001_submissions.sql` if using the SQL path. The live Vercel route stores one sanitized JSON blob per run under `submissions/<run_id>.json`. Never persist `submission_token`; both the Python and Vercel APIs strip it before storage.

## Schema/versioning

- CLI uploads use `hermesbench.submission.v1` with a nested `hermesbench.result.v1`; legacy raw result uploads remain accepted locally.
- The local HTTP scaffold advertises `X-Hermesbench-Api-Schema: hermesbench.api.v0-dev` to make the dev-only contract explicit.
- Add migration notes before changing leaderboard fields consumed by `website/data/*.json`.

## Submission token policy

Tokens are for unofficial public submissions only. Keep them out of source control, rotate on disclosure, and invalidate old tokens after a migration window. Production should issue per-submitter or per-run scoped credentials and log token IDs, not raw secrets.

## CORS policy

Default to no wildcard browser writes. Allow the official website origin for `GET /health` and `GET /v1/leaderboard`; enable `POST /v1/results` only for trusted submission forms.

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
3. Announce cutoff for old submitters if needed.
4. Remove the old token and audit logs for rejected attempts.
