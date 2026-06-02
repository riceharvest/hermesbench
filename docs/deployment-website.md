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
- Connect a Vercel Blob store so production/preview have `BLOB_READ_WRITE_TOKEN`.

## Configuration
The visible leaderboard pages use checked-in JSON under `website/data`. The submission API uses `https://hermesbench.site/v1/results` and persists sanitized unofficial uploads to Vercel Blob. Static fallback should remain available when the API is unavailable.

## Smoke checklist
- Landing page loads.
- Leaderboard table renders demo entries.
- Result detail page shows task evidence and unofficial/official badge.
- Methodology/tasks/submissions/why sections are reachable.
- `GET /health` returns `200` with `storage: "vercel-blob"` on production.
- `uv run hermesbench upload <result.json> --endpoint https://hermesbench.site/v1/results` returns `202` and the run appears in `GET /v1/leaderboard`.
- No private task data or local paths appear in the deployed bundle.
