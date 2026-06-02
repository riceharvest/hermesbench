# HermesBench API Deployment Guide

## Status

The checked-in Python HTTP server uses `wsgiref` for local development and CI smoke tests. Do **not** expose it directly to the public internet. The live `https://hermesbench.site` API is served by Vercel functions in `website/api/` and persists sanitized submissions to Vercel Blob.

## Required environment

- `HERMESBENCH_SUBMISSION_TOKEN`: maintainer/promoted-upload token for `POST /v1/results`; required for live production writes to the protected lane.
- `HERMESBENCH_RATE_LIMIT_MAX`: max accepted writes per IP/window for submission endpoints (default `12`; set `0` only for local debugging).
- `HERMESBENCH_RATE_LIMIT_WINDOW_SECONDS`: rate-limit window length (default `600`).
- `HERMESBENCH_RATE_LIMIT_STORE_PATH`: local JSON store for dev rate buckets; Vercel uses Blob objects instead.
- `HERMESBENCH_STORE_PATH`: local JSONL path for protected submissions.
- `HERMESBENCH_COMMUNITY_STORE_PATH`: local JSONL path for community submissions.
- `HERMESBENCH_CORS_ORIGINS`: allowed website origins when browser uploads are enabled.
- `BLOB_READ_WRITE_TOKEN`: Vercel Blob token for the live serverless storage path.

## Storage setup

For local smoke deployments use JSONL. The live Vercel route stores protected submissions under `submissions/<run_id>.json` and tokenless community submissions under `community-submissions/<run_id>.json`. Never persist `submission_token`; both the Python and Vercel APIs strip it before storage.

## Schema/versioning

- CLI uploads use `hermesbench.submission.v1` with a nested `hermesbench.result.v1`; legacy raw result uploads remain accepted locally.
- The local HTTP scaffold advertises `X-Hermesbench-Api-Schema: hermesbench.api.v0-dev` to make the dev-only contract explicit.
- Add migration notes before changing leaderboard fields consumed by `website/data/*.json`.

## Submission lanes

### Community lane

`POST /v1/community-results` is self-serve and tokenless. It exists so people can run public suites without maintainer involvement. Rows appear only on the Community page and `GET /v1/community-leaderboard`; they never enter the main leaderboard.

### Protected/promoted lane

`POST /v1/results` requires `HERMESBENCH_SUBMISSION_TOKEN` in production. Use it for maintainer-reviewed/promoted submissions or internal smoke tests. Keep this token out of source control, rotate on disclosure, and avoid posting it in issues, logs, screenshots, or docs. A future larger launch should use per-submitter or per-run scoped credentials and log token IDs, not raw secrets.

## CORS policy

Default to no wildcard browser writes. Allow the official website origin for `GET /health`, `GET /v1/leaderboard`, and `GET /v1/community-leaderboard`; enable browser `POST` only for trusted forms.

## Rate limiting

`POST /v1/community-results` and `POST /v1/results` enforce a per-IP write window in the API route. Tune `HERMESBENCH_RATE_LIMIT_MAX` and `HERMESBENCH_RATE_LIMIT_WINDOW_SECONDS` in the deployment environment; the current default is 12 accepted writes per 10 minutes. Vercel stores hashed-IP buckets under `ratelimits/`, while local/dev runs use `HERMESBENCH_RATE_LIMIT_STORE_PATH`.

Keep platform/body-size limits enabled too:

- `POST /v1/community-results`: low burst, per IP, with body-size caps.
- `POST /v1/results`: low burst, per token/IP, with body-size caps.
- `GET /v1/leaderboard` and `GET /v1/community-leaderboard`: cache at the edge and allow higher read rates.
- Rejected validation/auth attempts: log and alert on spikes.

## Official-run admin process

Official results are not accepted through tokenless public upload. Maintainers run private/fresh packs, create an official manifest, review score hashes and evidence archives, and publish only approved outputs. Public uploads that set `metadata.official=true` are rejected.

## Token rotation

1. Generate a new token in the deployment secret manager.
2. Deploy/restart the API.
3. Update internal maintainer tooling if needed.
4. Remove the old token and audit logs for rejected attempts.
