# Website deployment guide

## Build
```bash
cd website
pnpm install
pnpm build
```

## Output
Deploy `website/dist` as a static site.

## Vercel
- Root directory: `website`
- Install command: `pnpm install`
- Build command: `pnpm build`
- Output directory: `dist`
- Rewrites in `website/vercel.json` expose `/health` and `/v1/*` from the serverless functions under `website/api/`.
- Set `HERMESBENCH_SUBMISSION_TOKEN` in production/preview for the protected `/v1/results` lane. Tokenless community uploads use `/v1/community-results`.
- Connect a Vercel Blob store so production/preview have `BLOB_READ_WRITE_TOKEN`.

## Configuration
The main leaderboard pages use checked-in JSON under `website/data`. Tokenless self-serve submissions use `https://hermesbench.site/v1/community-results`, persist sanitized uploads to Vercel Blob, and appear only on the Community page. The protected maintainer lane remains `https://hermesbench.site/v1/results`.

## Smoke checklist
- Landing page loads.
- Leaderboard table renders demo entries.
- Community page renders live community entries or the empty state.
- Result detail page shows task evidence and unofficial/official badge.
- Methodology/tasks/submissions/why sections are reachable.
- `GET /health` returns `200` with `storage: "vercel-blob"` on production.
- `uv run hermesbench upload <result.json> --endpoint https://hermesbench.site/v1/community-results` returns `202` and the run appears in `GET /v1/community-leaderboard`, not `GET /v1/leaderboard`.
- `HERMESBENCH_SUBMISSION_TOKEN=UPLOAD_SECRET_FROM_MAINTAINER uv run hermesbench upload <result.json> --endpoint https://hermesbench.site/v1/results` returns `202` for the protected lane.
- No private task data or local paths appear in the deployed bundle.
