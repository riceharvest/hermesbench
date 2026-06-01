# HermesBench API Deployment Guide

## Required environment

- `HERMESBENCH_SUBMISSION_TOKEN`: shared public upload token; rotate regularly.
- `HERMESBENCH_STORE_PATH`: JSONL or SQLite path mounted on durable storage.
- `HERMESBENCH_CORS_ORIGINS`: allowed website origins when browser uploads are enabled.

## Storage setup

For smoke deployments use JSONL. For maintainer demos use SQLite and apply `migrations/0001_submissions.sql`. Never persist `submission_token`; the API strips it before storage.

## Submission token policy

Tokens are for unofficial public submissions only. Keep them out of source control, rotate on disclosure, and invalidate old tokens after a migration window.

## CORS policy

Default to no wildcard browser writes. Allow the official website origin for `GET /health` and `GET /v1/leaderboard`; enable `POST /v1/results` only for trusted submission forms.

## Rate limiting plan

Put the service behind a reverse proxy/platform limiter. Apply stricter limits to `POST /v1/results` than leaderboard reads.

## Official-run admin process

Official results are not accepted through public upload. Maintainers run private/fresh packs, create an official manifest, and archive with `hermesbench archive-official`. Public uploads that set `metadata.official=true` are rejected.

## Token rotation

1. Generate a new token in the deployment secret manager.
2. Deploy/restart the API.
3. Announce cutoff for old submitters if needed.
4. Remove the old token and audit logs for rejected attempts.
