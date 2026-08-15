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
         -> executor(tool_calls) -> state.steps.append(result)
         -> sufficiency_check(state) -> refine (<=2 rounds) | proceed
         -> synthesizer(state) -> answer{mode, citations}
```

**Why:** free-text ReAct (model emits "Thought/Action/Observation" as
unstructured text, regex-parsed) makes Tier 2 tracing an afterthought
retrofitted onto strings. An explicit state object makes tracing free
(serialize `state.steps`), makes dedup trivial (check steps before
calling), and makes sufficiency a real function instead of a hopeful
prompt.

## 5. Memory model — event log, not a tool-results list

The Groq API is stateless; there is no server-side session. All continuity
comes from what is re-sent in each call, built from `AgentState`. State is
an **append-only event log**, not just a list of tool results — this is
required for Tier 2 traces to explain *why* the agent did what it did, not
just what it retrieved.

```python
# Run-level (header)
run_id: str                 # uuid4 — NOT second-resolution timestamp,
                             # to avoid collision when Q4/Q6 run twice
                             # in quick succession for Tier 2 A/B
question: str
question_ref: str            # e.g. "Q4" — matches reference_questions.md
variant: "single_pass" | "refine"   # explicit, for Tier 2 auto-pairing
started_at: str
trace_schema_version: str    # bump whenever event shape changes —
                              # earlier outputs/ traces become unparseable
                              # by a later comparison tool otherwise
config: RunConfig            # model id + exact date/version pinned,
                              # temperature, decode params, policy file
                              # hash, prompt_version (so a diff caused by
                              # editing a prompt is attributable, not
                              # confused with a genuine behavior change)
outcome: str                 # final mode, or "aborted: <reason>",
                              # or "refused: out_of_scope" vs
                              # "refused: insufficient_evidence" (§5d)

events: list[AgentEvent]

# AgentEvent (union by kind)
# Every event has a STRUCTURAL id and a separate VOLATILE namespace —
# kept apart so the Tier 2 diff tool excludes timing/token noise by
# construction, not by a retrofitted normalization pass.
#   event_id: int             # monotonic, unique across ALL event kinds
#   kind: "plan" | "answerability" | "dedup_skip" | "tool_result" |
#         "sufficiency" | "synthesize" | "error"
#   refine_round: int
#   caused_by: int | None     # event_id of the plan/decision that led
#                              # to this event — explicit causal pointer,
#                              # not inferred from list ordering
#   timing: {timestamp_ms, duration_ms}   # volatile, excluded from diff
#
#   tool_result adds: tool_name, query, normalized_query, ok, reason,
#     source_id, content_full, content_for_synthesis, truncated
#   sufficiency adds: passed, reason, matched_step_ids, rejected_step_ids,
#     rejected_reasons, rule_version   # log rejections too, not just
#                                       # winners — needed to explain
#                                       # "why refine didn't fire"
```

`step_id` from earlier drafts is retired — replaced by `event_id`
(ordering/uniqueness) and `source_id` (stable per-retrieval identity,
used in citations). Do not conflate the two.

Export: `state.to_trace_dict()` → JSON; no string parsing later.

- **Stable IDs, assigned at ingest, not later:** every `tool_result` event
  gets a monotonic `step_id` and a stable `source_id` (e.g.
  `wikipedia:Title`, `arxiv:2301.12345`). Synthesizer citations reference
  `source_id` directly — no unverifiable free-text citations.
- **Two views of every tool result, both stored:** `content_full` (for
  synthesis + trace export) and `content_for_synthesis` (truncated to
  ~1500 chars, `truncated: true/false` recorded). Never store only the
  truncated version — citations must be traceable back to real content.
- **Planner call** — gets `question` + a *compact summary* of prior
  `tool_result` events (tool name + query + `source_id` only, not full
  content).
- **Sufficiency check** — deterministic Python rule, not an LLM call (see
  §5a for the relevance definition it must use).
- **Synthesizer call** — gets `question` + full `content_full` from every
  relevant step.
- **Dedup** — before any tool call, check `(tool_name, normalized_query)`
  against prior `tool_result` events. Normalization: lowercase, collapse
  whitespace, strip punctuation. A blocked call is logged as a
  `dedup_skip` event, not silently dropped.
- **`refine_round`** stored on every event (0..N). `SINGLE_PASS=1` → all
  events `refine_round=0`, header records `refine_disabled: true`. This
  is what makes the Tier 2 A/B comparison a diff, not a manual reconciliation.

**Scope note for README:** memory here is working memory only, scoped to
one run. No persistence across invocations (out of scope per the brief).
Natural "what I'd do with more time" item: a SQLite-backed session log the
agent could consult for repeat/related questions.

## 5a. Sufficiency / relevance — defined mechanically, not left implicit

Sufficiency is **not** "any `ok=True` result," and it is **not** "N
`tool_result` events regardless of which tool produced them." A prior
build of this design passed sufficiency for cross-tool questions (Q4,
Q6 — tagged "multi-source synthesis" and "cross-tool synthesis" in
`reference_questions.md`) on two Wikipedia results alone, because the
count-based check never looked at *which tools* the evidence came from.
The planner never even attempted arXiv — sufficiency was satisfied
before it needed to. Define before coding:

- **Wikipedia:** page title/redirect match, or keyword overlap between
  question tokens and returned title+summary above a fixed threshold
  (e.g. >=1 non-stopword overlap, tune during Tier 1).
- **arXiv:** at least one returned result with query-term overlap in
  title or abstract.
- **Source diversity gate (new):** if the question signals a
  multi-source/cross-tool need — keyword triggers ("research," "papers,"
  "academic," "studies," "compare," "differ") or an explicit
  `question_type` tag from `reference_questions.md` — sufficiency
  requires evidence from **>=2 distinct tools**, not just >=2 results
  from any tool. A single-tool result set fails sufficiency regardless of
  count until the diversity requirement is met or loop bounds are
  exhausted (§5b), at which point it proceeds to `caveated` with the gap
  noted, not silently treated as sufficient.
- Every sufficiency check is logged as a `sufficiency` event:
  `{passed, reason, matched_step_ids, rejected_step_ids, rejected_reasons,
  rule_version}` — `reason` must explicitly state whether the diversity
  gate was the deciding factor, so a reviewer can see *why* refine did or
  didn't fire, not just that it did or didn't.

## 5b. Loop bounds — checked deadline, not a declared constant

Worst case for one failing arXiv call: 3 retries x 10s timeout + backoff
(1+2+4s) + the 3s min_interval gate ~= 35-40s. Two failing calls, or one
failing call plus a Groq retry, already meets or exceeds a naive
`RUN_TIMEOUT_S=90`. The circuit breaker (3 consecutive failures) needs
~120s to trip for the slow tool — **longer than the run timeout itself**,
so it can never fire before the deadline kills the run anyway.

```python
MAX_REFINE_ROUNDS = 2
MAX_PLANNER_CYCLES = 3
MAX_TOOL_CALLS_PER_RUN = 6
RUN_TIMEOUT_S = 90
CIRCUIT_BREAKER_CONSECUTIVE_FAILURES = 2   # lowered from 3 — must trip
                                            # before RUN_TIMEOUT_S at
                                            # worst-case per-tool latency
PER_TOOL_CUMULATIVE_TIME_CAP_S = 45        # hard stop on total time spent
                                            # in one tool this run,
                                            # independent of breaker state
```

`RUN_TIMEOUT_S` must be a **checked deadline enforced across every
blocking point** — the `min_interval` sleep, the tool call itself, and
retry backoff sleeps all check remaining budget before sleeping/calling,
not just a value compared after the fact. If remaining budget is
insufficient for even one more attempt, skip straight to synthesis with
whatever evidence exists. At exhaustion (any cap hit, deadline hit, or
sufficiency still failing after max rounds): proceed to synthesis with
`mode=caveated` or `mode=refused` per §5a/§7. **Never hang, never loop
silently past a cap.**

- **arXiv calls execute strictly sequentially**, never in parallel with
  each other or with Wikipedia (Tier 1 is fully sequential — parallelism
  interacts badly with rate gating and the deadline check; do not add it
  even as an optimization).
- **Cross-invocation rate limiting:** `min_interval_s` state is scoped to
  one process by default, which resets on every `python agent.py`
  invocation. A reviewer running all 8 reference questions back-to-back
  bursts arXiv calls across process boundaries, defeating the 1-req/3s
  gate and risking a real ToU violation / soft block. Persist the last
  call timestamp per tool to a small local file (e.g.
  `.ratelimit_state.json`, gitignored) that `RetryPolicy` reads/writes,
  OR run the batch runner as a single long-lived process rather than
  shelling out per question. Prefer the single-process batch runner for
  Tier 1 — simpler, no extra state file to reason about.

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
- Every LLM call (plan + synthesize) is logged as its own event, not just
  tool calls — trace must show LLM-side decisions too.

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
  citable answer) using a small rule set or a single cheap LLM
  classification call, logged as its own event kind (`answerability`).
- If out-of-scope: **orchestrator short-circuits directly to a templated
  refusal, skipping tool calls and the synthesizer LLM entirely.**
  Zero hallucination risk, zero wasted tool budget.
- If in-scope but sufficiency still fails after all bounds are
  exhausted (§5b): that's the *separate* `mode=caveated`/`refused` path
  based on evidence quantity, not answerability. Log which of the two
  paths triggered a refusal in the trace header's `outcome` field — a
  reviewer should be able to tell "out of scope" apart from "in scope but
  we couldn't find enough."

## 5e. Trace export contract

- Format: JSON Lines, one event per line, flushed **incrementally** after
  each event (so a crash mid-run still leaves a partial, readable trace —
  not an all-or-nothing write at the end).
- Path: `traces/{run_id}.jsonl`.
- File header (first line): `run_id, question, started_at, config
  (single_pass, model id, policy file hash), outcome (final mode, or
  aborted + error)`.
- `agent.py` prints the trace file path in its final CLI output, so a
  reviewer can locate it without searching.

## 6. Tool reliability policy (Tier 1 baseline, not deferred)

See `config/tool_policy.yaml` for exact values. Contract:

- Every `Tool.invoke()` self-enforces `min_interval_s` (client-side rate
  gate) *before* calling out, independent of whether a prior call failed.
- Every call has a hard `timeout_s`.
- On failure, retry up to `max_retries` with exponential backoff
  (`backoff_base_s`).
- After retries exhausted: return `ToolResult(ok=False, reason=...)`.
  **Never raise** to the agent loop.
- arXiv note: ToU permits 1 request/3s on a single connection, but 429/503
  responses have been observed even from fully compliant clients — treat
  as retryable regardless of compliance, don't treat a 429 as a client bug.

## 7. Synthesizer output modes (needed for reference Q7 / Q8)

- `grounded` — every claim is `inference: false`, sourced from `ok=True`
  tool results.
- `caveated` — at least one claim is `inference: true`. **This is
  enforced mechanically in Python after synthesis, not left to the LLM's
  mode choice**: if the validated `claims[]` list contains any
  `inference: true` entry, `mode` is forced to `caveated` regardless of
  what the model returned. The model cannot self-report `grounded` while
  including inferred content.
- `refused` — answerability check failed (§5d) — orchestrator
  short-circuit, synthesizer never called.

`ok=False` (tool unavailable) must render visibly differently from
`ok=True` with an irrelevant result — a reviewer should be able to tell
"the tool broke" apart from "the tool worked but had nothing useful."

**Structured output contract (validated in Python before write, not
trusted as free prose):**
```python
{
  "mode": "grounded" | "caveated" | "refused",   # recomputed, not trusted
  "claims": [
    {"text": str, "source_id": str | None, "inference": bool}
  ],
  "citations": [{"source_id": str, "title": str, "url_or_id": str}]
}
```
Every `claims[].source_id` must resolve to a real `tool_result` event's
`source_id` in this run's event log — reject and repair (one attempt) if
not. Aggregate token budget: sum of `content_full` lengths fed to the
synthesizer across all relevant steps is capped (e.g. ~6000 chars); if
exceeded, drop lowest-relevance steps and log each as a `dropped_context`
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

See `reference_questions.md`.

## 10. Dependencies, offline fallback, tests (Tier 1 baseline additions)

- **Pin all dependency versions in `requirements.txt`.** Do not use the
  `wikipedia` PyPI package — it raises `DisambiguationError` and silently
  auto-suggests the *wrong* page on ambiguous titles, directly defeating
  the "wrong-article must not pass sufficiency" goal, and can throw
  inside the tool despite the "never raise" contract. Call the Wikipedia
  REST API directly via `requests`/`httpx` instead. If using the `arxiv`
  PyPI package, pin the exact version — its `Search`/`Client` API has
  changed across releases.
- **Offline / no-key fallback:** a reviewer with no key today gets only a
  fast startup failure and nothing to inspect. Add a `--offline` flag (or
  `OFFLINE_MODE=1` env var) that replays small recorded fixture responses
  for each tool and a canned planner/synthesizer response, producing a
  real, inspectable trace without any network or API key. This is
  high-leverage for the stated "reviewer runs unattended, no paid keys"
  constraint — build it once Tier 1's happy path works, before Tier 2.
- **`pytest` suite on pure functions**, not full integration: dedup
  normalization, sufficiency/answerability rules, claim→`source_id`
  validation, mode-forcing logic (§7). These are the highest-ROI safety
  net for an unattended run and the cheapest to write given they're pure
  functions with no I/O.
- **Prompt-injection note:** tool content (Wikipedia/arXiv text) is
  *data*, never instructions — the synthesizer prompt must frame retrieved
  content as untrusted input to reason about, not as directives to follow.
