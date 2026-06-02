# API and submissions

HermesBench includes a minimal local API scaffold in `src/hermesbench/api.py`, a `wsgiref` wrapper in `src/hermesbench/http_api.py`, and Vercel serverless routes under `website/api/` for the live site.

> **Production-readiness status:** the live Vercel route accepts unofficial submissions and stores sanitized results in Vercel Blob. `wsgiref.simple_server` remains local/dev-only. Add scoped submitter tokens and edge rate limits before treating public uploads as trusted rankings.

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
    "submission_token": "anti-spam-token-placeholder",
    "results": []
  }
}
```

`metadata.official=true` is maintainer-reserved and rejected by public submissions. Accepted submissions are persisted with `submission_token` stripped.

## Current guardrails and placeholders

- **Schema:** result payloads are validated with `validate_result_schema`; website leaderboard exports are separately shape-validated during `website` build/CI.
- **Live storage:** Vercel uses `BLOB_READ_WRITE_TOKEN` and stores one sanitized JSON blob per `run_id` under `submissions/`.
- **Auth:** `submission_token` is an anti-spam placeholder for unofficial uploads only. Production should use scoped submitter tokens, signed manifests, or OIDC.
- **Rate limits:** no in-process limiter is implemented. Enforce limits at the reverse proxy/platform edge, especially for `POST /v1/results`.
- **Review workflow:** all public uploads are unofficial. Maintainers promote results only after private/fresh-pack reruns, manifest review, score hash/archive checks, and evidence retention.

This scaffold is intentionally framework-light so it can later be wrapped by FastAPI, Hono, Cloudflare Workers, or a static leaderboard ingestion job without changing the result schema.
