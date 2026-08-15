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
