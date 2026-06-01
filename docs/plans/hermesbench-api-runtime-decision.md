# HermesBench API Runtime Decision

## Constraints

- `src/hermesbench/api.py` remains the canonical submission validation/scoring-adapter layer.
- Public uploads must never set `metadata.official=true`.
- `submission_token` may be accepted for authentication but must not be persisted.
- Dependencies should stay lightweight until a hosted production API requires more.

## Candidates

- FastAPI/Starlette: mature, but adds dependencies before they are necessary.
- Cloudflare Worker/Hono: simple deployment, but risks duplicating Python validation.
- Python stdlib WSGI wrapper: tiny, testable, keeps validation in-process.

## Selected runtime

Use a Python stdlib WSGI-compatible wrapper in `src/hermesbench/http_api.py` around `HermesBenchAPI`. It exposes a testable `request()` method and can be served with `wsgiref` for demos. A future ASGI/FastAPI adapter can wrap the same core API.

## Persistence strategy

Keep JSONL as the default public smoke-test store and add SQLite storage/migration support for deployable maintainer demos. SQLite schema mirrors fields that can later move to Postgres.

## Deployment target

Initial target is a maintainer-operated Python service behind a reverse proxy or platform HTTP service, with `HERMESBENCH_SUBMISSION_TOKEN` configured outside source control.

## Migration path

1. Start with stdlib WSGI + JSONL/SQLite.
2. If traffic or auth requirements grow, introduce FastAPI without changing `src/hermesbench/api.py` behavior.
3. Move SQLite schema to Postgres-compatible migrations when official leaderboard traffic requires it.
