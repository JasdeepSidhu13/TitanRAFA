## Interaction 1

### User Prompt
# P1 — Set up repository controls

Before any assessment implementation, establish two repository-wide Cursor rules:

1. mandatory interaction logging;
2. pedagogical code documentation.

Do not perform any other assessment work in this interaction.

## Files to create

Create:

```text
prompt-log.md
.cursor/rules/mandatory-prompt-logging.mdc
.cursor/rules/pedagogical-code-documentation.mdc
```

---

## 1. Mandatory interaction logging

Create `prompt-log.md` in the repository root.

For **every Cursor interaction without exception**:

* record my complete prompt exactly as received;
* record your complete user-visible response;
* append chronologically;
* never overwrite, delete, reorder, summarize, truncate, or reconstruct prior entries;
* use sequential interaction numbers beginning with `1`.

Use this format:

```markdown
## Interaction N

### User Prompt
<complete prompt>

### Cursor Response
<complete user-visible response>

---
```

Create `.cursor/rules/mandatory-prompt-logging.mdc` as an **always-applied** Cursor Project Rule enforcing this workflow:

```text
receive prompt
→ perform requested work
→ append complete prompt and complete user-visible response to prompt-log.md
→ verify the entry exists
→ complete the interaction
```

The rule must explicitly state that Cursor Project Rules are behavioral instructions, not a technical guarantee that the platform captures every interaction.

Do not claim stronger enforcement than the platform provides.

---

## 2. Pedagogical code documentation

Create `.cursor/rules/pedagogical-code-documentation.mdc` as an **always-applied** Cursor Project Rule.

Its purpose is to make all new or materially modified code easy for a reviewer to understand.

### General principle

Comments and documentation should explain:

* what the code does;
* why the design exists;
* important architectural boundaries;
* invariants and safeguards;
* non-obvious control flow;
* failure handling;
* relevant tradeoffs.

Prefer explanations of **why** over comments that merely restate syntax.

Example:

Bad:

```python
step += 1  # Increment step.
```

Good:

```python
# The step budget guarantees termination even if the planner repeatedly
# requests actions that do not produce useful evidence.
step += 1
```

### Functions and methods

Every new or materially modified Python function or method must contain a docstring as its first statement.

Use these sections:

* `Description` which includes when to use, when not to use and any edge cases.
* `Input`
* `Output`
* `When to use`
* `When not to use`


Example:

```python
def validate_citation(
    source_id: str,
    evidence: list[EvidenceItem],
) -> bool:
    """Verify that a citation references evidence retrieved in this run.

    Description:
        Checks whether source_id belongs to evidence produced during the
        current agent execution.

    Input:
        source_id:
            Stable source identifier.
        evidence:
            Evidence collected from tool calls during the current run.

    Output:
        True when source_id matches retrieved evidence; otherwise False.

    When to use:
        Before exposing synthesized citations in the final answer.

    When not to use:
        Do not use this function to determine factual correctness. It verifies
        provenance membership only.

    
    """
```

Keep sections concise for simple helpers rather than creating unnecessary documentation volume.

### Modules and classes

New production modules must have a module-level docstring explaining:

* responsibility;
* role in the agent architecture;
* important dependencies or invariants where relevant.

New or materially modified classes must document:

* responsibility;
* lifecycle;
* relationship to other components;
* important state or invariants.

### Inline comments

Add comments where logic is non-obvious, especially around:

* planner/runtime boundaries;
* termination safeguards;
* evidence provenance;
* citation validation;
* state transitions;
* retries and failures;
* duplicate-action handling;
* API quirks;
* timeouts;
* scoring thresholds.

Do not add comments that merely restate obvious code.

### Tests

For non-trivial tests, document:

* the behavior being verified;
* the failure mode being protected against;
* the relevant assessment requirement when useful.

### Scope

This rule applies to:

* production code;
* tests;
* utilities;
* CLI code;
* tool integrations;
* evaluation code.

It applies only to **new or materially modified code**.

Do not modify unrelated existing code solely to add documentation.

Static configuration and JSON/YAML data files are exempt unless documentation is materially useful.

### Completion check

Before completing any coding interaction, verify:

* every new or materially modified function has the required docstring;
* new production modules have module documentation;
* important classes are documented;
* non-obvious logic has useful comments;
* tests explain non-obvious behavioral guarantees;
* documentation still matches the implementation.

---

## 3. Initialize and verify

Before completing this interaction:

1. Create all three required files.
2. Log this exact prompt as `Interaction 1`.
3. Record your complete response under `### Cursor Response`.
4. Verify `prompt-log.md` contains:

   * `## Interaction 1`
   * `### User Prompt`
   * the complete prompt
   * `### Cursor Response`
5. Verify both `.mdc` files:

   * contain valid Cursor rule metadata;
   * are configured with `alwaysApply: true`.
6. Report:

   * files created or modified;
   * verification result for each file.

## Stop condition

After setup and verification, STOP.

### Cursor Response
Repository controls are in place. Three files were created; verification for each is below.

## Files Created

| File | Action |
|------|--------|
| `prompt-log.md` | Created (Interaction 1 initialized) |
| `.cursor/rules/mandatory-prompt-logging.mdc` | Created |
| `.cursor/rules/pedagogical-code-documentation.mdc` | Created |

## Verification Results

### `prompt-log.md`

- `## Interaction 1` — present
- `### User Prompt` — present with the complete prompt
- `### Cursor Response` — present with this complete response
- Chronological append-only format with trailing `---` separator — correct

### `.cursor/rules/mandatory-prompt-logging.mdc`

- Valid YAML frontmatter with `description` — present
- `alwaysApply: true` — confirmed
- Workflow sequence documented (`receive prompt → perform work → append → verify → complete`) — present
- Explicit statement that Project Rules are behavioral instructions, not a platform guarantee — present

### `.cursor/rules/pedagogical-code-documentation.mdc`

- Valid YAML frontmatter with `description` — present
- `alwaysApply: true` — confirmed
- Docstring sections, module/class documentation, inline comment guidance, test documentation, scope, and completion check — all present

No assessment implementation work was performed. Stopping per the stop condition.

---

## Interaction 2

### User Prompt
Create these three files in the repo root/config with the exact content
attached — do not modify, summarize, reformat, or "improve" any of it.
Commit verbatim with message "Project scaffolding: design doc, tool policy,
reference questions" and push to the current branch.

### Cursor Response
Three files were copied byte-for-byte from the attachments into `config/` and committed.

| File | Source |
|------|--------|
| `config/DESIGN.md` | `DESIGN_0904.md` |
| `config/reference_questions.md` | `reference_questions_a538.md` |
| `config/tool_policy.yaml` | `tool_policy_1ca3.yaml` |

`diff -q` confirmed each destination file matches its source exactly — no content changes.

**Commit:** `5426e07` — `Project scaffolding: design doc, tool policy, reference questions`

**Branch:** `cursor/p1-repository-controls-72ca` (pushed to origin)

---

## Interaction 3

### User Prompt
I'm building a multi-tool research agent (Wikipedia + arXiv, Groq-hosted
LLM, ReAct-lite loop over an explicit AgentState). Constraints: 150-min
unpaused build, reviewer runs unattended with no paid keys, Tier 2 needs
structured traces, must handle refusal (Q7) and speculative (Q8) cases.

Read config/DESIGN.md, config/tool_policy.yaml, and config/reference_questions.md from
this repo before responding.

Before I implement anything: what's wrong or missing in this design?
Specifically — failure modes in an unattended 150-min run, and anything
in AgentState that would force rework once I get to Tier 2 tracing.

### Cursor Response
The design is unusually thorough for a timed build — it already encodes lessons from a prior failure (Q4/Q6 single-tool sufficiency). What follows are the gaps and contradictions most likely to bite you during an unattended run or force AgentState rework at Tier 2.

---

## Internal contradictions (fix before coding)

### 1. `tool_policy.yaml` vs DESIGN §5b disagree on loop bounds

| Parameter | `config/tool_policy.yaml` | DESIGN §5b |
|-----------|---------------------------|------------|
| `circuit_breaker_consecutive_failures` | **3** | **2** (with rationale) |
| `per_tool_cumulative_time_cap_s` | **missing** | **45** |

DESIGN says "see `config/tool_policy.yaml`" but also embeds a Python constant block that contradicts it. Pick one source of truth and add the missing cap to the YAML, or you'll implement the wrong breaker behavior.

### 2. `step_id` vs `event_id` — still inconsistent in §5

Lines 109–111 retire `step_id`, but lines 115–118 and the sufficiency event schema still use `matched_step_ids` / `rejected_step_ids`. If you implement both names, Tier 2 diffs and citation validation will have two ID namespaces.

**Recommendation:** use `event_id` everywhere in events and sufficiency; reserve `source_id` only for citation provenance.

### 3. `state.steps` vs `events` — orchestrator diagram is stale

§4 shows `state.steps.append(result)`; §5 defines `events: list[AgentEvent]`. Implement one name from day one — the trace serializer should not need a migration layer.

### 4. Event kind union is incomplete

§7 introduces `dropped_context` events; §5's union does not include them. §5c says every LLM call is logged, but there is no `llm_request` / `llm_response` payload schema — only `plan` and `synthesize` kinds, with no fields defined for planner output (`tool_calls[]`, raw JSON, validation errors, repair attempts).

### 5. Trace header format is underspecified and self-contradictory

§5e says JSONL with a header first line containing `outcome`, but `outcome` is unknown until the run ends. Options:

- write a `header` event kind at start, update a final `footer`/`outcome` event at end; or
- write header last; or
- keep header in memory and rewrite line 1 (breaks append-only).

The header is also described in CSV-ish prose (`run_id, question, started_at, config...`) while events are JSON objects. Decide the exact JSON shape now or Tier 2 tooling will be guesswork.

---

## AgentState fields that will force Tier 2 rework if wrong now

These are the highest-risk schema decisions — get them right in the first commit:

### 1. `question_ref` and `question_type` must be first-class header fields

Q4 is tagged "Multi-source synthesis" but contains none of the diversity-gate keywords ("research," "papers," "compare," etc.). The diversity gate only fires on keywords **or** an explicit `question_type` tag from `reference_questions.md` — but nothing in the CLI/batch contract says how that tag reaches `AgentState`.

Without `question_type` in the header (set by the batch runner), Q4 will reproduce the exact bug the design warns about: two Wikipedia hits → sufficiency passes → arXiv never called.

### 2. `variant` must be set at run start, not inferred later

Tier 2 needs paired runs of Q4/Q6 with `SINGLE_PASS=1` vs refine enabled. The header needs:

```python
variant: "single_pass" | "refine"
refine_disabled: bool  # mentioned in §5 but not in the header schema block
```

Plus a batch manifest (`outputs/tier2_comparison.md` or a JSON index) mapping `(question_ref, variant) → trace path`. `run_id` alone is not enough for unattended pairing.

### 3. Planner decisions need structured payloads, not just a `plan` kind label

Tier 2 diffs need to explain *why* refine did or didn't change behavior. Each `plan` event should carry:

- proposed `tool_calls[]` (tool, query)
- which prior `event_id`s were visible in the compact summary
- validation/repair status if JSON parse failed

Without this, comparing single_pass vs refine traces reduces to diffing tool_result counts.

### 4. `caused_by` graph must be wired at implementation time

The design specifies causal pointers but not who sets them:

- `tool_result.caused_by` → parent `plan` event_id
- `sufficiency.caused_by` → triggering `plan` or post-executor checkpoint
- `dedup_skip.caused_by` → the `plan` that proposed the blocked call

If you defer this, you'll rewrite every event emitter for Tier 2.

### 5. Structural vs volatile split needs an explicit field list

"Volatile excluded from diff" is the right idea, but without a concrete partition (e.g. `timing`, token counts, raw HTTP status in volatile; everything else structural), you'll either over-diff noise or under-diff real behavior changes.

### 6. Final answer storage is undefined

Is the synthesizer output a `synthesize` event payload? A separate `outputs/` artifact? Both? Tier 1 wants `outputs/tier1_results.md`; traces want JSONL. Define whether `AgentState` holds the validated `{mode, claims, citations}` object and whether that object is the last event or a separate export.

---

## Failure modes in an unattended 150-minute run

### Time budget math is tighter than it looks

Per-question `run_timeout_s=90` is fine in isolation. A full unattended run is roughly:

- 8 Tier-1 questions + 4 Tier-2 re-runs (Q4, Q6 × 2 variants) = **12 runs minimum**
- Each run: up to 3 planner cycles × (Groq call + up to 6 tool calls × ~3–40s each with arXiv gating)

Worst case per question approaches 90s. **12 × 90s ≈ 18 minutes** of wall-clock timeout budget alone, before pytest, FRED, offline mode, or Option B pivot. That's fine — but only if nothing hangs past caps.

The real risk is **cascading soft failures**, not single-run hangs:

| Failure | What happens | Design gap |
|---------|--------------|------------|
| arXiv 429/503 storm | Each call burns ~35–40s in retries + 3s gate; 2–3 calls can consume most of a 90s run | Circuit breaker in YAML is still **3**, may never trip before deadline (DESIGN already notes this for 3; YAML wasn't updated) |
| Groq 429 on free tier | 12+ runs × 2–4 LLM calls each; no cross-run Groq budget or cooldown | `groq` policy has per-call retry but no run-level or batch-level cap |
| Planner JSON repair fails → empty `tool_calls` | Sufficiency fails → refine loops → synthesizer called with thin evidence → wrong mode | Fallback is safe but **wastes entire run budget** producing a bad trace |
| Process-per-question invocation | arXiv `min_interval_s` resets every `python agent.py` | DESIGN flags this; fix is single-process batch runner — **not specified, not in repo yet** |
| Wikipedia disambiguation / wrong page | Design forbids `wikipedia` PyPI package (good) | REST API still returns search results; need explicit disambiguation handling or wrong-article passes keyword overlap |
| No `GROQ_API_KEY` | Fail fast (good) | `FRED_API_KEY` has no equivalent fail-fast; Q5 behavior pre-Tier-3 is undocumented at runtime |
| Network blip mid-batch | Partial JSONL trace exists (good) | Header `outcome` may be stale/missing if crash before footer |
| Tier 3 at 1h50 | Pivot to Option B | ~10 minutes for circuit-breaker tests + doc — very tight |

### Batch runner is load-bearing but unspecified

DESIGN §5b explicitly prefers a **single-process batch runner** over per-question shell-outs to preserve arXiv rate state. Without it:

- 12 cold starts burst arXiv past 1 req/3s
- risk of soft block mid-review
- no natural place to set `question_ref`, `question_type`, `variant`

This should be Tier-0 scaffolding, not a nice-to-have.

### Offline mode is deferred too late

§10 puts `--offline` after Tier-1 happy path. For "reviewer runs unattended with no paid keys," a reviewer without `GROQ_API_KEY` today gets a startup error and **zero inspectable artifacts**. Offline fixtures should be early — even a stub trace proves the export contract works.

### Q7 / Q8 behavioral gaps

**Q7 (refused):** Rule-based answerability on "best"/"favorite" is right. Risk: if you use LLM classification as fallback, a misclassify wastes tool budget and may retrieve a tangential Wikipedia page. The design's short-circuit path (no tools, no synthesizer) must be the default for keyword hits.

**Q8 (caveated):** Mode is forced to `caveated` only when `claims[].inference: true`. If the 8b model marks speculative content as `inference: false`, Python enforcement produces **`grounded` incorrectly**. You need either:

- a prompt rule requiring inference flags on forward-looking claims, or
- a post-validation heuristic (e.g. claims with no `source_id` and speculative language → force inference)

Also: §5d says `refused` is answerability-only, but §5b says proceed with `mode=refused` when evidence is exhausted — that's `insufficient_evidence`, which §5d wants as a distinct `outcome` string, not `mode=refused`. Clarify: **`mode`** vs **`outcome`** semantics.

### Missing operational guardrails

Not in design but needed for unattended runs:

- `requirements.txt` with pinned versions (mentioned, not created)
- `.env.example` documenting `GROQ_API_KEY`, `FRED_API_KEY`
- a one-command smoke script (`make tier1` or `python -m scripts.run_reference`) that produces `outputs/tier1_results.md` + trace paths
- pytest on pure functions before any integration run
- `.ratelimit_state.json` in `.gitignore` if you don't ship the batch runner first

---

## What the design gets right (don't rework these)

- Explicit `AgentState` event log over free-text ReAct — correct for Tier 2
- `uuid4` run_id for rapid A/B pairs
- `trace_schema_version` + `prompt_version` + policy hash in `RunConfig`
- Answerability before tools (Q7) separate from sufficiency
- Source diversity gate concept (just needs `question_type` wired)
- `content_full` + `content_for_synthesis` dual storage
- Deadline checked at every sleep/call boundary
- Mechanical `mode` forcing from `claims[].inference`
- Incremental JSONL flush

---

## Recommended pre-implementation checklist (≈30 min, saves hours later)

1. **Reconcile** `tool_policy.yaml` with DESIGN §5b (breaker=2, add `per_tool_cumulative_time_cap_s`).
2. **Freeze** `AgentEvent` schema as a typed dataclass/Pydantic model with all kinds including `dropped_context`, `llm_response`.
3. **Rename** `step_id` → `event_id` everywhere; sufficiency uses `matched_event_ids`.
4. **Add** header fields: `question_ref`, `question_type`, `variant`, `refine_disabled`.
5. **Define** JSONL line 0 as `{"kind": "run_header", ...}` and final line as `{"kind": "run_footer", "outcome": ...}`.
6. **Spec** the batch runner CLI that feeds metadata and preserves arXiv rate state.
7. **Clarify** `mode` (grounded/caveated/refused) vs `outcome` (out_of_scope / insufficient_evidence / aborted).

The biggest Tier-2 rework trap is implementing a minimal `steps[]` list now and bolting on `event_id`, `caused_by`, and planner payloads later. Implement the full event union in the first `state.py` commit even if most fields are `None` initially.

---

Want me to draft the reconciled `tool_policy.yaml` and a concrete `AgentEvent` schema next, or start with the batch runner spec?

---
