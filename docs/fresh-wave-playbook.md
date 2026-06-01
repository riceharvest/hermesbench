# Fresh rolling wave playbook

HermesBench fresh waves keep evaluation current without mixing ad-hoc tasks into official scoring.

## Cadence
- Open a fresh wave monthly by default; biweekly waves are allowed during rapid release cycles.
- Name waves `fresh-YYYY-MM` unless multiple waves ship in one month (`fresh-YYYY-MM-a`).
- Freeze task edits at least 72 hours before an official scoring window.

## Allowed sources
- Public documentation, changelogs, issues, release notes, public datasets, and locally reproducible fixtures published inside the freshness window.
- Synthetic fixtures derived from current workflows when raw source data cannot be redistributed.

## Disallowed sources
- Private user data, credentials, embargoed vulnerability details, paywalled material that cannot be redistributed, and leaked benchmark/private-pack content.
- Tasks whose answer depends on live network access at scoring time unless a fixture snapshot is archived.

## Freshness window
- Each task records `freshness_window_start` and `freshness_window_end`.
- Source material should be new or materially changed within the current wave window.

## Minimum content
- Target at least 10 tasks per official fresh wave.
- Cover at least three categories and at least two tool modalities.
- Every task must include fixtures or explicit `no_fixture_required: true`, deterministic/test scoring, contamination notes, and safety notes.

## Contamination review
- Record source URLs or provenance in task metadata.
- Check that exact expected artifacts are not posted publicly before the scoring window closes.
- Review prompts for benchmark-answer leakage and remove hidden-check details from public exports.

## Human baseline
- Collect at least two timed human attempts for official fresh waves when feasible.
- Record median completion time, common failure modes, and required tools; do not expose hidden oracle notes.

## Archival and anchor candidacy
- After a wave closes, mark it archived and preserve fixtures/result evidence.
- A fresh task may become an anchor candidate only after at least one public/fresh run window, deterministic scoring review, and removal of current-world dependencies.
