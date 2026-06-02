# API and submissions

HermesBench includes a minimal local API scaffold in `src/hermesbench/api.py`, a `wsgiref` wrapper in `src/hermesbench/http_api.py`, and Vercel serverless routes under `website/api/` for the live site.

> **Production-readiness status:** the live Vercel route requires a configured submission secret for writes, rate-limits submission IPs, and stores sanitized unofficial results in Vercel Blob. `wsgiref.simple_server` remains local/dev-only. Public uploads are still unofficial until maintainer review/private rerun.

## Endpoints

- `POST /v1/results` — validates and stores an unofficial CLI submission payload.
- `GET /v1/leaderboard` — returns scored submissions from the configured store.
- `GET /health` — health check.

HTTP responses include scaffold headers such as `X-Hermesbench-Api-Schema: hermesbench.api.v0-dev`.

## Upload payload

The CLI posts a `hermesbench.submission.v1` wrapper. The API also accepts a legacy raw `hermesbench.result.v1` object for local compatibility.

```json
{
  "schema_version": "hermesbench.submission.v1",
  "classification": "unofficial",
  "result": {
    "schema_version": "hermesbench.result.v1",
    "run_id": "abc123",
    "suite": "public-dev",
    "agent": "hermes",
    "model": "openai-codex/gpt-5.5",
    "results": []
  }
}
```

`metadata.official=true` is maintainer-reserved and rejected by public submissions. Send the write secret as `X-Hermesbench-Submission-Token` or a Bearer authorization header; accepted submissions are persisted with any `submission_token` field stripped.

## Current guardrails

- **Schema:** result payloads are validated with `validate_result_schema`; website leaderboard exports are separately shape-validated during `website` build/CI.
- **Live storage:** Vercel uses `BLOB_READ_WRITE_TOKEN` and stores one sanitized JSON blob per `run_id` under `submissions/`.
- **Auth:** live Vercel writes fail closed when `HERMESBENCH_SUBMISSION_TOKEN` is missing in production, and accept the secret via `X-Hermesbench-Submission-Token`, a Bearer authorization header, or CLI env/flag forwarding. Move to scoped submitter credentials, signed manifests, or OIDC for a larger public launch.
- **Rate limits:** `POST /v1/results` is IP-limited by `HERMESBENCH_RATE_LIMIT_MAX` per `HERMESBENCH_RATE_LIMIT_WINDOW_SECONDS` window. Vercel stores hashed-IP buckets in Blob objects; local dev uses a JSON file.
- **Review workflow:** all public uploads are unofficial. Maintainers promote results only after private/fresh-pack reruns, manifest review, score hash/archive checks, and evidence retention.

This scaffold is intentionally framework-light so it can later be wrapped by FastAPI, Hono, Cloudflare Workers, or a static leaderboard ingestion job without changing the result schema.
