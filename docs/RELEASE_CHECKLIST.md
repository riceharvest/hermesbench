# Release Checklist

This document defines the repeatable steps and gates for a HermesBench release.
Follow these steps for every release candidate.

## Pre-release: repository state

- [ ] Working tree is clean: `git diff --stat` shows no uncommitted changes.
- [ ] Working tree contains no generated or untracked build artifacts: `git status` shows only intentional files.
- [ ] Current branch is `main` (or the designated release branch).
- [ ] All commits from the pivot/mock-removal/authenticated-probe branch have been reviewed and merged.
- [ ] `docs/PROCESS_STATUS.md` records the current production-readiness stage. Read it before starting the checklist to confirm you are at release-candidate stage.

## Version and tag provenance

- [ ] `src/hermesbench/__init__.py` has the correct `__version__`.
- [ ] `pyproject.toml` version matches `__init__.py`.
- [ ] CI (`uv run pytest tests/test_release_reproducibility.py::test_package_version_matches_pyproject`) passes.
- [ ] Release tag is created as an **annotated** tag matching `v<version>`:

    ```bash
    git tag -a v<version> -m "HermesBench v<version>"
    git push origin v<version>
    ```

- [ ] `release.yml` tag provenance step asserts `GITHUB_REF_NAME == v<package_version>`.

## Build verification

- [ ] Full test suite passes: `uv run pytest -v --timeout=120`
- [ ] Task inventory validates: `uv run hermesbench validate-tasks`
- [ ] Python distributions build: `uv build`
- [ ] `dist/` contains both `.whl` and `.tar.gz`.
- [ ] Fresh-wheel verification passes:

    ```bash
    uv run pytest tests/test_release_reproducibility.py::test_fresh_wheel_install -v --timeout=120
    uv run pytest tests/test_release_reproducibility.py::test_sdist_rebuilds_identical_wheel -v --timeout=240
    ```

- [ ] Website builds: `cd website && pnpm install --frozen-lockfile && pnpm build`
- [ ] Website API smoke: `cd website && pnpm test:api`
- [ ] Reproducibility gates pass:

    ```bash
    uv run pytest tests/test_release_reproducibility.py -v --timeout=120
    ```

- [ ] Export produces valid JSONL: `uv run hermesbench export --suite natural-tools-dev --format jsonl > /tmp/check.jsonl && head -1 /tmp/check.jsonl | python -m json.tool > /dev/null`
- [ ] If `dist/` exists, SHA256SUMS are generated and valid: `sha256sum -c dist/SHA256SUMS`

## Self-hosted real-agent smoke

- [ ] Self-hosted runner is online with the target label.
- [ ] `hermes` CLI is installed on the runner.
- [ ] `hermesbench` profile exists: `test -d ~/.hermes/profiles/hermesbench`
- [ ] Hermes version is recorded:

    ```bash
    hermes --version
    ```

- [ ] Real-process smoke passes:

    ```bash
    uv run hermesbench run --agent hermes --profile hermesbench --task htu-dev-001-file-and-terminal-self-serve --output-dir /tmp/hermesbench-release-smoke
    uv run hermesbench score /tmp/hermesbench-release-smoke/*.json
    ```

- [ ] Smoke output is cleaned up: `rm -rf /tmp/hermesbench-release-smoke`

## Artifact integrity

- [ ] Release artifacts are uploaded with SHA256SUMS.
- [ ] Published artifact checksums match local build:

    ```bash
    sha256sum dist/hermesbench-<version>*
    curl -sL <release-url> | sha256sum -c <(echo "<expected-sha>  -")
    ```

- [ ] No submission tokens, transcripts, secrets, or private paths appear in release artifacts.

## Post-deploy smoke (live API)

- [ ] `GET https://hermesbench.site/health` returns `200 {"ok": true}`
- [ ] `GET https://hermesbench.site/v1/leaderboard` returns a valid leaderboard (may be empty).
- [ ] Invalid submissions are rejected with appropriate error codes.

## Post-release

- [ ] Release tag is pushed and GitHub Release is created (or triggered by tag push).
- [ ] `docs/RELEASE_CHECKLIST.md` is updated with any new steps discovered during this release.

## Rollback procedure

If a release must be rolled back:

1. Revert the GitHub Release to the previous tag.
2. If the API was deployed, redeploy the previous Vercel production deployment.
3. If Vercel Blob was modified, restore from backup (see `docs/deployment-api.md`).
4. If leaderboard data is corrupted, contact the maintainer to restore from the offline official archives.
