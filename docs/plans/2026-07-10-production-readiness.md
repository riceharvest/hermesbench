# HermesBench Production Readiness Plan

> **For Hermes:** Use the subagent-driven-development skill to implement this plan task-by-task. Keep real-agent verification on the self-hosted Hermes runner; never copy provider credentials into GitHub Actions, artifacts, logs, or the website.

**Goal:** Turn the authenticated, real-Hermes capability probe into a reproducible, secure, observable, and operable production service and release process.

**Architecture:** Cloud-hosted jobs perform repository, packaging, website, and static checks. A separately labelled self-hosted Hermes runner performs real-agent smoke/benchmark execution using its local `hermesbench` profile and local provider configuration. Vercel functions serve the public API and Vercel Blob stores sanitized unofficial submissions; official results are promoted through a maintainer-controlled offline workflow.

**Tech Stack:** Python 3.11+, uv/Hatch, pytest, Hermes CLI, GitHub Actions, self-hosted Linux runner, Vercel Functions, Vercel Blob, pnpm 9, static website.

---

## Current baseline

Evidence collected before writing this plan:

- `uv build` succeeds and produces both sdist and wheel.
- `uv run pytest -q` passes: 76 tests.
- Workflow YAML parses and `git diff --check` passes.
- The worktree contains a 37-file uncommitted mock-removal/authenticated-probe pivot. Treat this as an integration branch, not as a production release candidate yet.
- `src/hermesbench/api.py:11-17` explicitly documents that the Python API scaffold is development-only and that auth/rate limiting are not production-grade.
- `docs/deployment-api.md:5-19` defines the intended Vercel production path, token, rate-limit, CORS, and Blob settings.
- The existing self-hosted runner is online with labels `self-hosted`, `Linux`, `X64`, and `vercel`.

## Independent audit findings that affect sequencing

Four read-only audits confirmed these launch blockers or early gates:

- `src/hermesbench/schemas.py:69-75` checks that `schema_version` exists but not that it equals `hermesbench.result.v1`.
- `src/hermesbench/api.py:66-82` does not accept the same header-token sources or apply the same sanitization allowlists as `website/api/_submissions.js`.
- `website/api/_submissions.js:411-448` uses public deterministic Blob paths and allows overwrite; missing Blob configuration can fall back to ephemeral local storage.
- The self-hosted workflows share one runner, HOME, Hermes profile, and state; the current `vercel` label does not provide isolation.
- `release.yml` has no tag history, artifact checksums/signatures, Hermes version pin, or post-deployment smoke gate.
- The public submission path still uses one shared token. Decide whether that is acceptable for an invite-only launch; otherwise replace it with scoped credentials before enabling public writes.

## Proposed first-release posture

Implement the first release as a deliberately narrow, defensible launch:

1. One local Hermes profile and one serialized self-hosted real-agent lane.
2. Maintainer/invite-only submissions; do not enable anonymous public uploads yet.
3. Vercel Blob as the production store, with fail-closed behavior when Blob is unavailable.
4. Official results generated privately and promoted through a maintainer-only workflow.
5. No provider credentials in GitHub Actions, artifacts, logs, or public data.

## Proposed fixes, in implementation order

### P0-A: Make Python and Vercel validation equivalent

Create shared JSON fixtures and enforce exact schema versions, strict field/type validation, score bounds, task/result limits, header/Bearer token parity, constant-time token comparison, and identical sanitization allowlists. Remove submission tokens from request bodies; use headers only.

### P0-B: Make production storage fail closed and idempotent

Require Blob configuration in production, remove overwrite behavior, make `run_id` submissions idempotent, reject conflicting duplicates, and use private or unguessable storage paths. Never silently persist to ephemeral Vercel filesystem storage.

### P0-C: Isolate the real-Hermes lane

Prefer an ephemeral or dedicated `hermesbench-local` runner with isolated HOME/filesystem. Until that exists, serialize all profile access with a shared Actions concurrency group and `flock`, use run/job-specific temporary paths, pin Hermes, and clean up after every run.

### P1-A: Make releases reproducible

Add annotated version tags, Hermes version recording/pinning, benchmark manifests, result/artifact hashes, SHA-256 checksums, fresh-wheel verification, and post-deployment API smoke tests.

### P1-B: Keep the grader boundary trusted

Treat task packs as trusted, hash-verified repository code; do not over-restrict legitimate shell checks. Require explicit opt-in for the arbitrary `shell` adapter and isolate untrusted task packs before supporting them.

### P2: Add operational hardening after the first stable release

Add request/run correlation IDs, bounded structured errors, health alerts, retention policies, backup/restore drills, and scoped per-submitter credentials before expanding beyond invite-only uploads.

## Implementation wave 1 — subagent results, pending parent integration

Four free implementation agents completed isolated workstreams. Their reported changes are **not yet applied to this checkout** and require parent-side diff review and verification.

| Workstream | Reported result | Parent integration gate |
|---|---|---|
| P0-A schema/API parity | Exact schema version/type/limit validation; header/Bearer token parity; constant-time comparison; deep token scrubbing; 73 focused tests reported passing | Re-read current Python API files, apply minimal diff, run the real full suite, and resolve existing wheel-test failures rather than accepting the subagent's “pre-existing” label blindly |
| P0-B Blob hardening | Production fail-closed storage; no overwrite; idempotent/conflicting duplicate handling; hash-prefixed paths; 26 Node tests reported passing | Inspect Blob SDK semantics and the actual handler call graph; verify no public response leaks internal hash fields; run website tests and a local handler smoke |
| P0-C runner isolation | Shared workflow concurrency; unique smoke directories; cleanup; explicit timeouts; Hermes version capture; 16 workflow tests reported passing | Compare all three workflow files against current uncommitted pivot; ensure concurrency groups cover every profile-using job and do not serialize unrelated cloud-only jobs unnecessarily |
| P1-A release reproducibility | Tag/version assertions; SHA-256SUMS; fresh-wheel/sdist tests; release checklist; 13 reproducibility tests reported passing | Verify release workflow syntax and artifact paths; run packaging tests from the parent checkout; do not create a tag or claim a release until the maintainer approves versioning |

### Integration order

1. Integrate and verify P0-A first because API behavior and tests are shared contract dependencies.
2. Integrate P0-B separately and run the JavaScript suite before touching deployment configuration.
3. Integrate P0-C only after checking that its workflow rewrites preserve the local-profile-only credential boundary.
4. Integrate P1-A last; it depends on the final workflow shape and current package version.
5. Run parent-side `uv run pytest -q`, `uv build`, website tests/build, YAML parsing, and `git diff --check` after the wave.

## Non-negotiable constraints

1. No mock adapter, mock result, static demo fallback, or mock-based release gate returns.
2. Real Hermes execution must use the local Hermes profile on the self-hosted runner.
3. Provider credentials remain local to Hermes and must never enter GitHub secrets, workflow logs, result artifacts, public data, or Vercel.
4. Cloud CI must fail when required repository checks fail; it must not silently skip real-agent verification.
5. Public submissions are unofficial. Only the maintainer promotion process can create official results.
6. Every production claim needs a reproducible command and stored evidence.

---

# Phase 0 — Freeze the product contract and isolate the pivot

### Task 0.1: Decide the production lanes

**Objective:** Record the boundary between cloud repository checks, self-hosted real-Hermes checks, unofficial public submissions, and official promotion.

**Files:**
- Modify: `docs/architecture.md`
- Modify: `docs/deployment-api.md`
- Create: `docs/PROCESS_STATUS.md`

**Acceptance:** The documents state which runner executes real Hermes, which data may be public, where credentials live, and what creates an official result.

### Task 0.2: Split the current uncommitted pivot into reviewable commits

**Objective:** Make the mock-removal/authenticated-probe change auditable before adding production hardening.

**Files:** Current 37-file worktree; do not include unrelated generated or local files.

**Acceptance:** Separate commits exist for mock removal, API/website changes, workflow changes, and documentation/tests; each commit passes its relevant tests. Do not rewrite history or push until reviewed.

### Task 0.3: Add a production-readiness status tracker

**Objective:** Prevent future sessions from confusing local build readiness with release-candidate or live-deployment readiness.

**Files:** `docs/PROCESS_STATUS.md`, `README.md`

**Acceptance:** The tracker has stage, status, evidence, next action, gate criteria, and explicit already-tried/rejected approaches.

---

# Phase 1 — Make CI and the self-hosted Hermes lane trustworthy

### Task 1.1: Add a dedicated self-hosted runner label

**Objective:** Prevent unrelated deployment jobs from consuming the runner intended for local Hermes execution.

**Files:** `.github/workflows/ci.yml`, `.github/workflows/release.yml`, `.github/workflows/vercel-prebuilt.yml`, runner configuration outside the repository.

**Acceptance:** The runner has a dedicated label such as `hermesbench-local`; real-agent jobs target that label and no cloud job can accidentally run the local-provider lane. If the runner remains shared, a workflow-level concurrency group serializes all jobs that touch the local Hermes profile. The preferred production design is an ephemeral or separately provisioned runner with isolated HOME and filesystem.

### Task 1.2: Split cloud checks from real-agent checks

**Objective:** Keep unit/package/website checks portable while making the local-provider dependency explicit.

**Files:** `.github/workflows/ci.yml`, `.github/workflows/release.yml`, `.github/workflows/vercel-prebuilt.yml`

**Acceptance:**
- Cloud jobs run tests, builds, schema checks, and website checks.
- A separate self-hosted job verifies `hermes`, the `hermesbench` profile, the configured local endpoint, and one real task.
- No provider credential environment variables are declared in workflow YAML.
- Self-hosted jobs use a shared concurrency group, unique `${{ github.run_id }}-${{ github.job }}` output paths, timeouts, and cleanup traps to avoid overlapping local model runs and stale artifacts.

### Task 1.3: Add a local Hermes preflight command

**Objective:** Fail before a benchmark if the self-hosted runner cannot actually execute the configured local Hermes process.

**Files:** `src/hermesbench/cli.py`, `src/hermesbench/adapters/hermes.py`, `tests/test_hermesbench_pipeline.py`, `docs/official-runs.md`

**Acceptance:** Preflight checks the profile, Hermes executable, selected provider/model resolution, local endpoint reachability where applicable, and tool availability without printing credentials. Missing local services produce actionable errors.

### Task 1.4: Test fresh-environment packaging

**Objective:** Ensure the wheel and sdist work without the current developer environment masking missing dependencies.

**Files:** `pyproject.toml`, `.github/workflows/ci.yml`, packaging tests if needed.

**Acceptance:** A clean venv installs the built wheel, runs `hermesbench --help`, validates tasks, and executes non-network deterministic checks. `uv build` and wheel-content inspection are CI gates.

---

# Phase 2 — Harden schemas, scoring, and provenance

### Task 2.1: Enforce exact result schema versions and types

**Objective:** Reject malformed or ambiguous results before storage or scoring.

**Files:** `src/hermesbench/schemas.py`, `src/hermesbench/api.py`, `website/api/_submissions.js`, Python/JS tests.

**Acceptance:** Validation checks exact schema version, field types, score bounds, timestamps, task IDs, result cardinality, and required metadata. Python and JavaScript behavior agree on accepted/rejected fixtures. The Python HTTP API accepts `X-Hermesbench-Submission-Token` and Bearer headers with the same precedence as the Vercel API.

### Task 2.2: Define and freeze the public submission schema

**Objective:** Separate private runner telemetry from public leaderboard data.

**Files:** `docs/api.md`, `docs/deployment-api.md`, `src/hermesbench/schemas.py`, `website/api/_submissions.js`

**Acceptance:** The public allowlist is documented, versioned, tested, and includes no transcripts, prompts, environment paths, secret-like values, or raw logs.

### Task 2.3: Sanitize the Python storage path as well as Vercel storage

**Objective:** Ensure local/dev persistence follows the same privacy boundary as the live Vercel path.

**Files:** `src/hermesbench/api.py`, `tests/test_hermesbench_http_api.py`

**Acceptance:** `sanitize_for_storage()` removes transcripts, logs, sensitive metadata, and submission tokens; tests prove secrets and model-controlled text cannot reach stored public records.

### Task 2.4: Make run identity and duplicate handling explicit

**Objective:** Prevent retries from creating duplicate leaderboard entries.

**Files:** `src/hermesbench/api.py`, `website/api/_submissions.js`, API tests, `docs/api.md`

**Acceptance:** `run_id` format and uniqueness are documented; repeated submission of the same run is idempotent or returns a deterministic conflict; concurrent writes do not corrupt storage.

### Task 2.5: Version scoring independently from result schema

**Objective:** Make leaderboard changes reproducible when scoring logic evolves.

**Files:** `src/hermesbench/scoring.py`, `src/hermesbench/api.py`, website scoring/build code, docs.

**Acceptance:** Every score records a scorer version and benchmark version; historical results can be rescored or explicitly remain pinned to their original scorer.

---

# Phase 3 — Production API and data layer

### Task 3.1: Verify Vercel production environment configuration

**Objective:** Prove the deployed API has the required token, Blob, CORS, limits, and environment separation.

**Files:** `docs/deployment-api.md`, Vercel project configuration, deployment checklist.

**Acceptance:** Production has `HERMESBENCH_SUBMISSION_TOKEN`, `BLOB_READ_WRITE_TOKEN`, explicit CORS origins, body/task limits, and rate-limit settings. Preview and production values are distinct and secrets are not printed.

### Task 3.2: Add deployment smoke tests against the live domain

**Objective:** Verify the deployed route rather than only the local JavaScript handler.

**Files:** `website/scripts/smoke-api.js`, `.github/workflows/vercel-prebuilt.yml`, `docs/deployment-website.md`

**Acceptance:** Smoke tests cover health, leaderboard, invalid schema, missing token, valid unofficial submission, duplicate submission, CORS, body-size rejection, and that public responses contain only allowlisted fields. The test never submits an official or sensitive fixture.

### Task 3.3: Harden rate-limit and storage failure behavior

**Objective:** Define safe behavior under concurrent requests and Blob/API outages.

**Files:** `website/api/_submissions.js`, tests, deployment docs.

**Acceptance:** Rate-limit failures fail closed or return a documented retryable response; Blob write/list failures do not produce false success; production fails closed when Blob is unavailable instead of using ephemeral local storage; public Blob writes do not allow overwrite and use private/unguessable storage paths where supported; request IDs and bounded error messages are returned; concurrency tests cover duplicate and rate-limit races.

### Task 3.4: Add operational backup and rollback procedures

**Objective:** Recover leaderboard data and revert a bad deployment.

**Files:** `docs/deployment-api.md`, `docs/deployment-website.md`, new maintenance scripts only if required.

**Acceptance:** Documented restore test exists for Blob data, deployment rollback, token rotation, and removal of an invalid public submission without rewriting unrelated records.

---

# Phase 4 — Official-run integrity and release process

### Task 4.1: Define the official-run manifest contract

**Objective:** Make official results independently reviewable.

**Files:** `docs/official-runs.md`, official archive utilities, manifest tests.

**Acceptance:** A manifest records commit, benchmark version, task-pack hash, Hermes version, profile/provider/model identifiers without credentials, runner identity, scorer version, result hashes, and timestamps.

### Task 4.2: Build a private/fresh-pack official-run command

**Objective:** Ensure official runs cannot accidentally use stale fixtures, public submissions, or mock adapters.

**Files:** `src/hermesbench/cli.py`, `src/hermesbench/runner.py`, official-run scripts/tests.

**Acceptance:** The command creates an isolated work directory, verifies the task-pack hash, requires real Hermes, rejects `mock`, records provenance, and emits a reviewable archive.

### Task 4.3: Add review and promotion gates

**Objective:** Prevent an unreviewed upload from becoming official leaderboard data.

**Files:** `website/api/`, archive/promotion tooling, `docs/official-runs.md`, tests.

**Acceptance:** Public POST cannot set official status; only a maintainer-controlled promotion path can publish an official artifact; promotion is auditable and reversible.

### Task 4.4: Create a release candidate checklist

**Objective:** Turn production readiness into a repeatable release decision.

**Files:** `docs/RELEASE_CHECKLIST.md`, README/release docs.

**Acceptance:** Checklist includes clean-tree review, full tests, fresh install, self-hosted real smoke, official manifest validation, live API smoke, website build, artifact inspection, security checks, rollback readiness, and evidence links. A release is annotated/tagged, records the Hermes CLI version, publishes SHA-256 checksums (and signing/provenance when available), and runs a post-deploy health/leaderboard smoke.

---

# Phase 5 — Observability and operations

### Task 5.1: Add structured request and run identifiers

**Objective:** Correlate benchmark runs, API submissions, Blob writes, and deployment logs without logging secrets.

**Files:** `src/hermesbench/api.py`, `website/api/_submissions.js`, runner/result metadata, tests.

**Acceptance:** Every request and run has a safe correlation ID; logs contain status, latency, route, result ID, and error class but never tokens, transcripts, prompts, or full payloads.

### Task 5.2: Define health and alerting signals

**Objective:** Detect broken deployments and local runner failures quickly.

**Files:** `docs/deployment-api.md`, workflow files, optional monitoring scripts.

**Acceptance:** Document alerts for health failure, elevated 4xx/5xx, rate-limit spikes, Blob failures, stale self-hosted runner, failed real smoke, and leaderboard refresh failure.

### Task 5.3: Add retention and cleanup policies

**Objective:** Prevent unbounded local logs, temporary runs, rate-limit buckets, and archived submissions.

**Files:** docs, runner maintenance scripts/configuration, tests where behavior is code-owned.

**Acceptance:** Retention periods and deletion ownership are documented and exercised without deleting official evidence accidentally.

---

# Production launch gates

Do not call the system production-ready until all are true:

- [ ] The pivot is split into reviewable commits and the working tree is intentionally clean.
- [ ] `uv run pytest -q`, `uv build`, fresh-wheel install, and website build pass.
- [ ] Cloud CI and self-hosted Hermes CI are separate, timeout-bounded, and green.
- [ ] The self-hosted runner executes the intended local Hermes provider through `hermesbench` with no credential transfer.
- [ ] Python and Vercel validation/sanitization behavior agree on fixture tests.
- [ ] Live production API health, auth, idempotency, rate limiting, CORS, storage failure, and public-field allowlist tests pass.
- [ ] Official-run manifests and promotion/review gates pass against a fresh private run.
- [ ] Backup, rollback, token rotation, retention, and alerting procedures have been exercised.
- [ ] No mock code, mock data, demo fallback, credential, transcript, or secret appears in shipped artifacts or public responses.

## Direction questions to answer before Phase 1 implementation

1. Should the existing `vercel` runner receive a dedicated `hermesbench-local` label, or should a separate self-hosted runner be provisioned for benchmark execution?
2. Is Vercel Blob the intended production system of record, or should submissions move to a database before launch?
3. Should public unofficial uploads remain enabled at launch, or should the API be maintainer-only until the review workflow is complete?
4. Is the benchmark expected to run one local provider/model configuration per release, or should the runner support an explicit local profile matrix?
