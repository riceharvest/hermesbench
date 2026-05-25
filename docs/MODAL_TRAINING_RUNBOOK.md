# Modal training runbook

Use this before launching expensive Hermes-agent SFT jobs.

## Rules

- Put datasets, configs, checkpoints, and reports on a Modal Volume.
- Launch real training as a durable/background Modal job; do not rely on a local terminal staying connected.
- Save checkpoints frequently enough that a preemption/client issue does not waste the whole run.
- Write an eval report after every checkpoint candidate.
- Do not report training success until both exist:
  - checkpoint / adapter artifact
  - eval report with baseline comparison

## Suggested launch shape

```bash
modal run modal_train_sft.py --config configs/qwen36-hermes-v0-sft.yaml
```

For long runs, prefer a detached/background terminal/process and monitor logs by Modal app/run id.

## Required post-run checks

```text
outputs/qwen36-hermes-v0-sft-main/       # adapter/checkpoint exists
reports/hermes-v0-sft-main-eval.json    # eval exists
```

Then compare:

```text
quality score
invalid output rate
tool/action correctness
tokens per successful task
latency
cost per successful task
```

Only after v0 SFT is strong should we run the MTP refresh.
