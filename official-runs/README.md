# Versioned official evidence

This directory is intentionally **not ignored**. It is reserved for reviewed, public-safe evidence from official HermesBench runs.

Do not place exploratory output here. Local runs belong in `results/` and local artifacts in `artifacts/`, both ignored by Git. For an official run, archive the sanitized `result.json`, reviewed manifest, score summary, and checksums in a run-specific subdirectory after maintainer review. The legacy `official_runs/TEMPLATE.yaml` remains a manifest template; new checked-in evidence should use this hyphenated directory.

A mock-adapter run is plumbing evidence only and must never be archived here as model-capability evidence.
