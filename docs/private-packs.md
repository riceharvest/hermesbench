# Private and fresh task packs

HermesBench keeps official tasks out of the public repository. Public `tasks/public-dev` packs are for development and always produce unofficial leaderboard entries.

## Loading a private pack

Use either:

```bash
HERMESBENCH_PRIVATE_PACK_DIR=/secure/hermesbench-packs \
  uv run hermesbench validate-tasks --task-root /secure/hermesbench-packs

uv run hermesbench run --suite fresh-2026-06 --task-root /secure/hermesbench-packs --agent mock
```

`--task-root` takes precedence over `HERMESBENCH_PRIVATE_PACK_DIR`. The directory must contain `manifest.yaml` and suite subdirectories shaped like the public `tasks/` directory.

## Secret-free repository policy

Do not commit private prompts, fixtures, hidden checks, or generated archives. Commit only public manifests/hashes and policy docs. Store private packs in maintainer-controlled storage.

## Manifest hash/archive policy

For every official pack, maintain a non-secret manifest record containing:

- pack name and suite id
- task ids and public categories (no prompts or hidden checks)
- SHA-256 hash of the canonical pack archive
- archive URI/location accessible only to maintainers
- creation date, freshness window, and retirement date

Canonical archive recommendation:

```bash
tar --sort=name --mtime='UTC 2026-01-01' --owner=0 --group=0 --numeric-owner \
  -czf hermesbench-fresh-YYYY-MM.tar.gz -C /secure/hermesbench-packs .
sha256sum hermesbench-fresh-YYYY-MM.tar.gz
```

Official results should include the manifest hash in run metadata and be archived with `hermesbench archive-official`.
