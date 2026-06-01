# HermesBench API Deployment Guide

## Status

The checked-in HTTP server uses Python `wsgiref` for local development and CI smoke tests. Do **not** expose it directly to the public internet. A production deployment must provide a real application server or serverless wrapper, TLS, durable storage, observability, authentication, and edge rate limits.

## Required environment

- `HERMESBENCH_SUBMISSION_TOKEN`: shared unofficial-upload token; rotate regularly. Replace with scoped tokens/OIDC before production.
- `HERMESBENCH_STORE_PATH`: JSONL or SQLite path mounted on durable storage.
- `HERMESBENCH_CORS_ORIGINS`: allowed website origins when browser uploads are enabled.

## Storage setup

For smoke deployments use JSONL. For maintainer demos use SQLite and apply `migrations/0001_submissions.sql` if using the SQL path. Never persist `submission_token`; the API strips it before storage.

## Schema/versioning

- Result uploads must pass the `hermesbench.result.v1` validator.
- The local HTTP scaffold advertises `X-Hermesbench-Api-Schema: hermesbench.api.v0-dev` to make the dev-only contract explicit.
- Add migration notes before changing leaderboard fields consumed by `website/data/*.json`.

## Submission token policy

Tokens are for unofficial public submissions only. Keep them out of source control, rotate on disclosure, and invalidate old tokens after a migration window. Production should issue per-submitter or per-run scoped credentials and log token IDs, not raw secrets.

## CORS policy

Default to no wildcard browser writes. Allow the official website origin for `GET /health` and `GET /v1/leaderboard`; enable `POST /v1/results` only for trusted submission forms.

## Rate limiting plan

Put the service behind a reverse proxy/platform limiter. Suggested starting points:

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
