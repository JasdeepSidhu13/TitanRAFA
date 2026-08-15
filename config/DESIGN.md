# DESIGN.md — Research Agent Architecture & Decisions

This file is the source of truth for architecture. Reference it in prompts
instead of re-explaining design in prose each time.

---

## 1. Scenario

Banking startup research agent: takes a natural-language question, decides
which tools to call, synthesizes a cited answer, distinguishes retrieved
fact from model inference.

## 2. Components (LLM / Tools / Memory / Orchestrator)

- **LLM** — Groq-hosted model (see §3), used for planning and synthesis only.
  Never used for tool execution or state management.
- **Tools** — `WikipediaTool`, `ArxivTool` (Tier 1), `FREDTool` (Tier 3
  extension). Each implements a shared `Tool` interface and owns its own
  `RetryPolicy` (see `config/tool_policy.yaml`).
- **Memory** — `AgentState`. Working memory, scoped to a single run
  (`python agent.py "question"` → exit). Not persisted across invocations.
  Holds every step taken (tool, query, result, reasoning) so the planner
  doesn't re-decide from zero and dedup can check history before any call.
- **Orchestrator** — the loop in `agent.py`. Plain Python control flow, not
  an LLM call: planner → executor → sufficiency_check → refine-or-proceed
  → synthesizer.

## 3. LLM choice

**Groq free tier** (e.g. Llama 3.1-8b-instant) over local Ollama/llama.cpp.

**Tradeoff (for README):** local models add download/setup variance that's
incompatible with an unpaused, timed build and with a reviewer running
cold on unknown hardware. A hosted free tier is deterministic for both of
us. Cost: reviewer needs a free Groq key (documented in `.env.example`),
no payment required.

## 4. Orchestration pattern

**ReAct-lite over explicit `AgentState`**, not free-text ReAct parsing.

```
question -> planner(state) -> tool_calls
         -> executor(tool_calls) -> state.events.append(tool_result)
         -> sufficiency_check(state) -> refine (<=2 rounds) | proceed
         -> synthesizer(state) -> answer{mode, citations}
```

**Why:** free-text ReAct (model emits "Thought/Action/Observation" as
unstructured text, regex-parsed) makes Tier 2 tracing an afterthought
retrofitted onto strings. An explicit state object makes tracing free
(serialize `state.events`), makes dedup trivial (check events before
calling), and makes sufficiency a real function instead of a hopeful
prompt.

## 5. Memory model — event log, not a tool-results list

The Groq API is stateless; there is no server-side session. All continuity
comes from what is re-sent in each call, built from `AgentState`. State is
an **append-only event log**, not just a list of tool results — this is
required for Tier 2 traces to explain *why* the agent did what it did, not
just what it retrieved.

```python
# Run-level (in-memory AgentState; mirrored in trace run_header event)
run_id: str                 # uuid4 — NOT second-resolution timestamp,
                             # to avoid collision when Q4/Q6 run twice
                             # in quick succession for Tier 2 A/B
question: str
question_ref: str            # e.g. "Q4" — matches reference_questions.md
question_type: str           # canonical tag from reference_questions.md
                             # (e.g. multi_source_synthesis, speculative)
variant: "single_pass" | "refine"   # explicit, for Tier 2 auto-pairing
experiment_id: str | None    # optional batch-level id for Tier 2 pairing
refine_disabled: bool        # true when SINGLE_PASS=1
started_at: str
trace_schema_version: str    # bump whenever event shape changes —
                              # earlier outputs/ traces become unparseable
                              # by a later comparison tool otherwise
config: RunConfig            # model id + exact date/version pinned,
                              # temperature, decode params, policy file
                              # hash, prompt_version (so a diff caused by
                              # editing a prompt is attributable, not
                              # confused with a genuine behavior change)

# Terminal fields — set only at run end; written in run_complete event (§5e)
mode_final: "grounded" | "caveated" | "refused"   # synthesizer path only
outcome_final: "completed" | "aborted" | "out_of_scope" |
               "insufficient_evidence" | "degraded"
refusal_reason: str | None   # null unless mode_final=refused (§7)

events: list[AgentEvent]

# AgentEvent (union by kind)
# Every event has a STRUCTURAL id and a separate VOLATILE namespace —
# kept apart so the Tier 2 diff tool excludes timing/token noise by
# construction, not by a retrofitted normalization pass.
#   event_id: int             # monotonic, unique across ALL event kinds
#   kind: "run_header" | "run_complete" | "plan" | "answerability" |
#         "dedup_skip" | "tool_result" | "sufficiency" | "synthesize" |
#         "dropped_context" | "error"
#   refine_round: int
#   caused_by: int | None     # event_id of the plan/decision that led
#                              # to this event — MUST be set by emitter
#                              # per rules below; not inferred later
#   timing: {timestamp_ms, duration_ms}   # volatile, excluded from diff
#
#   tool_result adds: tool_name, query, normalized_query, ok, reason,
#     failure_class, source_id, content_full, content_for_synthesis,
#     truncated
#     failure_class (required when ok=False): timeout | http_429 |
#       parse_error | empty_result
#   sufficiency adds: passed, reason, matched_event_ids, rejected_event_ids,
#     rejected_reasons, rule_version
#   plan adds: tool_calls_proposed, tool_calls_after_validation,
#     planner_input_summary, validation_errors, repair_count, model_id
#     planner_input_summary: list[int] — event_ids visible in compact summary
#   synthesize adds: mode_model, mode_enforced, claims_raw, claims_validated,
#     context_event_ids, chars_fed, model_id
```

Use `event_id` for ordering, uniqueness, and sufficiency matching.
Use `source_id` for stable per-retrieval identity and citations only.
Do not conflate the two. Do not use `step_id` anywhere.

Export: `state.to_trace_dict()` → JSON; no string parsing later.

- **Stable IDs, assigned at ingest, not later:** every `tool_result` event
  gets a monotonic `event_id` and a stable `source_id` (e.g.
  `wikipedia:Title`, `arxiv:2301.12345`). Synthesizer citations reference
  `source_id` directly — no unverifiable free-text citations.
- **Two views of every tool result, both stored:** `content_full` (for
  synthesis + trace export) and `content_for_synthesis` (truncated to
  ~1500 chars, `truncated: true/false` recorded). Never store only the
  truncated version — citations must be traceable back to real content.
- **Planner call** — gets `question` + a *compact summary* of prior
  `tool_result` events (tool name + query + `source_id` only, not full
  content). The `plan` event records which `event_id`s were visible.
- **Sufficiency check** — deterministic Python rule, not an LLM call (see
  §5a for the relevance definition it must use).
- **Synthesizer call** — gets `question` + full `content_full` from every
  relevant event.
- **Dedup** — before any tool call, check `(tool_name, normalized_query)`
  against prior `tool_result` events. Normalization: lowercase, collapse
  whitespace, strip punctuation. A blocked call is logged as a
  `dedup_skip` event, not silently dropped.
- **`refine_round`** stored on every event (0..N). `SINGLE_PASS=1` → all
  events `refine_round=0`, `refine_disabled: true` in run header. This
  is what makes the Tier 2 A/B comparison a diff, not a manual reconciliation.

### caused_by — emitter requirements (not optional metadata)

Each event emitter **must** set `caused_by` at write time:

| Event kind | `caused_by` must point to |
|---|---|
| `tool_result` | the parent `plan` event's `event_id` that proposed this call |
| `sufficiency` | the `plan` event that triggered this sufficiency check |
| `dedup_skip` | the `plan` event that proposed the blocked call |
| `plan` | prior `sufficiency` or `answerability` event if refine-triggered; else `None` for first plan |
| `synthesize` | the final `sufficiency` event that passed, or the exhaustion checkpoint if caps hit |
| `dropped_context` | the `synthesize` preparation step that dropped the context |

Do not infer `caused_by` from list ordering during export or diff.

**Scope note for README:** memory here is working memory only, scoped to
one run. No persistence across invocations (out of scope per the brief).
Natural "what I'd do with more time" item: a SQLite-backed session log the
agent could consult for repeat/related questions.

## 5a. Sufficiency / relevance — defined mechanically, not left implicit

Sufficiency is **not** "any `ok=True` result," and it is **not** "N
`tool_result` events regardless of which tool produced them." A prior
build of this design passed sufficiency for cross-tool questions (Q4,
Q6 — tagged `multi_source_synthesis` and `cross_tool_synthesis` in
`config/reference_questions.md`) on two Wikipedia results alone, because the
count-based check never looked at *which tools* the evidence came from.
The planner never even attempted arXiv — sufficiency was satisfied
before it needed to. Define before coding:

- **Wikipedia:** page title/redirect match, or keyword overlap between
  question tokens and returned title+summary above a fixed threshold
  (e.g. >=1 non-stopword overlap, tune during Tier 1).
- **arXiv:** at least one returned result with query-term overlap in
  title or abstract.
- **Source diversity gate:** evaluated in this order:
  1. **Primary signal — `question_type` from run header** (set by batch
     runner from `config/reference_questions.md`):
     - `multi_source_synthesis` or `cross_tool_synthesis` → require
       evidence from **>=2 distinct tools** before sufficiency passes.
     - All other canonical types → no diversity gate (single-tool OK).
  2. **Fallback only when `question_type` is absent** — keyword triggers
     in the question text ("research," "papers," "academic," "studies,"
     "compare," "differ"). Do not rely on keywords when `question_type`
     is present; Q4's "differ" phrasing is not reliably caught by a
     keyword list alone.
  A single-tool result set fails sufficiency when the diversity gate
  applies, regardless of result count, until the requirement is met or
  loop bounds are exhausted (§5b), at which point it proceeds with
  `mode_final=caveated` and `outcome_final=insufficient_evidence`, not
  silently treated as sufficient.
- **data_retrieval:** sufficiency requires an `ok=True` `tool_result`
  from a tool specifically designated as the data source for this
  `question_type` (currently: `fred`). Generic relevance matches from
  Wikipedia or arXiv are insufficient on their own — they may supply
  background/context claims (logged as `inference: true` in synthesis)
  but cannot satisfy a current-data-point question by substitution. If
  no data-source tool is registered (e.g. pre-Tier-3, FRED not yet
  wired), sufficiency cannot pass; bounds exhaust per §5b and the run
  proceeds to `mode_final=caveated`, `outcome_final=insufficient_evidence`,
  per §7 — this is the Q5 pre-FRED path, not a bug.
- Every sufficiency check is logged as a `sufficiency` event:
  `{passed, reason, matched_event_ids, rejected_event_ids, rejected_reasons,
  rule_version}` — `reason` must explicitly state whether the diversity
  gate or `data_retrieval` source requirement was the deciding factor, so
  a reviewer can see *why* refine did or didn't fire, not just that it
  did or didn't.

## 5b. Loop bounds — checked deadline, not a declared constant

Worst case for one failing arXiv call: 3 retries x 10s timeout + backoff
(1+2+4s) + the 3s min_interval gate ~= 35-40s. Two failing calls, or one
failing call plus a Groq retry, already meets or exceeds a naive
`RUN_TIMEOUT_S=90`. A circuit breaker at 3 consecutive failures needs
~120s to trip for the slow tool — **longer than the run timeout itself**,
so it can never fire before the deadline kills the run anyway.

```python
MAX_REFINE_ROUNDS = 2
MAX_PLANNER_CYCLES = 3
MAX_TOOL_CALLS_PER_RUN = 6
RUN_TIMEOUT_S = 90
CIRCUIT_BREAKER_CONSECUTIVE_FAILURES = 2   # must trip before RUN_TIMEOUT_S
                                            # at worst-case per-tool latency
PER_TOOL_CUMULATIVE_TIME_CAP_S = 45        # hard stop on total time spent
                                            # in one tool this run,
                                            # independent of breaker state
```

Values above are mirrored in `config/tool_policy.yaml` `loop_bounds` —
the YAML is the runtime source of truth.

`RUN_TIMEOUT_S` must be a **checked deadline enforced across every
blocking point** — the `min_interval` sleep, the tool call itself, and
retry backoff sleeps all check remaining budget before sleeping/calling,
not just a value compared after the fact. If remaining budget is
insufficient for even one more attempt, skip straight to synthesis with
whatever evidence exists. At exhaustion (any cap hit, deadline hit, or
sufficiency still failing after max rounds): proceed to synthesis with
`mode_final=caveated` and `outcome_final=insufficient_evidence` per §7.
`mode_final=refused` is reserved for answerability failures only (§5d).
**Never hang, never loop silently past a cap.**

- **arXiv calls execute strictly sequentially**, never in parallel with
  each other or with Wikipedia (Tier 1 is fully sequential — parallelism
  interacts badly with rate gating and the deadline check; do not add it
  even as an optimization).
- **Cross-invocation rate limiting:** `min_interval_s` state is scoped to
  one process by default, which resets on every `python agent.py`
  invocation. A reviewer running all 8 reference questions back-to-back
  bursts arXiv calls across process boundaries, defeating the 1-req/3s
  gate and risking a real ToU violation / soft block. See §6a — the
  batch runner is the required fix; `.ratelimit_state.json` (gitignored)
  is a fallback only if batch runner is not used.

## 5c. LLM call policy (mirrors tool policy — see `config/tool_policy.yaml` groq section)

Groq calls get the same discipline as tool calls: timeout, retry, and now
also **output validation**, since planner/synthesizer output must parse
as expected JSON.

- Missing/invalid `GROQ_API_KEY` → fail fast at startup with a clear
  message, not a crash mid-run.
- 429 / transient 5xx → retry per policy (see config file).
- Planner output failing schema validation → **one repair attempt**
  (re-prompt with the validation error), then fall back to a safe default
  (empty `tool_calls`, proceed to sufficiency check as "insufficient").
- Every LLM call (plan + synthesize) is logged as its own event (`plan` or
  `synthesize` kind) with full payloads — see §5 event schemas. Trace must
  show LLM-side decisions, not just tool calls.

## 5d. Refusal path — answerability, not retrieval overlap

**Refusal is about whether the question is answerable by these tools at
all — not whether some tool result technically overlaps in keywords.**
"Best restaurant in NYC" can return a tangential Wikipedia hit (e.g. a
"Restaurants in New York City" page) that clears a naive overlap
threshold, making sufficiency pass and the answer proceed to synthesis
instead of refusing — exactly the failure mode the refusal path exists
to prevent.

Add an explicit **answerability check, run before tool calls, separate
from sufficiency**:
- Classify the question as in-scope (factual/academic/data/synthesis) or
  out-of-scope (subjective preference, opinion, no factual ground truth —
  "best," "favorite," "should I," recommendation-style questions with no
  citable answer) using a small rule set keyed on `question_type=out_of_scope`
  or keyword fallback, logged as its own event kind (`answerability`).
- If out-of-scope: **orchestrator short-circuits directly to a templated
  refusal, skipping tool calls and the synthesizer LLM entirely.**
  Set `mode_final=refused`, `outcome_final=out_of_scope`,
  `refusal_reason` set. Zero hallucination risk, zero wasted tool budget.
- If in-scope but sufficiency still fails after all bounds are
  exhausted (§5b): `mode_final=caveated`,
  `outcome_final=insufficient_evidence`, `refusal_reason=null`. This is
  evidence quantity failure, not answerability. A reviewer must be able
  to tell the two apart via `run_complete` fields (§5e, §7).

## 5e. Trace export contract

- Format: JSON Lines, one JSON object per line, flushed **incrementally**
  after each event (so a crash mid-run still leaves a partial, readable
  trace — not an all-or-nothing write at the end).
- Path: `traces/{run_id}.jsonl`.

**First line — `run_header` event** (written at run start; `outcome` is
not known yet and must not appear here):

```json
{
  "kind": "run_header",
  "event_id": 0,
  "run_id": "<uuid4>",
  "question": "<full question text>",
  "question_ref": "Q4",
  "question_type": "multi_source_synthesis",
  "variant": "refine",
  "experiment_id": "<optional batch id>",
  "refine_disabled": false,
  "started_at": "<ISO8601>",
  "trace_schema_version": "1",
  "config": {
    "model_id": "...",
    "temperature": 0.0,
    "policy_file_hash": "...",
    "prompt_version": "..."
  }
}
```

**Last line — `run_complete` event** (written at run end only):

```json
{
  "kind": "run_complete",
  "event_id": <N>,
  "run_id": "<uuid4>",
  "mode_final": "grounded",
  "outcome_final": "completed",
  "refusal_reason": null,
  "evidence_fingerprint": {
    "source_ids": ["arxiv:2301.12345", "wikipedia:Federal_Reserve"],
    "tools_used": ["arxiv", "wikipedia"]
  }
}
```

`evidence_fingerprint` is sorted `source_id` list plus distinct tools used
from all `ok=True` `tool_result` events — enables Tier 2 diff without
re-parsing full content.

Intermediate lines are standard `AgentEvent` objects per §5.

- `agent.py` prints the trace file path in its final CLI output, so a
  reviewer can locate it without searching.

## 6. Tool reliability policy (Tier 1 baseline, not deferred)

See `config/tool_policy.yaml` for exact values. Contract:

- Every `Tool.invoke()` self-enforces `min_interval_s` (client-side rate
  gate) *before* calling out, independent of whether a prior call failed.
- Every call has a hard `timeout_s`.
- On failure, retry up to `max_retries` with exponential backoff
  (`backoff_base_s`).
- After retries exhausted: return `ToolResult(ok=False, reason=...,
  failure_class=...)`. **Never raise** to the agent loop.
- `failure_class` (required when `ok=False`): `timeout` | `http_429` |
  `parse_error` | `empty_result` — machine-diagnosable; `reason` remains
  human-readable detail.
- arXiv note: ToU permits 1 request/3s on a single connection, but 429/503
  responses have been observed even from fully compliant clients — treat
  as retryable regardless of compliance, don't treat a 429 as a client bug.

## 6a. Batch Runner (required Tier-1 scaffolding)

The batch runner is **required Tier-1 scaffolding**, not an optional
optimization. Do not rely on shelling out `python agent.py` per question
for reference-question runs.

**Contract:**
- Single long-lived Python process runs all reference questions (and Tier 2
  re-runs of Q4/Q6) sequentially in one invocation.
- Reads `config/reference_questions.md` (or an equivalent parsed structure)
  and for each row sets on the run's `run_header`:
  - `question_ref` (e.g. `"Q4"`)
  - `question_type` (canonical tag, e.g. `multi_source_synthesis`)
  - `variant` (`single_pass` or `refine` per env/CLI flag)
  - `experiment_id` (optional, for batch-level Tier 2 pairing)
- Preserves arXiv `min_interval_s` rate state across questions in the
  batch — timestamps do not reset between runs.
- Writes `outputs/tier1_results.md` (and `outputs/tier2_comparison.md` for
  Tier 2 pairs) with answer text and trace file paths per question.
- Entry point: e.g. `python -m scripts.run_reference` or `make tier1`
  (see §10 operational guardrails).

Without the batch runner, cross-process arXiv bursts violate ToU and
`question_type` will not reach sufficiency logic reliably.

## 7. Synthesizer output modes (needed for reference Q7 / Q8)

### mode_final vs outcome_final — distinct fields

| Field | Set on | Value set | Meaning |
|---|---|---|---|
| `mode_final` | `run_complete` | `grounded` \| `caveated` \| `refused` | What the answer path decided about claim grounding |
| `outcome_final` | `run_complete` | `completed` \| `aborted` \| `out_of_scope` \| `insufficient_evidence` \| `degraded` | Why the run ended |
| `refusal_reason` | `run_complete` | `str` \| `null` | Human detail when `mode_final=refused`; **null** otherwise |

**Rules:**
- `mode_final=refused` → answerability failure only (`outcome_final=out_of_scope`).
- In-scope evidence exhaustion → `mode_final=caveated`,
  `outcome_final=insufficient_evidence`, `refusal_reason=null`.
- Groq mass-429 / sustained LLM unavailability (see `config/tool_policy.yaml`
  `groq` section) → `outcome_final=degraded`. Pair with:
  - `mode_final=caveated` when ≥1 `ok=True` `tool_result` exists before
    degradation (partial evidence available); or
  - `mode_final=refused` when degradation occurs before any usable evidence
    is gathered and the run cannot produce a grounded or caveated answer.
  `refusal_reason=null` unless `mode_final=refused` for answerability.
- Never encode `out_of_scope` vs `insufficient_evidence` inside
  `mode_final` or a combined `"refused: X"` string.

### Modes

- `grounded` — every claim is `inference: false`, sourced from `ok=True`
  tool results.
- `caveated` — at least one claim is `inference: true`. **This is
  enforced mechanically in Python after synthesis, not left to the LLM's
  mode choice**: if the validated `claims[]` list contains any
  `inference: true` entry, `mode_enforced` is forced to `caveated`
  regardless of `mode_model`. The model cannot self-report `grounded` while
  including inferred content.
- `refused` — answerability check failed (§5d) — orchestrator
  short-circuit, synthesizer never called.

`ok=False` (tool unavailable) must render visibly differently from
`ok=True` with an irrelevant result — a reviewer should be able to tell
"the tool broke" apart from "the tool worked but had nothing useful."

### Speculative questions (Q8)

When `question_type=speculative` (or answerability subclass marks
speculative intent):
- Set `speculative=true` on the run header (or in `answerability` event).
- Synthesizer prompt must require **at least one `inference: true` claim**
  even when sources exist — forward-looking implications cannot be
  all-grounded.
- Post-validation: if all claims have `inference: false`, force the first
  forward-looking claim to `inference: true` and set `mode_enforced=caveated`.
  An all-grounded answer must not pass Q8.

**Structured output contract (validated in Python before write, not
trusted as free prose):**
```python
{
  "mode": "grounded" | "caveated" | "refused",   # mode_enforced in trace
  "claims": [
    {"text": str, "source_id": str | None, "inference": bool}
  ],
  "citations": [{"source_id": str, "title": str, "url_or_id": str}]
}
```
Every `claims[].source_id` must resolve to a real `tool_result` event's
`source_id` in this run's event log — reject and repair (one attempt) if
not. Aggregate token budget: sum of `content_full` lengths fed to the
synthesizer across all relevant events is capped (e.g. ~6000 chars); if
exceeded, drop lowest-relevance events and log each as a `dropped_context`
event (mirrors `dedup_skip` — never silently truncate mid-content in a
way that corrupts a citation).

## 8. Tier 3 decision

- **Default: Option C** — add `FREDTool` behind the existing `Tool`
  interface + a 12–15 question routing eval (question -> expected tool).
- **Fallback trigger:** if FRED integration is not passing smoke tests by
  **1 hour 50 minutes elapsed**, abandon it and pivot to **Option B**
  (exponential backoff tuning + circuit breaker + synthetic failure
  injection tests on the existing two tools). This trigger is a
  deliberate time-box, stated in the README as a decision, not discovered
  as a shortfall.

## 9. Reference questions

See `config/reference_questions.md`.

## 10. Dependencies, offline fallback, tests (Tier 1 baseline additions)

- **Pin all dependency versions in `requirements.txt`.** Do not use the
  `wikipedia` PyPI package — it raises `DisambiguationError` and silently
  auto-suggests the *wrong* page on ambiguous titles, directly defeating
  the "wrong-article must not pass sufficiency" goal, and can throw
  inside the tool despite the "never raise" contract. Call the Wikipedia
  REST API directly via `requests`/`httpx` instead. If using the `arxiv`
  PyPI package, pin the exact version — its `Search`/`Client` API has
  changed across releases.
- **Offline / no-key fallback — part of Tier 1 happy path, not deferred:**
  a reviewer with no key gets a fast startup failure and nothing to inspect
  without this. Ship `--offline` (or `OFFLINE_MODE=1`) in the same Tier 1
  milestone as the live happy path. It replays small recorded fixture
  responses for each tool and canned planner/synthesizer responses,
  producing a real, inspectable trace (including `run_header` /
  `run_complete`) without network or API keys. Required for the "reviewer
  runs unattended, no paid keys" constraint.
- **`pytest` suite on pure functions**, not full integration: dedup
  normalization, sufficiency/answerability rules, claim→`source_id`
  validation, mode-forcing logic (§7), speculative minimum-inference rule.
  These are the highest-ROI safety net for an unattended run and the
  cheapest to write given they're pure functions with no I/O.
- **Prompt-injection note:** tool content (Wikipedia/arXiv text) is
  *data*, never instructions — the synthesizer prompt must frame retrieved
  content as untrusted input to reason about, not as directives to follow.

### Operational guardrails checklist (Tier 1)

Before calling Tier 1 complete, verify all of the following exist:

| Item | Requirement |
|---|---|
| `requirements.txt` | All dependencies pinned to exact versions |
| `.env.example` | Documents `GROQ_API_KEY` and `FRED_API_KEY` |
| Batch runner | `python -m scripts.run_reference` or `make tier1` — single process, sets header metadata, preserves arXiv rate state |
| Smoke output | One command produces `outputs/tier1_results.md` with trace paths |
| `.gitignore` | Includes `.ratelimit_state.json` if file-based rate fallback is used alongside or instead of batch runner |
| Offline mode | `--offline` / `OFFLINE_MODE=1` produces inspectable trace without keys |
