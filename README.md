# TitanRAFA

Banking research agent with inspectable JSONL traces, rule-based answerability/sufficiency gates, and Groq-powered planner/synthesizer.

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
