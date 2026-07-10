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
- Set `HERMESBENCH_SUBMISSION_TOKEN` in production/preview for `/v1/results`.
- Connect a Vercel Blob store so production/preview have `BLOB_READ_WRITE_TOKEN`.

## Configuration
The main leaderboard pages use checked-in JSON under `website/data`. The committed sample set is a labeled historical mock fixture for website/pipeline development, not model-capability evidence; new public capability evidence belongs in a reviewed `official-runs/` archive. Authenticated submissions use `https://hermesbench.site/v1/results`, persist sanitized uploads to Vercel Blob, and feed the API leaderboard.

## Smoke checklist
- Landing page loads.
- Leaderboard table renders demo entries.
- Leaderboard page renders entries from the API.
- Result detail page shows task evidence and status badge.
- Methodology, tasks, and run instructions are reachable.
|- Browser upload form on /submit page lets maintainers select a scored JSON file, enter a submission token, and POST to `/v1/results` without the token being stored or logged.
|- `HERMESBENCH_SUBMISSION_TOKEN=UPLOAD_SECRET uv run hermesbench upload <result.json> --endpoint https://hermesbench.site/v1/results` returns `202` and the run appears in `GET /v1/leaderboard`.
- No private task data or local paths appear in the deployed bundle.
