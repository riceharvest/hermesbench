# Architecture

`src/hermesbench` contains the installable HermesBench package: CLI, task parser, runner, adapters, graders, schemas, scoring, API/storage helpers, and official-run archive utilities. Tasks live under `tasks/` with a manifest and reusable template. Fixtures are copied into isolated temp workdirs per task. Results are normalized JSON and can be aggregated locally or uploaded later.

The wheel packaging boundary is deliberate: HermesBench ships `src/hermesbench/` only, keeping the core install small.

Dependency tiers:

- Core runtime: lightweight CLI/benchmark dependencies only (`pyyaml`).
- Dev/test: `pytest` via the `dev` dependency group.

## CI / self-hosted runner architecture

### Runner isolation model

Repository CI uses a **split runner model**:

| Runner | Label | Purpose |
|---|---|---|
| **Cloud** (GitHub-hosted) | `ubuntu-latest` | Unit tests, Python build, website build, schema checks, artifact packaging |
| **Self-hosted** | `[self-hosted, Linux, X64, vercel, hermesbench-local]` | Real Hermes agent execution — requires the local `hermesbench` Hermes profile |

Cloud jobs run on GitHub-hosted runners and never access the local Hermes profile, provider credentials, or model endpoints. Self-hosted jobs execute on a dedicated physical runner that has the `hermesbench` Hermes profile configured with local provider settings.

### Dedicated label: `hermesbench-local`

Every self-hosted job targets `[self-hosted, Linux, X64, vercel, hermesbench-local]`. The `hermesbench-local` label is the **dedicated production label** that prevents cloud-only jobs from accidentally landing on the shared runner. If the label hasn't been added to the runner configuration yet, the job still matches the existing `[self-hosted, Linux, X64, vercel]` set as a fallback — adding `hermesbench-local` to the label list makes the constraint stricter without breaking existing runner registration.

**Runner setup** (one-time):
```bash
# Add the hermesbench-local label to the self-hosted runner's config
# Usually this means editing .runner in the runner's home directory
# to add "hermesbench-local" to the "labels" array, then restarting the runner.
```

### Profile lock: `flock`

All self-hosted workflows serialize Hermes profile access with `flock --exclusive`:

```yaml
- name: Acquire Hermes profile lock and run smoke
  run: |
    LOCK_FILE="/tmp/hermesbench-profile.lock"
    flock --exclusive --timeout 300 "$LOCK_FILE" bash -c '...'
```

The lock file lives at `/tmp/hermesbench-profile.lock` and is shared across all jobs on the same runner filesystem. This prevents concurrently dispatched jobs (from different workflow runs) from accessing the same Hermes profile simultaneously, which could cause state corruption or overlapping model calls.

**Timeout:** 300 seconds (5 minutes). If a job cannot acquire the lock within that window it fails — this is intentional fail-closed behavior.

### Cloud-only vs self-hosted split

| Workflow | Cloud jobs | Self-hosted jobs |
|---|---|---|
| `ci.yml` | `validate-and-test` (ubuntu-latest) | `real-agent-smoke` |
| `release.yml` | `build-and-prepare`, `package-and-publish` (ubuntu-latest) | `real-agent-smoke` |
| `vercel-prebuilt.yml` | `cloud-checks` (ubuntu-latest) | `real-agent-validate`, `deploy` |

### Credential boundary

- **No provider credentials** (API keys, model tokens) are declared in workflow YAML, GitHub secrets, or environment variables in Actions.
- Provider configuration lives only in the Hermes profile at `$HOME/.hermes/profiles/hermesbench/`, which is local to the self-hosted runner.
- The concurrency group (`hermesbench-realagent-*`) and flock lock together ensure only one profile-accessing job runs at a time.
- Smoke output paths use unique `${{ github.run_id }}-${{ github.job }}` suffixes and are cleaned up via `if: always()` cleanup steps.
