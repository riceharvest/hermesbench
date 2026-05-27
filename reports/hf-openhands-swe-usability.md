# HF OpenHands/SWE usability + compact-CoT conversion report for Hermes v0 SFT

Scope: local samples only, no network inspection. Samples read from `tmp/hf_samples/openhands_sft.json`, `tmp/hf_samples/swe_zero.json`, and `tmp/hf_samples/nebius_swe.json`. Style contract checked against `src/qwen_mtp_probe/ultra_compact.py` and `tests/test_data_alignment.py`: assistant targets must be `ACTION tool {json}`, `SCRATCH<=32` + blank line + ACTION/FINAL, `SCRATCH<=96` only for GPT-5.5 teacher traces, or `FINAL:`.

## 1. Dataset verdicts

| Dataset sample | Local sample facts | Verdict | Rationale |
|---|---:|---|---|
| `SWE-Gym/OpenHands-SFT-Trajectories` (`openhands_sft.json`, split `train.success.oss`) | 8 rows; `messages`; 78 `str_replace_editor`, 34 `execute_bash`, 8 `finish`; no per-row license in sample | **Import now, after deterministic conversion + metadata/license gate** | Best fit: already successful OpenHands trajectories, simple XML tool format, concise enough action supervision after stripping verbose narration. Needs path normalization away from `/workspace/...`, tool remapping, removal of raw system/tool docs, and license/provenance checks from upstream metadata before large-scale import. |
| `nvidia/SWE-Zero-openhands-trajectories` (`swe_zero.json`, split `train`) | 8 rows; `trajectory` with OpenAI-style `tool_calls`; licenses: 7 MIT, 1 BSD-3-Clause; 211 `str_replace_editor`, 108 `execute_bash`, 23 `think`, 8 `finish`; non-empty `model_patch`; no success/pass field in sample | **Prototype only** | Tool calls are structured and convertible, and licenses in sample are permissive. But the sample includes very verbose phase/reading prose and private `think` calls; there is no sampled success field, so quality cannot be gated without external eval/pass metadata. Use for converter prototyping and import only rows joined to verified success/pass data. |
| `nebius/SWE-agent-trajectories` (`nebius_swe.json`, split `train`) | 8 rows; `target=false` for all sampled rows; 5 `submitted (exit_context)`, 3 `submitted`; repeated instances; fenced SWE-agent shell/editor commands; eval logs present | **Reject for v0 SFT targets; keep only as negative/error-analysis source** | The sampled rows are explicitly unsuccessful (`target=false`) and include hallucinated/failed navigation, raw shell transcripts, duplicated tasks, and SWE-agent pseudo-editor syntax. Do not train Hermes v0 to imitate these assistant targets. If used at all, mine isolated negative preference examples or failure filters, not SFT actions. |

## 2. Concrete conversion mapping to Hermes tools

Hermes valid action format is parseable text:

```text
ACTION terminal {"command":"pytest -q","workdir":"/repo"}
```

The JSON object must be valid JSON and the tool name must be in the Hermes valid action set.

### OpenHands XML / OpenAI tool-call mapping

| Source tool/action | Source shape | Hermes target | Notes |
|---|---|---|---|
| `execute_bash` | XML `<function=execute_bash><parameter=command>...</parameter>` or `tool_calls[].function.name` | `ACTION terminal {"command":"...","workdir":"..."}` | Add `workdir` when command begins with `cd /path && ...`; preserve foreground/background intent using Hermes `background`/`notify_on_complete` only when source truly starts a long-lived process. Prefer direct `terminal` over embedding pseudo-interactive polling patterns. |
| `str_replace_editor` `view` on file | `{"command":"view","path":"/path/file.py"}` | `ACTION read_file {"path":"/path/file.py","offset":1,"limit":500}` | If the source viewed a specific range, map to offset/limit. Do not train `cat`, `head`, `tail` wrappers when `read_file` is available. |
| `str_replace_editor` `view` on directory | `{"command":"view","path":"/path"}` | `ACTION search_files {"target":"files","pattern":"*","path":"/path","limit":50}` | For intent to list repository tree, use `search_files` file mode. For targeted discovery, use content/file glob searches. |
| `str_replace_editor` `str_replace` | old/new string edit | `ACTION patch {"path":"...","old_string":"...","new_string":"..."}` | Preserve narrow context. Reject edits where old/new context is incomplete or ambiguous. |
| `str_replace_editor` `insert` | insert at line | `ACTION patch {"path":"...","old_string":"<nearby context>","new_string":"<context+insert>"}` | Convert line-based edits into context-based replace patches; reject if context cannot be reconstructed. |
| `str_replace_editor` `create` | create file | `ACTION write_file {"path":"...","content":"..."}` | Only for genuine requested/source-created files. Avoid training creation of throwaway reproduction files unless task requires it. |
| `finish` | no args | `FINAL: ...` | Replace with concise verified summary. No raw patch dump unless asked. |
| `think` (SWE-Zero) | private thought tool | `SCRATCH<=32` or drop | Never preserve hidden/private CoT. Keep only a short rationale if it directly explains why the next tool is needed. Usually drop and emit ACTION-only. |

### SWE-agent command mapping

| Source command | Hermes target | Notes |
|---|---|---|
| `open <path> [line]` | `ACTION read_file {"path":"<path>","offset":<line or 1>,"limit":120}` | Replace pseudo-editor window state with explicit path/range. |
| `goto <line>`, `scroll_down`, `scroll_up` | `ACTION read_file` with recalculated `offset`/`limit` | Only usable if current open file is known; otherwise reject the turn. |
| `search_dir <term> [dir]` | `ACTION search_files {"target":"content","pattern":"<term>","path":"<dir or .>","limit":50}` | Escape/quote regex-sensitive literals when needed. |
| `search_file <term> [file]` | `ACTION search_files {"target":"content","pattern":"<term>","path":"<file>","limit":50}` | Use `file_glob` when source searched by filename pattern. |
| `find_file <name> [dir]` | `ACTION search_files {"target":"files","pattern":"<glob>","path":"<dir or .>","limit":50}` | Map exact names to glob as appropriate. |
| `edit ... end_of_edit` | `ACTION patch ...` or `ACTION write_file ...` | Convert to deterministic patch only if exact surrounding file content is available. Reject transcript-only edits that rely on editor state. |
| Plain shell (`python`, `pytest`, `ls`, `rm`, package commands) | `ACTION terminal {"command":"...","workdir":"..."}` | Prefer Hermes-native `search_files`/`read_file` over shell for reads/searches. Keep shell for tests/builds/git/package managers. |
| `submit` | `FINAL: ...` | Only after verification. In failed Nebius sample rows, do not convert submitted turns into positive final targets. |

## 3. Reasoning compression rules

### ACTION-only

Use `ACTION tool {json}` with no scratch when the next operation is obvious from the user request or the previous observation:

- initial repository/file discovery;
- reading a named file or directory;
- running a provided reproduction command/test;
- opening the exact file named by a traceback/search result;
- applying an obvious narrow patch after the edit location is known;
- rerunning the same test after an edit;
- final tool call equivalents such as OpenHands `finish` become `FINAL:` rather than ACTION.

### `SCRATCH<=32`

Use a short rationale only when it prevents ambiguous imitation:

- choosing between several likely files/modules;
- explaining why a test should be rerun with a narrower command;
- linking an error line to a specific code path;
- summarizing the invariant that the patch should preserve.

Keep it under 32 words and then immediately emit ACTION/FINAL. Example pattern:

```text
SCRATCH<=32:
The traceback points to invariant wrapping, and the found file contains that checker code.

ACTION read_file {"path":"/repo/icontract/_checkers.py","offset":430,"limit":120}
```

### `SCRATCH<=96`

Reserve for high-value teacher traces only (`hermes-gpt55-compact-v0`) when the trace genuinely teaches multi-step debugging strategy that cannot be compressed to 32 words. Do **not** use `SCRATCH<=96` for normal v0 ultra-compact rows; `validate_ultra_compact_assistant` rejects it.

### Reject / drop

Reject or drop turns/rows when:

- sampled success is false or absent and cannot be joined to verified pass/fail data;
- tool action cannot be mapped to a Hermes tool with valid JSON;
- edit depends on hidden editor state or lacks exact file context;
- source contains verbose private CoT, phase narratives, raw transcripts, or speculative explanations not needed for the next action;
- source path assumes `/workspace/...` when the target environment requires discovery or a provided repo root;
- raw secrets or credentials match high-risk patterns; redact as `[REDACTED]` if retaining surrounding text is necessary;
- row appears in or near evaluation benchmarks/tasks targeted for held-out SWE-bench style eval.

## 4. Before → after compact examples from sampled rows

### Example 1: OpenHands directory view → Hermes file search

Before (OpenHands XML, `openhands_sft.json`):

```xml
<function=str_replace_editor>
<parameter=command>view</parameter>
<parameter=path>/workspace/python__mypy__0.820</parameter>
</function>
```

After:

```text
ACTION search_files {"target":"files","pattern":"*","path":"/workspace/python__mypy__0.820","limit":50}
```

### Example 2: OpenHands reproduce command → Hermes terminal

Before (OpenHands XML, `openhands_sft.json`):

```xml
<function=execute_bash>
<parameter=command>mypy --follow-imports=silent --show-error-codes --warn-unused-ignores --warn-redundant-casts --strict --show-traceback /workspace/python__mypy__0.820/reproduce_error.py</parameter>
</function>
```

After:

```text
ACTION terminal {"command":"mypy --follow-imports=silent --show-error-codes --warn-unused-ignores --warn-redundant-casts --strict --show-traceback /workspace/python__mypy__0.820/reproduce_error.py","workdir":"/workspace/python__mypy__0.820"}
```

### Example 3: SWE-Zero private `think` + directory view → ACTION-only

Before (`swe_zero.json`): assistant logs a long `think` about entity IDs, then calls:

```json
{"name":"str_replace_editor","arguments":"{\"command\": \"view\", \"path\": \"/workspace\"}"}
```

After:

```text
ACTION search_files {"target":"files","pattern":"*","path":"/workspace","limit":50}
```

The private thought is dropped because repository discovery is obvious from the uploaded path.

### Example 4: SWE-Zero file read → Hermes read_file

Before (`swe_zero.json`):

```json
{"name":"str_replace_editor","arguments":"{\"path\": \"/workspace/jbradberry__universe__unknown/README.rst\", \"command\": \"view\"}"}
```

After:

```text
ACTION read_file {"path":"/workspace/jbradberry__universe__unknown/README.rst","offset":1,"limit":500}
```

### Example 5: Nebius SWE-agent failed trajectory → reject or negative-only

Before (`nebius_swe.json`, row with `target=false`):

````text
We have successfully replicated the bug... Let's open the `_checkers.py` file...

```
open icontract/icontract/_checkers.py
```
````

Observed next result in the sampled transcript: `File icontract/icontract/_checkers.py not found`.

After for positive SFT:

```text
REJECT: unsuccessful row (`target=false`) and action used an invalid path after a prior search result.
```

If mined as a negative preference pair, the corrected compact chosen action would be:

```text
ACTION read_file {"path":"/icontract/icontract/_checkers.py","offset":1,"limit":120}
```

## 5. Filters and risks

### Required import filters

1. **Success/pass gate**
   - OpenHands sample is from `train.success.oss`; keep only rows from confirmed success splits or rows with explicit pass metadata.
   - SWE-Zero sample lacks success fields; require an external join to verified evaluation status before SFT import.
   - Nebius sample has `target=false`; reject for positive SFT.
2. **License/provenance gate**
   - SWE-Zero sample includes permissive row licenses (MIT/BSD-3-Clause), but large-scale import still needs row-level license allowlist.
   - OpenHands sample lacks per-row license locally; require upstream dataset/repo license and underlying repo license resolution before import.
   - Reject unknown, copyleft-incompatible, or missing license rows unless separately cleared.
3. **Tool validity gate**
   - Every assistant target with an action must match `^ACTION <valid_tool> {json}$` and JSON must parse as an object.
   - Allowed converted tools should primarily be `terminal`, `read_file`, `search_files`, `patch`, `write_file`, and `process` for background sessions.
4. **Verbosity/CoT gate**
   - Drop OpenHands/SWE-Zero phase prose, private `think`, and multi-paragraph explanations.
   - Keep only ACTION-only, `SCRATCH<=32`, rare `SCRATCH<=96` teacher traces, and concise `FINAL:`.
5. **Edit reconstructability gate**
   - Convert edits only when exact target path and context can be reconstructed. Reject line-state editor diffs that cannot be made into safe `patch`/`write_file` calls.
6. **Leakage gate**
   - Deduplicate by `instance_id`, repo, issue text, and generated patch fingerprints.
   - Exclude tasks overlapping intended SWE-bench/SWE-rebench evaluation sets.
   - Watch Nebius repeated sampled instances (`ResearchObject__ro-crate-py-168`, `Stratoscale__skipper-164`) as a signal to de-duplicate aggressively.
7. **Secret/safety gate**
   - Apply the existing high-risk secret patterns from `tests/test_data_alignment.py` (`sk-*`, DB URLs with passwords, private keys) and redact retained snippets as `[REDACTED]`.

## Bottom line

- **Import now:** `SWE-Gym/OpenHands-SFT-Trajectories`, but only via deterministic converter and license/provenance gate.
- **Prototype only:** `nvidia/SWE-Zero-openhands-trajectories`; promising structured tool calls, but needs success metadata and heavy compression.
- **Reject:** `nebius/SWE-agent-trajectories` for positive Hermes v0 SFT because the local sample is unsuccessful (`target=false`) and tool/state mismatch is high.
