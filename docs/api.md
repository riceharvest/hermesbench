# API and submissions

HermesBench includes a minimal local API scaffold in `src/hermesbench/api.py`.

## Endpoints

- `POST /v1/results` — validates and stores a result payload.
- `GET /v1/leaderboard` — returns scored submissions from the local JSONL store.
- `GET /health` — health check.

## Upload payload

The body is a `hermesbench.result.v1` object plus optional submission metadata:

```json
{
  "schema_version": "hermesbench.result.v1",
  "run_id": "abc123",
  "suite": "public-dev",
  "agent": "hermes",
  "model": "openai-codex/gpt-5.5",
  "submission_token": "anti-spam-token-placeholder",
  "submitter": {"name": "runner name"},
  "results": []
}
```

`metadata.official=true` is maintainer-reserved and rejected by public submissions. Accepted submissions are persisted as JSONL with the token stripped.

This scaffold is intentionally framework-light so it can be wrapped later by Hono, FastAPI, Cloudflare Workers, or a static leaderboard ingestion job without changing the result schema.
