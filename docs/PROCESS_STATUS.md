# Production-Readiness Status Tracker

> Ground truth for what stage the repository is in and what must happen before launch.
> Last updated: 2026-07-10.

## Stage definitions

| Stage | Meaning | Who can claim it |
|---|---|---|
| **Local build-ready** | All repository-level gates pass on the developer workstation. | Any contributor |
| **Release candidate** | Build, test, website, packaging, and self-hosted real-agent smoke gates all pass; release artifacts are publishable. | Maintainer (after RC checklist) |
| **Live deployment** | `https://hermesbench.site` serves live submissions and leaderboard from Vercel with Blob storage. | Maintainer (after live checklist) |

**Current stage: LOCAL BUILD-READY** — heading toward first release candidate.

---

## Stage 1: Local build-ready — PASSED

| Gate | Command | Status | Evidence |
|---|---|---|---|
| Full test suite | `uv run pytest -q` | ✅ **155 passed, 2 skipped** | Parent-side verification after CI/workflow integration |
| Python package builds | `uv build` | ✅ sdist + wheel produced | `dist/hermesbench-0.1.0-py3-none-any.whl`, `dist/hermesbench-0.1.0.tar.gz` |
| Website builds | `cd website && pnpm install --frozen-lockfile && pnpm build` | ✅ | `website built; all public JSON provenance and paths validated` |
| Website API smoke (local handler) | `cd website && pnpm test:api` | ✅ **9/9 passed** | Parent-side verification after rate-limit environment cleanup |
| Workflow YAML syntax | `python3 -c "yaml.safe_load(…)"` for all 3 workflow files | ✅ | `All workflow YAML files parse OK` |
| Git whitespace | `git diff --check` | ✅ | No trailing-space or tab-in-indent errors |
| Task inventory validates | `uv run hermesbench validate-tasks` | ✅ | (passes via CI gate) |
| Reproducibility gates | `uv run pytest --run-slow tests/test_release_reproducibility.py -q` | ✅ **13 passed** | Parent-side verification; fresh-wheel and sdist-rebuild tests executed |
| Mock adapter removed | `src/hermesbench/adapters/mock.py` | ✅ **Deleted** | part of 37-file pivot |
| Demo mock data removed | `website/data/demo-leaderboard.json`, `website/data/demo-result.json`, `website/data/latest-result.json`, `website/data/leaderboard.json` | ✅ **Deleted** | part of 37-file pivot |
| Mock results removed | `results/mock-nt/` | ✅ **Deleted** | part of 37-file pivot |

---

## Stage 2: Release candidate — UNVERIFIED BLOCKERS

### Runner label: `hermesbench-local`

The workflows target `[self-hosted, Linux, X64, vercel, hermesbench-local]`. The `hermesbench-local` label is present in the workflow YAML and verified on
the GitHub runner configuration.

**To verify:**
```bash
# Verified from the repository API:
gh api repos/riceharvest/hermesbench/actions/runners \
  --jq '.runners[] | select(.name == "fedora-hermesbench") | .labels[].name'
# Required output includes: hermesbench-local
```

**Why it matters:** Without this label, real-agent jobs silently fall back to the generic `vercel` label, and cloud-only jobs might land on the shared runner — defeating the credential isolation boundary.

### Live Vercel environment and Blob

The deployment docs (`docs/deployment-api.md`, `docs/deployment-website.md`) define the production contract but the `https://hermesbench.site` environment has **NOT been verified**:

| Requirement | Status | Verifier |
|---|---|---|
| `HERMESBENCH_SUBMISSION_TOKEN` set in Vercel project | ❓ Not verified | Vercel dashboard or `vercel env ls` |
| `BLOB_READ_WRITE_TOKEN` auto-provisioned by connected Blob store | ❓ Not verified | Vercel dashboard |
| CORS origins configured for `https://hermesbench.site` | ❓ Not verified | Vercel config or smoke test against live domain |
| Rate-limit settings (`MAX`, `WINDOW_SECONDS`) | ❓ Not verified | Vercel environment variables |
| No `HERMESBENCH_SUBMISSION_TOKEN` in GitHub secrets or Actions | ❓ Not verified | `gh secret list`, workflow YAML audit |

### Real self-hosted smoke (Hermes agent run)

The workflows contain the step definition for real-agent smoke (`uv run hermesbench run --agent hermes --profile hermesbench …`) but a **real Hermes agent run on the self-hosted runner has NOT been executed** against this repository state:

| Sub-gate | Status | Verifier |
|---|---|---|
| Self-hosted runner is online | ✅ Verified | `gh api repos/riceharvest/hermesbench/actions/runners`: `fedora-hermesbench`, online, idle |
| `hermes` CLI is installed on runner | ❓ Not verified | Runner login or CI log |
| `hermesbench` Hermes profile exists | ❓ Not verified | `test -d ~/.hermes/profiles/hermesbench` |
| Concurrency group + `flock` serialization works | ❓ Not verified | Two concurrent workflow triggers must not collide |
| Runtime output paths are unique and cleaned up | ❓ Not verified | CI log inspection after run |
| No credentials in logs or artifacts | ❓ Not verified | CI log inspection |

### Post-deploy smoke (live API)

The RELEASE_CHECKLIST defines post-deploy smoke tests against `https://hermesbench.site` that have **never been executed**:

```bash
# Health check
curl https://hermesbench.site/health
# Expected: {"ok": true}

# Leaderboard (may be empty)
curl https://hermesbench.site/v1/leaderboard

# Invalid submissions rejected
curl -X POST https://hermesbench.site/v1/results -H 'Content-Type: application/json' -d '{"garbage": true}'
# Expected: 4xx
```

---

## Next actions (ordered)

1. **Clean up the working tree** — Split the 37-file uncommitted pivot into reviewable commits per the production plan (Task 0.2). The current dirty worktree is intentional for integration but must be cleaned before a release candidate.
2. **Verify `hermesbench-local` runner label** — Confirmed through the GitHub Actions runner API; `fedora-hermesbench` is online with the label.
3. **Verify live Vercel environment** — Set `HERMESBENCH_SUBMISSION_TOKEN` (if not already), confirm Blob is connected and `BLOB_READ_WRITE_TOKEN` is present, review CORS and rate-limit config.
4. **Execute real self-hosted smoke** — Push the reviewed changes and verify the `real-agent-smoke` job runs end-to-end on the local runner.
5. **Run post-deploy smoke** — After Vercel deploy, run the RELEASE_CHECKLIST post-deploy smoke tests against `https://hermesbench.site`.
6. **Execute the full RELEASE_CHECKLIST** — Before tagging any release, go through every gate in `docs/RELEASE_CHECKLIST.md`.

---

## Rejected approaches

These were considered, tested, and rejected:

| Approach | Why rejected |
|---|---|
| **Mock adapter fallback in CI** | Non-negotiable constraint: no mock adapter, mock result, or static demo fallback may appear in production release gates. The mock adapter (`src/hermesbench/adapters/mock.py`) and all mock result data (`results/mock-nt/`, `website/data/demo-*.json`) have been deleted. |
| **Provider credentials in GitHub secrets/Actions** | Non-negotiable constraint: provider credentials must remain local to the Hermes profile on the self-hosted runner. No provider API keys, model tokens, or endpoint secrets may be declared in GitHub Secrets, workflow YAML, or environment variables in Actions. |
| **Vercel ephemeral filesystem as production storage** | Rejected in favor of fail-closed Blob storage. When `VERCEL=1` and `BLOB_READ_WRITE_TOKEN` is absent, the API returns 503 instead of silently falling back to the Vercel filesystem. |
| **Anonymous public uploads at launch** | Deferred. First release is maintainer/invite-only. Public uploads require per-submitter scoped credentials, review workflows, and retention policies (P2). |
| **Single shared `vercel` runner label for all jobs** | Replaced with dedicated `hermesbench-local` label to prevent cloud-only jobs from running on the profile-accessing self-hosted runner. |

---

## Known minor issues

### Historical verification notes

The website smoke test previously leaked temporary rate-limit settings into its
second phase; the environment cleanup is now in place and the complete smoke
passes 9/9. The slow reproducibility tests are now wired into release CI and
pass when invoked with `--run-slow`.

---

## Production ground truth

- The **only** HermesBench website/production domain is **`https://hermesbench.site`**.
- The **only** live API is served by Vercel functions under `website/api/`.
- The Python HTTP server (`src/hermesbench/http_api.py`) is for **local dev and CI smoke only** — never exposed to the public internet (documented in `docs/deployment-api.md`).
- Official results are **never** accepted through public upload. They are created by maintainer-only offline promotion.
