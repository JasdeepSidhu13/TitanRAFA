# Tier 2 Comparison (Q4 & Q6: single_pass vs refine)

Generated: 2026-08-15T16:27:50.573694+00:00
Experiment ID: `tier2-live-20260815`
Offline mode: `False`

Paired runs share `question_ref` and `experiment_id`; they differ only by `variant`.

## Live run notes (`tier2-live-20260815`)

- **Q4 — clean proof point:** Both variants reached `completed` with **arxiv + wikipedia** in `tools_used`. Sufficiency passed on round 0 for both; refine did not change outcome (no extra plan cycles). Confirms multi-tool diversity gate can pass live when both tools return evidence.
- **Q6 — same Tier 1 pattern (not debugged):** arXiv **was called** on every plan cycle but returned `empty_result` (`arxiv search returned no entries`). Diversity gate fails with wikipedia-only matched evidence → `insufficient_evidence`. Refine adds a second wikipedia source (`Yield_curve`) but cannot satisfy cross-tool diversity without ok arXiv evidence.

## Q4 — `multi_source_synthesis`

**Question:** How did the Federal Reserve's monetary policy response to the 2008 financial crisis differ from its response to COVID-19?

### variant: `single_pass`

**mode_final:** `caveated`  
**outcome_final:** `completed`

**evidence_fingerprint:**
- source_ids: `['arxiv:2007.15419v1', 'wikipedia:Federal_Reserve']`
- tools_used: `['arxiv', 'wikipedia']`

**Trace:** `traces/0d178930-3a1a-47a1-a410-ade7b00f3afe.jsonl`

**Event sequence:** `0:run_header → 1:answerability → 2:plan → 3:tool_result → 4:tool_result → 5:sufficiency → 6:synthesize → 7:run_complete`

**Groq complete() calls:** `2`

### variant: `refine`

**mode_final:** `caveated`  
**outcome_final:** `completed`

**evidence_fingerprint:**
- source_ids: `['arxiv:2007.15419v1', 'wikipedia:Federal_Reserve']`
- tools_used: `['arxiv', 'wikipedia']`

**Trace:** `traces/36d514b1-574f-4dcb-bb1e-eeb364434ff3.jsonl`

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

**Trace:** `traces/7065cc22-ef6c-41c5-8848-7e0deb3f6613.jsonl`

**Event sequence:** `0:run_header → 1:answerability → 2:plan → 3:tool_result → 4:tool_result → 5:sufficiency → 6:synthesize → 7:run_complete`

**Groq complete() calls:** `3`

### variant: `refine`

**mode_final:** `caveated`  
**outcome_final:** `insufficient_evidence`

**evidence_fingerprint:**
- source_ids: `['wikipedia:Inverted_yield_curve', 'wikipedia:Yield_curve']`
- tools_used: `['wikipedia']`

**Trace:** `traces/09dfdc5f-03a4-4984-abc2-fb0a0cace695.jsonl`

**Event sequence:** `0:run_header → 1:answerability → 2:plan → 3:tool_result → 4:tool_result → 5:sufficiency → 6:plan → 7:tool_result → 8:dedup_skip → 9:sufficiency → 10:plan → 11:tool_result → 12:tool_result → 13:sufficiency → 14:synthesize → 15:run_complete`

**Groq complete() calls:** `5`

**Total Groq complete() calls (all 4 runs):** `12`
