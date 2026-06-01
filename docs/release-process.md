# Release process

1. Update benchmark version registry and changelog.
2. Run local gates: `uv run pytest`, `uv run hermesbench validate-tasks`, mock public/dev run and score, and website build.
3. Export public tasks: `uv run hermesbench export --format jsonl > hermesbench-public-dev-v0.1.jsonl`.
4. Tag with `v0.x.y` and push the tag.
5. Let `.github/workflows/release.yml` build release artifacts.
6. Create or review the GitHub release, attaching the public task export JSONL and score schema documentation.
7. Confirm no private packs, hidden checks, secrets, local paths, or unpublished official-run evidence are attached.

Official leaderboard claims require the launch readiness checklist and official run archive policy to be satisfied.
