# Tier 2 Comparison (Q4 & Q6: single_pass vs refine)

Generated: 2026-08-15T16:33:55.846783+00:00
Experiment ID: `tier2-live-20260815-rerun`
Offline mode: `False`

Paired runs share `question_ref` and `experiment_id`; they differ only by `variant`.

## Live run notes (`tier2-live-20260815-rerun`)

- **Q4 — clean proof point:** Both variants reached `completed` with **arxiv + wikipedia** in `tools_used`. Sufficiency passed on round 0 for both; refine did not change outcome (no extra plan cycles). Confirms multi-tool diversity gate passes live when both tools return evidence.
- **Q6 — same Tier 1 routing gap (pre-fix):** arXiv **was called** on every plan cycle but returned `empty_result` (`arxiv search returned no entries`). Diversity gate fails with wikipedia-only matched evidence → `insufficient_evidence`. Refine adds a second wikipedia source (`Yield_curve`) but cannot satisfy cross-tool diversity without ok arXiv evidence.

## Post-fix spot-check (`spot-check-20260815`) — not a full Tier 2 re-run

After arXiv query normalization (`prepare_arxiv_search_query`) and planner single-tool routing fix, **Q6 refine only** was re-run live once:

| Q | variant | mode_final | outcome_final | tools_used | Groq |
|---|---------|------------|---------------|------------|------|
| **Q6** | refine | `grounded` | **`completed`** | `arxiv`, `wikipedia` | **2** |

Trace: `traces/55b889f3-6b3d-4c01-b7d8-7269072f15c6.jsonl`. Prior batch rows below are **pre-fix** and left unchanged.

**Note:** Full Tier 2 paired re-run after this fix was not completed due to time — spot-checked Q6 refine only.

## Q4 — `multi_source_synthesis`

**Question:** How did the Federal Reserve's monetary policy response to the 2008 financial crisis differ from its response to COVID-19?

### variant: `single_pass`

**mode_final:** `caveated`  
**outcome_final:** `completed`

**evidence_fingerprint:**
- source_ids: `['arxiv:2007.15419v1', 'wikipedia:Federal_Reserve']`
- tools_used: `['arxiv', 'wikipedia']`

**Trace:** `traces/ffa98845-e7fc-45ca-a0a0-a4f3a6fbe0e3.jsonl`

**Event sequence:** `0:run_header → 1:answerability → 2:plan → 3:tool_result → 4:tool_result → 5:sufficiency → 6:synthesize → 7:run_complete`

**Groq complete() calls:** `2`

### variant: `refine`

**mode_final:** `caveated`  
**outcome_final:** `completed`

**evidence_fingerprint:**
- source_ids: `['arxiv:2007.15419v1', 'wikipedia:Federal_Reserve']`
- tools_used: `['arxiv', 'wikipedia']`

**Trace:** `traces/e7f3dc11-03ea-4129-9646-8703dc9879c3.jsonl`

**Event sequence:** `0:run_header → 1:answerability → 2:plan → 3:tool_result → 4:tool_result → 5:sufficiency → 6:synthesize → 7:run_complete`

**Groq complete() calls:** `2`

## Q6 — `cross_tool_synthesis`

**Question:** Explain the relationship between yield curve inversions and recessions. Are there recent academic papers on this topic?

### variant: `single_pass`

**mode_final:** `caveated`  
**outcome_final:** `insufficient_evidence`

**evidence_fingerprint:**
- source_ids: `['wikipedia:Inverted_yield_curve']`
- tools_used: `['wikipedia']`

**Trace:** `traces/e0cd304a-1f8f-4e9e-ae69-af64c8744b14.jsonl`

**Event sequence:** `0:run_header → 1:answerability → 2:plan → 3:tool_result → 4:tool_result → 5:sufficiency → 6:synthesize → 7:run_complete`

**Groq complete() calls:** `3`

### variant: `refine`

**mode_final:** `caveated`  
**outcome_final:** `insufficient_evidence`

**evidence_fingerprint:**
- source_ids: `['wikipedia:Inverted_yield_curve', 'wikipedia:Yield_curve']`
- tools_used: `['wikipedia']`

**Trace:** `traces/752456ce-c4fc-4b33-8c81-9a37b9c71734.jsonl`

**Event sequence:** `0:run_header → 1:answerability → 2:plan → 3:tool_result → 4:tool_result → 5:sufficiency → 6:plan → 7:tool_result → 8:dedup_skip → 9:sufficiency → 10:plan → 11:tool_result → 12:tool_result → 13:sufficiency → 14:synthesize → 15:run_complete`

**Groq complete() calls:** `5`

**Total Groq complete() calls (all 4 runs):** `12`
