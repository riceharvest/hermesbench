# HF Qwen / TauBench / Hermes tool-use usability for Hermes v0 SFT

Scope: local samples only from `tmp/hf_samples/qwen_toolscale.json`, `tmp/hf_samples/taubench.json`, and `tmp/hf_samples/hermes_reasoning.json`. No network data was used.

Style target checked against `src/qwen_mtp_probe/ultra_compact.py` and `tests/test_data_alignment.py`:

- `ACTION tool {json}` for the next tool action when it is obvious.
- `SCRATCH<=32:` + blank line + `ACTION ...` or `FINAL:` when a short rationale is useful.
- `SCRATCH<=96:` only for GPT-5.5 teacher-style traces where preserving several high-value state steps is genuinely needed.
- Concise `FINAL:` after tool-result verification.
- No verbose `<think>`, XML tool-call wrappers, or raw transcript dumping.

## 1. Dataset verdicts

| Dataset | Local sample shape | Verdict | Why |
|---|---:|---|---|
| `qwen_toolscale` (`zake7749/Qwen-3.6-plus-agent-tool-calling-trajectory`) | 8 rows; domains: 7 bank, 1 ecommerce; OpenAI-like `tool_calls`; `reasoning_content` on many messages; `score`/`reward` fields | **Prototype only** | Useful for testing `reasoning_content` -> compact trace conversion and policy-heavy customer-service tool use, but not ready for direct v0 import. Sample includes low-quality rows (`score=0.666...`, `reward=0.0`), long user-side reasoning traces from simulated customers, domain-specific bank policies/tools, and write-action constraints that require careful confirmation filtering. |
| `taubench` (`jkazdan/taubench_traces_training_data`) | 8 full trajectories; 60 assistant tool-call messages; OpenAI-like `tool_calls`; no reasoning fields | **Import now, with filters and tool mapping** | Cleanest structure for v0 SFT: assistant tool calls already map to `ACTION name {json}`, natural assistant finals map to `FINAL:`, and tool outputs are explicit. Must filter/transform TauBench-specific `think` pseudo-tool, confirm-before-write turns, and train/eval leakage. Domain remains customer-service airline/retail-like, so mix proportion should be capped. |
| `hermes_reasoning` (`AmanPriyanshu/...hermes_reasoning_tool_use...`) | 8 rows; custom roles `reasoning`, `tool_call`, `tool_output`, `answer`; XML `<think>`, `<tool_call>`, `<answer>` | **Reject for direct v0 SFT; use only as a conversion stress test** | The sample trains the opposite behavior: explicit long hidden reasoning, XML wrappers, custom role names, sometimes multiple tool calls in one message, synthetic API/result content, and non-Hermes action grammar. A heavily curated subset could be used to test CoT compression, but direct import would contaminate v0 style. |

## 2. Mapping to Hermes compact traces

### OpenAI-style `tool_calls` (`qwen_toolscale`, `taubench`)

Assistant message with one tool call:

```text
content: null
reasoning_content: optional rationale
tool_calls: [{"function": {"name": "get_user_details", "arguments": "{...}"}}]
```

Convert to:

```text
ACTION get_user_details {...}
```

If `reasoning_content` contains a genuinely useful state check, compress it first:

```text
SCRATCH<=32:
Need the reservation list because the user has no reservation ID.

ACTION get_user_details {"user_id":"[REDACTED]"}
```

Rules:

- Parse `function.arguments` as JSON; output a JSON object, not a quoted JSON string.
- Drop OpenAI call ids (`id`, `tool_call_id`) unless needed to associate tool outputs during preprocessing.
- Preserve exactly one `ACTION` per assistant training target unless the Hermes runtime supports multi-action turns. Split multi-call assistant messages into sequential synthetic turns if safe; otherwise reject.
- For obvious lookup/continuation actions, omit scratch entirely.
- For TauBench `think` pseudo-tool: do **not** train as `ACTION think` unless Hermes intentionally exposes such a tool. Convert high-value thoughts to `SCRATCH<=32/96` attached to the next real action, or drop them.

### `reasoning_content` (`qwen_toolscale`)

Convert assistant-side `reasoning_content` to compact scratch only when it contributes one of:

- required policy gate (`authenticate by email first`, `must confirm before write`),
- entity disambiguation (`reservation/account ending in ...`),
- verification after tool results (`status is frozen`, `belongs to authenticated user`),
- refusal/transfer condition.

Drop repetitive planning, enumerated checklists, and any user-role `reasoning_content`. User-side rationale is not a target for assistant SFT.

### XML `<think>` / `<tool_call>` / `<answer>` (`hermes_reasoning`)

Map only after strict parsing:

- `<think>...</think>` -> compressed `SCRATCH<=32` or `SCRATCH<=96`; never keep XML or full chain-of-thought.
- `<tool_call>{"name":"tool","arguments":{...}}</tool_call>` -> `ACTION tool {...}`.
- Multiple `<tool_call>` blocks in one message -> split into ordered single-action turns when tool outputs exist and semantics are independent; otherwise reject.
- `<tool_response>` messages remain tool observations in the conversation context, not assistant targets.
- `<answer>text</answer>` -> `FINAL: text` after removing wrappers and verifying against preceding tool output.

## 3. Compression rules that preserve correctness

1. **Keep the next external action exact.** Tool name and JSON arguments are the highest-value label. If the action is already determined by the user and context, use action-only.
2. **Keep only decision pivots.** Scratch may mention authentication state, selected entity, policy constraint, missing required field, confirmation status, or checked tool result.
3. **Prefer `SCRATCH<=32`.** Most samples need one sentence. Examples: “Need to authenticate by email before account changes.” or “The matching return leg is IAH->EWR; user confirmed write.”
4. **Use `SCRATCH<=96` sparingly for teacher traces.** Allowed when a conversion would otherwise lose a multi-step dependency such as: tool result A identifies candidate entities, tool result B verifies constraints, user confirmation authorizes write, then action C executes.
5. **Never preserve verbose private deliberation.** Delete self-talk (“Okay”, “let me think”), repeated restatement, speculative “should return”, and numbered hidden reasoning.
6. **Post-tool responses must be verified.** `FINAL:` should summarize only fields present in tool outputs or provided by the user. Do not include raw JSON dumps unless the user requested raw data.
7. **Writes need explicit confirmation.** Any database/state update action should have either a previous clear user confirmation or be converted to a confirmation-seeking `FINAL:` instead of `ACTION`.
8. **Redact sample secrets and PII-like values.** Emails, user/client/account/card/payment/reservation IDs, dates of birth, addresses, and URLs should be redacted in reports and optionally normalized in training if not semantically needed.

## 4. Before -> after examples from sampled rows

### Example A: Qwen `reasoning_content` + OpenAI tool call

Before (sample row with email lookup, redacted):

```text
reasoning_content: The user has provided their email address. I need to authenticate them by finding their client ID using this email address.
tool_calls: find_client_id_by_email arguments="{\"email\":\"[REDACTED]\"}"
```

After:

```text
ACTION find_client_id_by_email {"email":"[REDACTED]"}
```

Rationale: the next action is obvious; no scratch is needed.

### Example B: Qwen confirmation-sensitive bank action

Before (representative sampled bank flow):

```text
reasoning_content: User wants to unfreeze checking account ending in [REDACTED]. Need authenticate, find account, check status, and get explicit confirmation before unfreezing.
assistant content: Could you please provide your email address associated with your bank account?
```

After:

```text
SCRATCH<=32:
Bank policy requires email authentication before account lookup or unfreeze.

FINAL: I can help with that. Please provide the email address associated with your bank account so I can authenticate you first.
```

Rationale: preserve the policy gate, not the full checklist.

### Example C: TauBench OpenAI tool call

Before:

```text
user: My user ID is [REDACTED], but I don't remember the reservation ID.
tool_calls: get_user_details arguments="{\"user_id\":\"[REDACTED]\"}"
```

After:

```text
ACTION get_user_details {"user_id":"[REDACTED]"}
```

Rationale: lookup is directly requested by context.

### Example D: TauBench pseudo-tool `think` before real action

Before:

```text
tool_calls: think arguments="{\"thought\":\"The reservation with ID [REDACTED] has a flight from IAH to EWR on [REDACTED], matching the user's return flight from Texas to Newark.\"}"
```

After, if the next real action is available:

```text
SCRATCH<=32:
Selected the matching IAH->EWR return leg for the requested Texas-to-Newark change.

ACTION search_onestop_flight {"origin":"IAH","destination":"EWR","date":"[REDACTED]"}
```

If no next real action is present, drop this as an assistant target. Do not train `ACTION think` unless `think` is an approved Hermes tool.

### Example E: Hermes XML `<think>` + `<tool_call>` + `<answer>`

Before:

```xml
<think>
Okay, the user wants to search for 'laptops' on Tmall and retrieve the second page of results... page=2...
</think>
<tool_call>
{"name":"tmall_search_by_keyword","arguments":{"page":2,"keyword":"laptops"}}
</tool_call>
```

After:

```text
ACTION tmall_search_by_keyword {"page":2,"keyword":"laptops"}
```

Post-tool answer before:

```xml
<answer>The LinkedIn page for ABC Corporation shows ... founded in [REDACTED] ...</answer>
```

After:

```text
FINAL: ABC Corporation is an IT services company in San Francisco, CA, founded in [REDACTED] with 11-50 employees. Its listed specialties include cloud computing, SaaS, and IT consulting.
```

Rationale: remove XML and hidden reasoning; answer only from tool response.

## 5. Filters and risks

### Quality fields and rewards

- `qwen_toolscale` exposes `score` and `reward`; sampled values include `score=0.666...` and `reward=0.0`. Do not import all rows blindly. Suggested filter: require high score/reward, successful terminal state, and valid final/tool sequence.
- `taubench` sample has no score/reward, so quality must be inferred from trajectory validity, policy compliance, and tool-result consistency.
- `hermes_reasoning` sample has no quality signal and contains style-incompatible traces; reject direct import.

### Domain mismatch

- Qwen sample is mostly bank customer-service; TauBench sample is airline/travel service; Hermes sample is broad synthetic API use.
- These are useful for tool discipline and policy gates, but they do not directly match Hermes Agent local tools (`read_file`, `terminal`, `patch`, `web_search`, etc.). Either train them as generic function-calling only, map to a sandbox tool namespace, or mix at a low ratio with native Hermes traces.

### Long reasoning / CoT contamination

- Qwen `reasoning_content` and Hermes `<think>` are verbose and often include self-talk. Direct import would teach long private CoT.
- Strip all `<think>` tags and compress to compact scratch; prefer action-only when the decision is obvious.
- Reject rows whose correctness depends on unstated reasoning that cannot be safely compressed.

### Confirmation-before-write

- Bank and TauBench flows include write tools such as unfreeze/update/booking/cancel operations.
- Require a preceding explicit user confirmation for every write `ACTION`. If absent, convert the assistant target to a `FINAL:` asking for confirmation.
- Preserve a short scratch note for high-risk writes, e.g. “User confirmed downgrade; write is authorized.”

### Train/eval leakage

- TauBench is commonly used as an agent benchmark family. Importing raw trajectories can contaminate evals if the same tasks/users/reservations appear in evaluation.
- Keep a dataset fingerprint (repo, split, ids if available), de-duplicate against evaluation prompts and tool-result objects, and avoid training on any rows that overlap planned TauBench eval scenarios.
- Redact or normalize IDs and PII-like fields to reduce memorization.

### Parser and schema risks

- OpenAI arguments are stored as strings; invalid JSON must reject the row.
- Multiple tool calls in one assistant message should be split or rejected according to Hermes runtime semantics.
- `taubench` has `content: null` system messages in samples; ensure preprocessing tolerates null content.
- `hermes_reasoning` custom roles (`reasoning`, `tool_call`, `answer`) need role normalization; do not pass them through as-is.

## Recommended next action

1. Add an offline converter prototype for `taubench` first: OpenAI `tool_calls` -> `ACTION`, text assistant -> `FINAL:`, filter `think` pseudo-tool and writes without confirmation.
2. Use `qwen_toolscale` as a small prototype for `reasoning_content` compression after filtering to successful/high-reward rows.
3. Keep `hermes_reasoning` out of v0 SFT except for a separate red-team/conversion test suite that verifies `<think>` and XML wrappers are removed.
