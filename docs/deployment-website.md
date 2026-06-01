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

## Configuration
The v0.1 site uses checked-in JSON under `website/data`. Future API-backed deployments may set `HERMESBENCH_API_URL`; static fallback should remain available when the API is unavailable.

## Smoke checklist
- Landing page loads.
- Leaderboard table renders demo entries.
- Result detail page shows task evidence and unofficial/official badge.
- Methodology/tasks/submissions/why sections are reachable.
- No private task data or local paths appear in the deployed bundle.
