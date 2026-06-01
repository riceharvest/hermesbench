# API and submissions

HermesBench includes a minimal local API scaffold in `src/hermesbench/api.py` and a `wsgiref` wrapper in `src/hermesbench/http_api.py`.

> **Production-readiness status:** this is a development/local ingestion scaffold, not an internet-facing production service. `wsgiref.simple_server` is single-process and dev-only. Put any deployment behind a real WSGI/ASGI server or platform gateway, durable storage, TLS, auth, and rate limiting.

## Endpoints

- `POST /v1/results` — validates and stores an unofficial result payload.
- `GET /v1/leaderboard` — returns scored submissions from the local JSONL store.
- `GET /health` — health check.

HTTP responses include scaffold headers such as `X-Hermesbench-Api-Schema: hermesbench.api.v0-dev` and `X-Hermesbench-Dev-Only: true` when served through the local wrapper.

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

`metadata.official=true` is maintainer-reserved and rejected by public submissions. Accepted submissions are persisted with `submission_token` stripped.

## Current guardrails and placeholders

- **Schema:** result payloads are validated with `validate_result_schema`; website leaderboard exports are separately shape-validated during `website` build/CI.
- **Auth:** `submission_token` is an anti-spam placeholder for unofficial uploads only. Production should use scoped submitter tokens, signed manifests, or OIDC.
- **Rate limits:** no in-process limiter is implemented. Enforce limits at the reverse proxy/platform edge, especially for `POST /v1/results`.
- **Review workflow:** all public uploads are unofficial. Maintainers promote results only after private/fresh-pack reruns, manifest review, score hash/archive checks, and evidence retention.

This scaffold is intentionally framework-light so it can later be wrapped by FastAPI, Hono, Cloudflare Workers, or a static leaderboard ingestion job without changing the result schema.
