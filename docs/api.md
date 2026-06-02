# API and submissions

HermesBench includes a minimal local API scaffold in `src/hermesbench/api.py`, a `wsgiref` wrapper in `src/hermesbench/http_api.py`, and Vercel serverless routes under `website/api/` for the live site.

> **Production-readiness status:** the live site has two write lanes: tokenless community uploads for self-serve public-suite comparisons, and a protected maintainer lane for promoted/official-style submissions. `wsgiref.simple_server` remains local/dev-only.

## Endpoints

- `POST /v1/community-results` — tokenless self-serve community upload. Stored separately and never used for the main leaderboard.
- `GET /v1/community-leaderboard` — returns scored community submissions from the community store.
- `POST /v1/results` — protected maintainer/promoted submission path requiring `HERMESBENCH_SUBMISSION_TOKEN` in production.
- `GET /v1/leaderboard` — returns scored protected submissions from the configured store.
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

`metadata.official=true` is maintainer-reserved and rejected by both public write paths. Accepted submissions are persisted with any `submission_token` field stripped.

## Current guardrails

- **Schema:** result payloads are validated with `validate_result_schema`; website leaderboard exports are separately shape-validated during `website` build/CI.
- **Community storage:** Vercel stores tokenless community uploads under `community-submissions/`. These appear on the Community page only.
- **Protected storage:** Vercel stores maintainer/promoted uploads under `submissions/`. These feed the protected API leaderboard, not the static official archive.
- **Auth:** `/v1/results` fails closed when `HERMESBENCH_SUBMISSION_TOKEN` is missing in production, and accepts the secret via `X-Hermesbench-Submission-Token`, a Bearer authorization header, or CLI env/flag forwarding.
- **Rate limits:** `POST /v1/community-results` and `POST /v1/results` are IP-limited by `HERMESBENCH_RATE_LIMIT_MAX` per `HERMESBENCH_RATE_LIMIT_WINDOW_SECONDS` window. Vercel stores hashed-IP buckets in Blob objects; local dev uses a JSON file.
- **Review workflow:** community uploads are unofficial and self-reported. Maintainers promote results only after private/fresh-pack reruns, manifest review, score hash/archive checks, and evidence retention.

This scaffold is intentionally framework-light so it can later be wrapped by FastAPI, Hono, Cloudflare Workers, or a static leaderboard ingestion job without changing the result schema.
