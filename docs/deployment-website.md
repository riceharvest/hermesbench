# Website deployment guide

## Build
```bash
cd website
pnpm install
pnpm build
```

## Output
Deploy `website/dist` as a static site.

## CI/CD workflow (`.github/workflows/vercel-prebuilt.yml`)

### Job dependency flow
```
cloud-checks (ubuntu-latest)
  └─ real-agent-validate (self-hosted runner)
      └─ deploy (ubuntu-latest)
          └─ post-deploy-smoke (ubuntu-latest, read-only)
```

**`cloud-checks`** — `ubuntu-latest`, no Hermes profile needed.
- Validate task inventory, run Python unit tests (`pytest`), build Python distributions, build the static website, run the local API smoke test suite (`pnpm test:api`). All operations are stateless and cloud-portable.

**`real-agent-validate`** — `self-hosted` runner, acquires a `flock`-based profile lock.
- Runs the actual Hermes agent against a benchmark task (`htu-dev-001-file-and-terminal-self-serve`) using the local Hermesbench profile, then scores the result. This is the only job that touches the self-hosted runner's local Hermes profile, and it's serialized via the `hermesbench-realagent-*` concurrency group.

**`deploy`** — moved to `ubuntu-latest` (no Hermes runner needed).
- Builds and deploys a prebuilt artifact to Vercel using `vercel@51.5.0`. Exports the deployed URL as `deploy.outputs.deployed_url` for the post-deploy smoke job.

**`post-deploy-smoke`** — `ubuntu-latest`, read-only.
- Hits `GET /health` and asserts `ok == true` using `jq`.
- Hits `GET /v1/leaderboard` and asserts `entries` is an array.
- Does **not** submit data, set `HERMESBENCH_SUBMISSION_TOKEN`, or carry Vercel credentials. Entirely safe.

### Concurrency model
Only `real-agent-validate` joins the `hermesbench-realagent-*` concurrency group (cancel-in-progress). All cloud jobs (`cloud-checks`, `deploy`, `post-deploy-smoke`) run independently — they share no local state and need no serialization.

## Vercel
- Root directory: `website`
- Install command: `pnpm install`
- Build command: `pnpm build`
- Output directory: `dist`
- Rewrites in `website/vercel.json` expose `/health` and `/v1/*` from the serverless functions under `website/api/`.
- Set `HERMESBENCH_SUBMISSION_TOKEN` in production/preview for `/v1/results`.
- Connect a Vercel Blob store so production/preview have `BLOB_READ_WRITE_TOKEN`.
- **Do NOT set `HERMESBENCH_SUBMISSION_TOKEN` in GitHub Actions, git-secret, or any code-adjacent location** — set it only in the Vercel Project environment variables.
- The API will **fail closed** (503) when running on Vercel (`VERCEL=1`) without `BLOB_READ_WRITE_TOKEN`. This is deliberate — no local-filesystem fallback on production.
- `BLOB_READ_WRITE_TOKEN` is implicitly present in any Vercel project with a connected Blob store; it is automatically available at runtime. Do not copy it to GitHub or local `.env` files.

## Configuration
The leaderboard is served live from the API. No static mock data exists in the repository. Only reviewed, archived official runs appear as capability evidence. Authenticated submissions use `https://hermesbench.site/v1/results`, persist sanitized uploads to Vercel Blob, and feed the API leaderboard.

## Smoke checklist
- Landing page loads with no-result state when no data exists.
- Leaderboard page renders entries from the API.
- Result detail page shows task evidence and status badge.
- Methodology, tasks, and run instructions are reachable.
- Browser upload form on /submit page lets maintainers select a scored JSON file, enter a submission token, and POST to `/v1/results` without the token being stored or logged.
- `HERMESBENCH_SUBMISSION_TOKEN=UPLOAD_SECRET uv run hermesbench upload <result.json> --endpoint https://hermesbench.site/v1/results` returns `202` and the run appears in `GET /v1/leaderboard`.
- No private task data or local paths appear in the deployed bundle.
