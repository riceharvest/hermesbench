# Benchmark methodology

HermesBench centers on the **minimum-capable-model probe** for Hermes Agent. The benchmark answers: *what is the smallest total-parameter model that can still autonomously use every Hermes tool class?*

The suite consists of the `natural-tools-dev` suite, containing 5 open-ended tool-use probes.

## Behavior grading

Scrubbing traditional scoreboards and correctness rankings, scoring is behavior-based from telemetry:

- **Trajectory evaluation**: Rather than grading output artifacts, we inspect the Hermes telemetry log to verify whether the agent successfully and correctly invoked the required tool classes during the execution.
- **Tool class mapping**: Telemetry events map specific tools to their core capability classes (e.g., `file`, `terminal`, `browser`, `web`, `code_execution`, `vision`, `memory`, `todo`, `delegation`, `clarify`, `cronjob`, `computer_use`, `skills`, `session_search`).
- **Scoring**: A task is scored as `1.0` if every required tool class was invoked at least once during execution, and `0.0` otherwise.
- **Minimum-capable model boundary**: The benchmark registry lists the parameter boundaries to identify the smallest models that achieve 100% coverage on required tool classes.
