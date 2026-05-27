# HF terminal-agent dataset usability for Hermes v0 SFT

Inspection target: public Hugging Face datasets close to Hermes Agent's behavior-first v0 SFT target. I inspected repository metadata, schemas, and at least 5 sampled rows per dataset using `huggingface_hub` + DuckDB parquet sampling. No training data or config was imported/modified.

Target style constraint: compact GPT-like assistant turns only:

```text
ACTION tool {json}
SCRATCH<=32:
short situational note

ACTION tool {json}
SCRATCH<=96:
only for imported high-value teacher traces that genuinely need more context

FINAL: concise verified answer
```

No verbose CoT, no raw `<think>`, no source-specific tool wrappers, parseable action JSON only.

## Dataset verdicts

| Dataset | Sampled schema / size | Terminal relevance | Direct usability | Verdict |
|---|---:|---|---|---|
| `open-thoughts/OpenThoughts-Agent-v1-SFT` | `conversations`, `agent`, `model`, `model_provider`, `date`, `task`, `episode`, `run_id`, `trial_name`; 15,209 train rows in one parquet shard | Very high: Terminal-Bench-like Linux command-line task trajectories with repeated terminal state observations and shell command batches | Not direct: assistant emits JSON with verbose `analysis`, verbose `plan`, `commands[{keystrokes,duration}]`, `task_complete`; some turns include plain explanatory text instead of JSON | **Use selectively.** Best of the three for Hermes terminal behavior after aggressive turn-level conversion and quality filters. |
| `AmanPriyanshu/tool-reasoning-sft-CODING-text_to_terminal_v2-sft-tool-use-agent-data-cleaned-rectified` | `messages[{role,content}]`; card says 114,201 train rows / 9 parquet shards; sampled first shard has 12,689 rows | High for single-shot bash command synthesis | Not direct: every sampled row has `system`, `user`, `reasoning`, `tool_call`; `reasoning` is long `<think>` with alternatives/tradeoffs; tool is `run_bash` in XML-ish `<tool_call>` | **Use cautiously.** Good source for short command-selection examples, but strip nearly all reasoning and filter risky commands. |
| `smolagents/hermes-function-calling-v1-formatted-code-agent` | configs: `func_calling` 1,893 rows, `func_calling_singleturn` 1,893, `glaive_func_calling` 5,209; sampled `func_calling` schema includes `id`, `category`, `subcategory`, `task`, `messages`, `chat_template_kwargs` | Low for terminal/repo behavior; mostly domain API/function calls in Python `<code>` blocks | Not direct: assistant uses `<code>print(func(...))</code>` and `final_answer(...)`; many synthetic smart-home/customer-service tasks | **Secondary/low priority.** Useful only for generic function-call syntax discipline, not Hermes terminal specialization. |

## Observed quality notes

### 1. `open-thoughts/OpenThoughts-Agent-v1-SFT`

Sample observations:

- First shard row count: 15,209.
- Sampled 5 rows, each multi-turn. Roles are `user` and `assistant`; sampled rows had 34 user turns and 34 assistant turns total.
- Sampled row JSON lengths ranged from ~9.3k to ~19.7k chars; assistant turns were often ~700-1,900 chars.
- User messages often embed a long system/task prompt plus terminal output. Assistant turns usually contain JSON such as:
  - `analysis`: current-state narrative.
  - `plan`: step-by-step rationale.
  - `commands`: array of terminal keystrokes.
  - `task_complete`: boolean.
- Terminal relevance is excellent: `find`, `ls`, `mkdir`, `stat`, output capture, file verification, shell polling.
- Main risk: some trajectories create fixtures "if needed" even when task says fixtures are preseeded; this may teach unnecessary environment mutation. Some turns are verbose or plain natural language rather than valid JSON.

Usability: high after conversion. Import only action/final assistant turns whose command/result sequence is coherent and verified.

### 2. `AmanPriyanshu/tool-reasoning-sft-CODING-text_to_terminal_v2-sft-tool-use-agent-data-cleaned-rectified`

Sample observations:

- Card metadata: Apache-2.0, tags include `terminal`, `bash`, `shell`, `command-line`, `tool-use`, `thinking`; 114,201 examples.
- Sampled first parquet shard: 12,689 rows.
- Sampled 5 rows. All used `system`, `user`, `reasoning`, `tool_call` roles.
- Reasoning in sampled rows ranged from ~1.8k to ~2.7k chars and is explicitly requested by the system prompt: "reason through the task inside `<think>...</think>`".
- Tool calls are easy to parse, e.g. `<tool_call>{"name":"run_bash","arguments":{"command":"find . -mindepth 1 -maxdepth 1 -type d"}}</tool_call>`.
- Some sampled commands are broad/risky in real agents, e.g. `find / ...`, which may be acceptable as command-syntax training but poor default Hermes behavior.

Usability: medium. Strong for command selection, weak for multi-turn verification. Treat as mined single-action examples with almost all CoT removed.

### 3. `smolagents/hermes-function-calling-v1-formatted-code-agent`

Sample observations:

- Multiple configs; sampled `func_calling` first parquet (1,893 rows).
- Sampled 5 rows. Roles: `user`, `assistant`, `tool`; typically one assistant `<code>` block, one tool observation, then one assistant `final_answer(...)` block.
- Task domains in sampled rows were smart home / IoT, not terminal or repo work.
- Assistant actions are Python code snippets, e.g. `print(get_camera_live_feed(...))`, not OpenAI-style JSON tool calls or Hermes Agent actions.
- Finals are verbose and often synthetic customer-service prose.

Usability: low for the current terminal-agent v0 objective. Only consider a tiny filtered slice if generic function-call ordering is needed.

## Conversion mapping

### Tool/action mapping

| Source pattern | Target |
|---|---|
| OpenThoughts `commands[{"keystrokes":"...\n","duration":x}]` | `ACTION terminal {"command":"...","timeout":N,"workdir":"..."}` when command is a shell command. Drop `duration`; map long-running commands to conservative `timeout`. |
| OpenThoughts empty `commands` with wait duration | Usually drop; if retaining process-polling behavior, map to `ACTION process {"action":"poll","session_id":"..."}` only when session context is explicit. |
| OpenThoughts `task_complete:true` with no command need | `FINAL: ...` concise summary based on verified terminal output. |
| Aman `<tool_call>{"name":"run_bash","arguments":{"command":cmd}}</tool_call>` | `ACTION terminal {"command":cmd}`. Add `timeout` only when command type warrants it. |
| Smolagents `<code>print(fn(arg=...))</code>` | Prefer `ACTION execute_code {"code":"print(fn(...))"}` only if the function namespace is available in the training context. Otherwise map to synthetic domain tool only if adding such tools is intended; do not map these to terminal. |
| Smolagents `<code>final_answer("""...""")</code>` | `FINAL: ...` after trimming to the directly relevant result. |
| Source terminal observations embedded in next user turn | Preserve as `tool`/observation context only if the training schema supports it; otherwise fold the minimum verified fact into a compact scratch/final. |

### Compression rules

1. Delete raw `<think>`, OpenThoughts `analysis`, and OpenThoughts `plan` by default.
2. Emit action-only whenever the user request directly determines the command.
3. Use `SCRATCH<=32` only when it improves tool choice, e.g. remembering constraints like "exclude ignored dir; capture stdout+stderr; verify file".
4. Use `SCRATCH<=96` only for high-value imported teacher traces where multiple constraints or previous observations are genuinely needed; tag the row as GPT-style teacher, not normal ultra-compact.
5. Collapse command batches into either:
   - one safe shell block in a single `ACTION terminal`, if the source intentionally required a single shell session; or
   - multiple separate assistant action turns only if observations between commands are preserved.
6. Convert final answers to one or two sentences: status, key result, verification. Remove customer-service filler and markdown lists unless needed.
7. Reject or rewrite source examples whose command has placeholders (`example`, `WORD`, `PATTERN`) but the user did not provide the placeholder value.
8. Prefer Hermes-native tools over terminal when source command is only reading/searching repo files: `read_file`, `search_files`, `patch`, `write_file`. But keep `ACTION terminal` for genuine shell semantics (`find`, permissions, pipes, process control).

## Before → after examples

### Example 1: OpenThoughts terminal search + capture

Source shape:

```json
{
  "analysis": "I'm in the /workspace directory as root. I need to search for files matching 'fileName*.txt' ... excluding './ignored_directory' ... capture both stdout and stderr ...",
  "plan": "1. Check current directory structure ... 2. Ensure /output ... 3. Run find ...",
  "commands": [
    {"keystrokes":"ls -la\n","duration":0.1},
    {"keystrokes":"mkdir -p /output\n","duration":0.1},
    {"keystrokes":"find . -path './ignored_directory' -prune -o -type f -iname 'fileName*.txt' -print > /output/command_capture.txt 2>&1\n","duration":1.0}
  ]
}
```

Compact target:

```text
SCRATCH<=32:
Need a single shell session, prune ignored_directory, capture stdout+stderr, then verify output file.

ACTION terminal {"command":"mkdir -p /output && find . -path './ignored_directory' -prune -o -type f -iname 'fileName*.txt' -print > /output/command_capture.txt 2>&1 && ls -l /output/command_capture.txt","workdir":"/workspace","timeout":30}
```

### Example 2: OpenThoughts verified final

Source shape:

```text
Let me analyze what has happened:
1. The find command was executed successfully ...
2. /output/command_capture.txt exists and is 46 bytes ...
I should check contents before marking complete ...
```

Compact target:

```text
ACTION terminal {"command":"wc -c /output/command_capture.txt && sed -n '1,20p' /output/command_capture.txt","workdir":"/workspace","timeout":10}
```

After observation:

```text
FINAL: Command completed successfully; `/output/command_capture.txt` exists and contains the captured output (46 bytes).
```

### Example 3: Aman text-to-terminal directory listing

Source shape:

```text
<think>
User intent: list only the directories that are immediate children ...
Possible approaches and trade-offs: ls -d */, printf, find ...
</think>
<tool_call>{"name":"run_bash","arguments":{"command":"find . -mindepth 1 -maxdepth 1 -type d"}}</tool_call>
```

Compact target:

```text
ACTION terminal {"command":"find . -mindepth 1 -maxdepth 1 -type d"}
```

### Example 4: Aman permissions search

Source shape:

```text
<think>
The user wants files whose permission bits are owner/group read+write and others read only ... exact mode 664 ...
</think>
<tool_call>{"name":"run_bash","arguments":{"command":"find . -perm 664"}}</tool_call>
```

Compact target:

```text
SCRATCH<=32:
Exact permission mode is 664: owner/group read-write, others read-only.

ACTION terminal {"command":"find . -type f -perm 664"}
```

Note: add `-type f` because the user asked for files; filter/rewrite rows where the original command is under-specified.

### Example 5: Smolagents code-function call

Source shape:

```text
<code>
print(set_smart_light_color(room="living room", brightness="dim", color="warm"))
print(sync_lights_with_automation_system(room="living room"))
</code>
```

Compact target if the Python tool namespace is intentionally provided:

```text
ACTION execute_code {"code":"print(set_smart_light_color(room='living room', brightness='dim', color='warm'))\nprint(sync_lights_with_automation_system(room='living room'))"}
```

Otherwise reject for Hermes terminal-agent v0 because these are domain APIs, not terminal/repo tools.

## Recommended filters

### Common filters for all three

- Require parseable target action: `ACTION <valid Hermes tool> {json}`.
- Drop rows containing raw `<think>`, `analysis`, `plan`, `<tool_call>`, or `<code>` after conversion.
- Redact/skip possible credentials/secrets: API keys, bearer tokens, private keys, database URLs, `.env` dumps.
- Enforce style validation from `src/qwen_mtp_probe/ultra_compact.py`: normal rows start with `ACTION`, `FINAL:`, or `SCRATCH<=32`; imported teacher traces may use `SCRATCH<=96` only when justified.
- Reject huge source rows whose converted target still needs more than one compact scratch block.
- Deduplicate by normalized user instruction + target action command/tool args.
- Prefer examples with explicit verification after side effects.

### OpenThoughts-specific filters

- Keep terminal task rows with coherent command/observation/final loops.
- Prefer successful trajectories where final verification is present (`ls`, `wc`, `cat`, command exit status, file size, test output).
- Reject assistant turns that invent/create fixtures unless the user asked to create them.
- Reject rows whose commands assume `/workspace` unless the task explicitly says that; do not teach fixed container paths as a default.
- Split multi-command `commands` arrays carefully: only collapse into a single shell block when no intermediate observation is needed.
- Filter dangerous shell operations: broad `rm`, destructive chmod/chown, writes outside requested paths, privilege escalation, network downloads/execution.

### Aman-specific filters

- Keep rows where user asks for a concrete bash command and the command is complete without placeholders.
- Drop the long `reasoning` role entirely; optionally synthesize one short `SCRATCH<=32` from constraints.
- Reject broad filesystem scans (`find /`, `grep -R /`, etc.) unless the prompt explicitly requests whole-system search.
- Reject commands with unsafe side effects or commands that should ask for a missing pattern/value.
- Prefer robust variants when converting: quote patterns, use `-type f` when user says files, use `-print0`/`xargs -0` where filename safety matters.

### Smolagents-specific filters

- Keep only examples whose functions resemble available Hermes tools or can be represented as `execute_code` with a provided namespace.
- Drop long synthetic user narratives when they can be normalized to the actual tool request.
- Convert finals to concise result statements; drop customer-service phrasing.
- Do not use for terminal-command specialization unless a config/row actually contains code-agent terminal behavior; sampled `func_calling` rows did not.

## Risks

- **Verbose CoT contamination:** OpenThoughts and Aman both strongly reward long rationale unless stripped. Direct import would violate compact style.
- **Tool-surface mismatch:** OpenThoughts uses terminal-keystroke JSON; Aman uses `run_bash`; Smolagents uses Python `<code>` and domain functions. All require explicit adapters.
- **Unsafe defaults:** Some examples use broad filesystem roots, root shell contexts, or fixture creation. These can teach poor Hermes operational discipline.
- **Synthetic boilerplate:** Smolagents and Aman contain templated prompts and repetitive reasoning. Deduplication and downsampling are necessary.
- **Path bias:** `/workspace`, `/output`, Ubuntu/root assumptions are common in OpenThoughts. Preserve only when user/task context specifies them.
- **Observation schema mismatch:** Multi-turn terminal trajectories need a consistent representation of tool observations; flattening incorrectly can create impossible one-turn examples.

## Recommendation

1. Prioritize a small filtered OpenThoughts slice for Hermes-v0 terminal behavior, but only after writing a converter that emits validated compact targets and preserves verification turns.
2. Use Aman as a large single-command augmentation source after strict risk filtering and reasoning removal.
3. Treat Smolagents as low-priority for this v0 terminal-agent goal; use at most a small generic function-call slice if future training needs `execute_code`/function-call mechanics.
4. Do not import any of the three directly into `data/processed/hermes_v0_train.jsonl`.
