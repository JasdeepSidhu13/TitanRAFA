# TitanRAFA

Banking research agent with inspectable JSONL traces, rule-based answerability/sufficiency gates, and Groq-powered planner/synthesizer.

## Tier 1 — verified ✅

Live batch run **`tier1-20260815-verify`** (see `outputs/tier1_results.md`):

| Q | Type | mode_final | outcome_final | Groq calls | Tool calls executed |
|---|------|------------|---------------|------------|---------------------|
| Q1 | single_source_factual | grounded | completed | 3 | wikipedia×1 (fail), arxiv×1 (ok) |
| Q2 | single_source_factual | grounded | completed | 2 | wikipedia×1 (fail), arxiv×1 (ok) |
| Q3 | academic_search | grounded | completed | 2 | arxiv×1 (ok), wikipedia×1 (fail) |
| Q4 | multi_source_synthesis | caveated | insufficient_evidence | 4 | wikipedia×1 (fail), arxiv×1 (ok) — diversity gate fired |
| Q5 | data_retrieval | caveated | insufficient_evidence | 4 | wikipedia×1 (fail), arxiv×1 (ok) — fred not registered |
| Q6 | cross_tool_synthesis | caveated | insufficient_evidence | 4 | wikipedia×2, arxiv×2 — diversity gate fired |
| Q7 | out_of_scope | refused | out_of_scope | 0 | none (answerability only) |
| Q8 | speculative | caveated | completed | 2 | wikipedia×1 (fail), arxiv×1 (ok) — inference:true claim |

Tool column legend: `wikipedia×1` = one Wikipedia call attempted; `(ok)` = `tool_result.ok=true`; `(fail)` = `tool_result.ok=false` (live batch: most Wikipedia calls returned HTTP 403).

**Batch totals:** 24 Groq `complete()` HTTP calls · 16 tool executions (wikipedia 8, arxiv 8; 7 ok) · 9 dedup skips

**Tests:** `bash scripts/run_tier1.sh` (29) + `pytest tests/` (45) — all passing

**Artifacts:** `outputs/tier1_results.md` + 8 live traces under `traces/` (experiment id in each `run_header`)

## Prerequisites

- Python 3.12+
- `GROQ_API_KEY` (required for live runs)
- Optional: `FRED_API_KEY` (Tier 3 — not wired in Tier 1)

## Setup

```bash
git clone <repo-url>
cd TitanRAFA
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and set GROQ_API_KEY=...
```

## Single question (CLI)

```bash
source .env  # or export GROQ_API_KEY=...
python3 agent.py "What is the Federal Reserve discount window?" \
  --question-ref Q1 --question-type single_source_factual
```

Stdout includes **Answer**, **Citations**, **mode_final**, **outcome_final**, and **Trace** path.

### Offline mode (no API key)

```bash
OFFLINE_MODE=1 python3 agent.py --offline "What is GDP?" \
  --question-type single_source_factual
```

## Batch runner (all 8 reference questions)

Single long-lived process — preserves arXiv rate-limit state across questions.

```bash
source .env
python3 -m scripts.run_reference
```

Writes `outputs/tier1_results.md` with per-question results and trace paths.  
Offline: `OFFLINE_MODE=1 python3 -m scripts.run_reference --offline`

## Tier 2 comparison (Q4 & Q6)

Paired runs: `single_pass` (refine disabled) vs `refine` (refine enabled).

```bash
source .env
python3 tier2.py
# or: SINGLE_PASS=1 python3 agent.py "..." --single-pass --question-ref Q4 ...
```

Writes `outputs/tier2_comparison.md` with mode/outcome, evidence_fingerprint, trace path, event sequence, and per-run Groq call counts. Offline: `OFFLINE_MODE=1 python3 tier2.py --offline`

## Tier 1 smoke tests

```bash
bash scripts/run_tier1.sh
python3 -m pytest tests/ -v
```

## Configuration

| File | Purpose |
|---|---|
| `config/DESIGN.md` | Architecture source of truth |
| `config/tool_policy.yaml` | Retry, rate limits, loop bounds |
| `config/reference_questions.md` | Q1–Q8 with canonical `question_type` tags |

## Traces

Each run writes `traces/{run_id}.jsonl`:
- First line: `run_header`
- Last line: `run_complete` (mode_final, outcome_final, refusal_reason, evidence_fingerprint)

## Development

- `SINGLE_PASS=1` disables refine rounds (Tier 2 A/B)
- Trace schema: `agentstate.py`
- Prompt interaction log: `prompt-log.md` (append-only)

## Performance & Limitations

| Fix | Status | Evidence |
|-----|--------|----------|
| **Q6 arXiv `empty_result`** | **Fixed** | Prior query `(yield curve inversion) AND (recession) AND (2020:2024)` returned no entries; `prepare_arxiv_search_query()` strips Boolean/date syntax before the API call. Post-fix Q6 refine spot-check: `completed`, `tools_used=['arxiv','wikipedia']`, 2 Groq calls. |
| **Planner over-calling both tools on `single_source_factual`** | **Fixed** | Planner prompt now instructs single-tool routing for `single_source_factual`. Post-fix Q1 spot-check: planner proposed **wikipedia only**, `completed`, 2 Groq calls. |

Full Tier 1 batch re-verification after these fixes was **not** completed due to time — spot-checked on **Q1** and **Q6** only.

Known remaining limits:
- arXiv rate limiting makes full live batches slow; use `OFFLINE_MODE=1` for CI.
- FRED (`data_retrieval` / Q5) is not wired in Tier 1–2.
- Planner behavior is LLM-dependent; prompt fixes reduce but do not eliminate mis-routing.
- Tier 2 comparison file still shows pre-fix Q6 paired runs; only post-fix Q6 refine spot-check is recorded above.

## What I'd do with more time

1. Re-run full Tier 1 batch and Tier 2 paired comparison live post-fix.
2. Wire FRED for Q5 (`data_retrieval`) and extend diversity gate for data + narrative sources.
3. Add deterministic post-planner validation: cap `single_source_factual` / `academic_search` to one tool when the plan proposes two.
4. Harden arXiv query shaping in the planner repair loop (reject Boolean syntax before tool invoke).
5. Merge Tier 1 Wikipedia User-Agent fix narrative into main README verification table (post-merge cleanup).
