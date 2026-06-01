# Benchmark methodology

Static LLM benchmarks get benchmaxxed: tasks leak into training data, prompts become optimization targets, and high scores stop predicting real agent reliability. HermesBench measures tool-using agents on execution: did the agent inspect files, create artifacts, run checks, and avoid claiming success without evidence?

HermesBench splits tasks into public/dev tasks for local iteration, private hidden holdouts for leaderboard integrity, fresh rolling waves for current-world robustness, and stable anchor sets for longitudinal comparison. Objective tasks use deterministic, artifact, or test-based scoring. LLM judges are secondary and only used where subjective quality is unavoidable.

Tasks are versioned by wave and include freshness windows, contamination notes, expected human time, required toolsets, safety notes, and grading type. Hidden checks should validate details not exposed in public prompts while avoiding credential leakage. Human baselines should be collected from timed runs by competent operators using the same fixtures and no hidden oracle access.

Interpret scores as practical reliability under a specific tool/runtime budget. Do not compare private official leaderboard scores with ad-hoc public/dev local runs, different timeout policies, or runs that skip verification/cost capture.

Official leaderboard entries follow `docs/official-runs.md`: maintainer-controlled private/fresh packs, disclosed runtime metadata, archived raw results, and SHA256-verified manifests. Public self-submissions remain unofficial and cannot set the official flag through the public API.


## Anchor promotion

Anchor tasks are promoted only after at least one public/dev or fresh run window, must avoid current-world facts, and must use deterministic or test-based scoring. Any substantive anchor change requires a new benchmark version; deprecations require a changelog entry. See `docs/anchor-set-policy.md`.
