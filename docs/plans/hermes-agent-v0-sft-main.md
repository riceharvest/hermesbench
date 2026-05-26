# Hermes Agent v0 SFT Main Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Build the first behavior-specialization pipeline for Qwen3.6-style Hermes-agent training, focused on maximum task performance with minimal reasoning/token spend.

**Architecture:** Keep the existing `qwen-mtp-probe` repo as the single project. Add dataset schemas, eval harness, SFT config, and training entrypoints before any expensive GPU run. MTP remains an acceleration refresh after SFT; normal-decode quality is the source of truth.

**Tech Stack:** Python 3.11+, PyTorch, Transformers, Accelerate, PEFT LoRA/DoRA, safetensors, pytest, Modal for remote GPU runs, SGLang/vLLM for serving eval.

---

## Current facts to preserve

- Working folder: `/home/dario/Documents/dev workspace/qwen-mtp-probe`.
- Git is initialized; initial probe commit is `5de6548`, SFT/eval scaffold commit is `b56b3e5`.
- Canonical current-stage tracker: `docs/PROCESS_STATUS.md`.
- Existing MTP proof is documented in `MTP_FEASIBILITY.md`.
- `unsloth/Qwen3.6-35B-A3B` has 19 `mtp.*` tensors and `mtp_num_hidden_layers = 1`.
- Stock HF ignores `mtp.*`; custom MTP wrapper/probes exist under `src/qwen_mtp_probe/qwen_mtp.py` and Modal scripts.
- MTP feasibility is complete: manual reconstruction, nonzero gradients, MTP-only overfit, export, and SGLang serving smoke all passed.
- SGLang speculative/MTP serving works with:

```bash
SGLANG_ENABLE_SPEC_V2=1 python -m sglang.launch_server \
  --model-path <assembled-checkpoint> \
  --reasoning-parser qwen3 \
  --speculative-algorithm EAGLE \
  --speculative-num-steps 3 \
  --speculative-eagle-topk 1 \
  --speculative-num-draft-tokens 4 \
  --mamba-scheduler-strategy extra_buffer
```

- Smoke benchmark result: normal `10.50 tok/s`, MTP `20.01 tok/s`, speedup `1.90x` on four compact JSON prompts.
- User target: maximize Hermes-agent performance with the highest performance in the least reasoning. Existing compact reasoning traces are valuable seed data; generate more only after format/scoring is defined.

---

## Stage A: Repository hygiene and docs

### Task A1: Initialize git history

**Objective:** Stop accumulating valuable experiments without version history.

**Files:**
- Modify/create: `.git/`
- Create: `.gitignore`

**Step 1: Check current state**

Run:

```bash
cd "/home/dario/Documents/dev workspace/qwen-mtp-probe"
git status --short || true
```

Expected: either not a git repo or shows untracked project files.

**Step 2: Create `.gitignore`**

Create `.gitignore` with:

```gitignore
.venv/
__pycache__/
.pytest_cache/
*.pyc
*.pyo
*.pyd
.DS_Store
reports/*.log
outputs/
checkpoints/
wandb/
.env
.env.*
```

Do **not** ignore `reports/*.json`; those are evidence artifacts for now.

**Step 3: Initialize and commit**

Run:

```bash
git init
git add README.md pyproject.toml uv.lock src tests scripts *.py *.md reports/*.json docs .gitignore
git commit -m "chore: initialize qwen hermes specialization probe"
```

Expected: first commit created.

---

### Task A2: Add project specialization overview

**Objective:** Preserve collected context and target strategy in docs.

**Files:**
- Already created: `docs/HERMES_AGENT_SPECIALIZATION.md`
- Modify: `README.md`

**Step 1: Add README pointer**

Append to `README.md`:

```markdown
## Hermes-agent specialization

This repo is also the working folder for Hermes-agent model specialization: compact reasoning traces, tool/action selection, SFT, optional preference/RL, and MTP refresh after behavior shifts.

See:

- `docs/HERMES_AGENT_SPECIALIZATION.md`
- `docs/plans/hermes-agent-v0-sft-main.md`
```

**Step 2: Verify docs render enough**

Run:

```bash
python - <<'PY'
from pathlib import Path
for p in [Path('README.md'), Path('docs/HERMES_AGENT_SPECIALIZATION.md')]:
    assert p.exists(), p
    assert p.read_text().strip(), p
print('docs ok')
PY
```

Expected: `docs ok`.

---

## Stage B: Dataset conventions and seed data

### Task B1: Create dataset README

**Objective:** Define the training/eval data contract before collecting more traces.

**Files:**
- Create: `data/README.md`
- Create dirs: `data/raw/`, `data/examples/`, `data/processed/`, `data/eval/`

**Step 1: Create directories**

Run:

```bash
mkdir -p data/raw data/examples data/processed data/eval
```

**Step 2: Write conventions**

Create `data/README.md` with sections:

```markdown
# Hermes-agent training data

## Data classes
- successful compact traces
- compact reasoning distillations
- tool/action selection examples
- negative/contrastive examples
- hard failure / uncertainty examples

## SFT JSONL schema
...

## Preference pair schema
...

## Eval item schema
...

## Quality rules
- no verbose chain-of-thought dumps
- compact scratchpad only when needed
- tool calls must be parseable
- final answers should be concise
- every example should encode a useful behavior
```

**Step 3: Verify**

Run:

```bash
test -f data/README.md && test -d data/examples && test -d data/eval
```

Expected: exit code 0.

---

### Task B2: Add seed SFT examples

**Objective:** Create a tiny, inspectable seed set that encodes target behavior.

**Files:**
- Create: `data/examples/hermes_compact_traces.seed.jsonl`
- Test: `tests/test_dataset_schema.py`

**Step 1: Write failing schema test**

Create `tests/test_dataset_schema.py`:

```python
import json
from pathlib import Path


def test_seed_sft_jsonl_has_messages():
    path = Path('data/examples/hermes_compact_traces.seed.jsonl')
    assert path.exists()
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    assert rows
    for row in rows:
        assert 'messages' in row
        assert isinstance(row['messages'], list)
        assert row['messages'][-1]['role'] == 'assistant'
        content = row['messages'][-1]['content']
        assert 'SCRATCH<=80:' in content or 'FINAL:' in content or 'ACTION' in content
```

**Step 2: Run to verify failure**

Run:

```bash
uv run --with pytest python -m pytest tests/test_dataset_schema.py -q
```

Expected: fails because seed file does not exist.

**Step 3: Create seed examples**

Create `data/examples/hermes_compact_traces.seed.jsonl` with 5-10 examples covering:

- inspect existing repo/folder before creating new one;
- use terminal for live system facts;
- search docs before changing SGLang flags;
- verify result before claiming success;
- concise final response after tool work.

Example line:

```json
{"messages":[{"role":"system","content":"You are Hermes Agent. Use compact reasoning and tool actions. Do not claim success without verification."},{"role":"user","content":"don't we have a repo already? or a folder?"},{"role":"assistant","content":"SCRATCH<=80:\nNeed inspect workspace, not create new repo. Find qwen/mtp folders and top-level files.\n\nACTION search_files {\"path\":\"/home/dario/Documents/dev workspace\",\"pattern\":\"*qwen*\",\"target\":\"files\"}"}]}
```

**Step 4: Run test to verify pass**

Run:

```bash
uv run --with pytest python -m pytest tests/test_dataset_schema.py -q
```

Expected: pass.

---

### Task B3: Add seed eval examples

**Objective:** Define measurable held-out tasks before training.

**Files:**
- Create: `data/eval/hermes_v0_eval.seed.jsonl`
- Modify: `tests/test_dataset_schema.py`

**Step 1: Extend schema test**

Add:

```python
def test_seed_eval_jsonl_has_expected_behavior():
    path = Path('data/eval/hermes_v0_eval.seed.jsonl')
    assert path.exists()
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    assert rows
    for row in rows:
        assert {'id', 'input', 'expected_behavior', 'scorer'} <= set(row)
```

**Step 2: Create eval seed file**

Create examples for scorer types:

- `tool_use_required`
- `repo_inspection_required`
- `verification_required`
- `concise_final_required`
- `no_unnecessary_clarification`

**Step 3: Verify**

Run:

```bash
uv run --with pytest python -m pytest tests/test_dataset_schema.py -q
```

Expected: pass.

---

## Stage C: Config and loaders

### Task C1: Add v0 SFT config

**Objective:** Record intended training settings without hard-coding them in scripts.

**Files:**
- Create: `configs/qwen36-hermes-v0-sft.yaml`
- Modify: `pyproject.toml` if PyYAML is needed for config loading.

**Config skeleton:**

```yaml
run_name: qwen36-hermes-v0-sft-main
base_model: unsloth/Qwen3.6-35B-A3B
output_dir: outputs/qwen36-hermes-v0-sft-main

training:
  method: qlora
  adapter: lora
  max_seq_length: 8192
  learning_rate: 0.0001
  num_train_epochs: 1
  per_device_train_batch_size: 1
  gradient_accumulation_steps: 16
  warmup_ratio: 0.03
  weight_decay: 0.0
  bf16: true
  gradient_checkpointing: true

lora:
  r: 16
  alpha: 32
  dropout: 0.05
  target_modules:
    - q_proj
    - k_proj
    - v_proj
    - o_proj
    - gate_proj
    - up_proj
    - down_proj
    - gate_up_proj

behavior:
  compact_scratchpad_budget_tokens: 80
  optimize_for: cost_per_successful_task
  forbidden:
    - unverified_success_claims
    - unnecessary_clarification
    - verbose_generic_reasoning

data:
  train_path: data/processed/hermes_v0_train.jsonl
  eval_path: data/eval/hermes_v0_eval.seed.jsonl
```

**Verification:**

```bash
python - <<'PY'
from pathlib import Path
p = Path('configs/qwen36-hermes-v0-sft.yaml')
assert p.exists() and 'qwen36-hermes-v0-sft-main' in p.read_text()
print('config ok')
PY
```

---

### Task C2: Implement dataset loader

**Objective:** Validate and load SFT chat JSONL consistently.

**Files:**
- Create: `src/qwen_mtp_probe/datasets.py`
- Create/modify: `tests/test_datasets.py`

**API:**

```python
from pathlib import Path
from qwen_mtp_probe.datasets import load_chat_jsonl

rows = load_chat_jsonl(Path('data/examples/hermes_compact_traces.seed.jsonl'))
```

**Rules:**

- each line must be valid JSON;
- each row must have `messages`;
- each message must have `role` and `content`;
- allowed roles: `system`, `user`, `assistant`, `tool`;
- assistant content should not be empty.

**Verification:**

```bash
uv run --with pytest python -m pytest tests/test_datasets.py -q
```

---

### Task C3: Implement eval item loader

**Objective:** Load eval JSONL and fail fast on malformed eval items.

**Files:**
- Modify: `src/qwen_mtp_probe/datasets.py`
- Modify: `tests/test_datasets.py`

**API:**

```python
from qwen_mtp_probe.datasets import load_eval_jsonl
items = load_eval_jsonl(Path('data/eval/hermes_v0_eval.seed.jsonl'))
```

**Required keys:**

```python
{'id', 'input', 'expected_behavior', 'scorer'}
```

**Verification:**

```bash
uv run --with pytest python -m pytest tests/test_datasets.py -q
```

---

## Stage D: Evaluation harness before training

### Task D1: Add simple rule-based eval harness

**Objective:** Score generated outputs on cheap deterministic checks before using LLM judges.

**Files:**
- Create: `src/qwen_mtp_probe/eval_usecase.py`
- Create: `tests/test_eval_usecase.py`

**Scorers to implement first:**

- `tool_use_required`: output contains `ACTION` or configured tool-call marker.
- `repo_inspection_required`: output indicates reading/searching files before claims.
- `verification_required`: output mentions verification step/result before success claim.
- `concise_final_required`: final response under configured token/word threshold.
- `no_unnecessary_clarification`: penalize questions when action is obvious.

**Verification:**

```bash
uv run --with pytest python -m pytest tests/test_eval_usecase.py -q
```

---

### Task D2: Add baseline eval runner shell

**Objective:** Produce a report shape before any model integration.

**Files:**
- Create: `scripts/run_hermes_eval.py`
- Create: `reports/hermes-v0-baseline-template.json`

**Report shape:**

```json
{
  "run_name": "baseline-template",
  "model": null,
  "eval_path": "data/eval/hermes_v0_eval.seed.jsonl",
  "items": 0,
  "scores": {},
  "latency": {},
  "tokens": {},
  "cost_per_successful_task": null
}
```

**Verification:**

```bash
PYTHONPATH=src uv run python scripts/run_hermes_eval.py \
  --eval data/eval/hermes_v0_eval.seed.jsonl \
  --output reports/hermes-v0-baseline-template.json
```

Expected: report written.

---

## Stage E: Training entrypoint skeleton

### Task E1: Add SFT trainer skeleton

**Objective:** Create a safe dry-run trainer entrypoint before GPU training.

**Files:**
- Create: `src/qwen_mtp_probe/train_sft.py`
- Create: `tests/test_train_sft_config.py`

**Requirements:**

- load YAML config;
- load train/eval JSONL paths;
- support `--dry-run`;
- print model/config/dataset counts;
- do not download model in dry-run.

**Verification:**

```bash
PYTHONPATH=src uv run --with pyyaml python -m qwen_mtp_probe.train_sft \
  --config configs/qwen36-hermes-v0-sft.yaml \
  --dry-run
```

Expected: exits 0 and prints dataset/config summary.

---

### Task E2: Add Modal training runbook stub

**Objective:** Document how to launch training without local client timeout killing the run.

**Files:**
- Create: `docs/MODAL_TRAINING_RUNBOOK.md`

**Include:**

- use Modal Volume for datasets/checkpoints;
- launch as durable background/detached job;
- monitor logs by app id;
- save checkpoints frequently;
- never report success until checkpoint exists and eval report is written.

---

## Stage F: MTP refresh after SFT

### Task F1: Add post-SFT MTP refresh plan stub

**Objective:** Keep MTP in the right place: after main behavior SFT.

**Files:**
- Create: `docs/plans/hermes-agent-v0-mtp-refresh.md`

**Content:**

- input checkpoint: `v0-sft-main`;
- load base + adapter/merged checkpoint;
- attach manual MTP module if HF drops it;
- train MTP-only with future-token CE;
- export `mtp-refresh.safetensors`;
- assemble full checkpoint;
- serve normal and MTP modes;
- compare cost/successful task.

---

## Stage G: Preference/RL later, not now

### Task G1: Add preference data placeholder

**Objective:** Prepare for DPO/SimPO without doing RL prematurely.

**Files:**
- Create: `data/examples/hermes_preference_pairs.seed.jsonl`
- Create: `docs/PREFERENCE_TUNING_NOTES.md`

**Rules:**

- only use after v0 SFT eval shows shaped but inconsistent behavior;
- chosen/rejected pairs should target compactness, tool correctness, verification discipline, and task success;
- GRPO only when reward is programmatic.

---

## Done criteria for this plan

This plan is complete when:

- repo has version history;
- docs preserve the collected strategy;
- dataset/eval conventions exist;
- seed examples exist;
- schema tests pass;
- v0 config exists;
- dry-run SFT entrypoint works without downloading the model;
- eval report skeleton can be generated;
- MTP/RL are documented as later stages, not blocking v0 SFT.

Only then start expensive GPU SFT.
