# Anchor set promotion policy

Anchor tasks are stable longitudinal tasks used to compare agents across benchmark versions. They are intentionally slower-moving than public/dev or fresh waves.

## Eligibility
- A task can become an anchor only after at least one public/dev or fresh run window.
- The task must not depend on current-world facts, live websites, mutable APIs, or current dates.
- Fixtures must be redistributable, pinned, and complete enough for offline scoring.
- Scoring must be deterministic or test-based; judge-only scoring is not allowed for anchors.

## Promotion process
1. Nominate a task with evidence from prior runs and known failure modes.
2. Review contamination risks and remove source-specific answer leakage.
3. Freeze prompt, fixtures, checks, scoring policy, timeout, and expected artifacts.
4. Add the task to the next benchmark version registry.

## Change control
- Any substantive anchor prompt, fixture, or scoring change requires a new benchmark version.
- Typo-only docs changes may be made without changing scores, but must not alter task semantics.
- Deprecation requires a changelog entry explaining why the task is no longer valid and what replaces it.

## Reporting
Leaderboard pages must label which benchmark version and anchor set were used. Historical scores remain tied to the version that produced them.
