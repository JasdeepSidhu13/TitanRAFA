# Tier 2 Comparison (Q4 & Q6: single_pass vs refine)

Generated: 2026-08-15T16:23:40.311729+00:00
Experiment ID: `tier2-offline-committed`
Offline mode: `True`

Paired runs share `question_ref` and `experiment_id`; they differ only by `variant`.

## Q4 — `multi_source_synthesis`

**Question:** How did the Federal Reserve's monetary policy response to the 2008 financial crisis differ from its response to COVID-19?

### variant: `single_pass`

**mode_final:** `caveated`  
**outcome_final:** `insufficient_evidence`

**evidence_fingerprint:**
- source_ids: `['wikipedia:Discount_window']`
- tools_used: `['wikipedia']`

**Trace:** `traces/70f08dd9-ce26-4ca9-ae41-47d76ca6a2c3.jsonl`

**Event sequence:** `0:run_header → 1:answerability → 2:plan → 3:tool_result → 4:tool_result → 5:sufficiency → 6:synthesize → 7:run_complete`

**Groq complete() calls:** `0`

### variant: `refine`

**mode_final:** `caveated`  
**outcome_final:** `insufficient_evidence`

**evidence_fingerprint:**
- source_ids: `['arxiv:2301.00001', 'wikipedia:Discount_window']`
- tools_used: `['arxiv', 'wikipedia']`

**Trace:** `traces/be9675d1-2663-4bc0-a981-e69a5832bc76.jsonl`

**Event sequence:** `0:run_header → 1:answerability → 2:plan → 3:tool_result → 4:tool_result → 5:sufficiency → 6:plan → 7:tool_result → 8:sufficiency → 9:plan → 10:dedup_skip → 11:sufficiency → 12:synthesize → 13:run_complete`

**Groq complete() calls:** `0`

## Q6 — `cross_tool_synthesis`

**Question:** Explain the relationship between yield curve inversions and recessions. Are there recent academic papers on this topic?

### variant: `single_pass`

**mode_final:** `caveated`  
**outcome_final:** `insufficient_evidence`

**evidence_fingerprint:**
- source_ids: `['arxiv:2301.00001']`
- tools_used: `['arxiv']`

**Trace:** `traces/6edf73a9-bb8d-4194-963d-1e1b00f65acd.jsonl`

**Event sequence:** `0:run_header → 1:answerability → 2:plan → 3:tool_result → 4:sufficiency → 5:synthesize → 6:run_complete`

**Groq complete() calls:** `0`

### variant: `refine`

**mode_final:** `caveated`  
**outcome_final:** `insufficient_evidence`

**evidence_fingerprint:**
- source_ids: `['arxiv:2301.00001']`
- tools_used: `['arxiv']`

**Trace:** `traces/f3efffce-3b25-4a0c-9e88-d716895ef2b4.jsonl`

**Event sequence:** `0:run_header → 1:answerability → 2:plan → 3:tool_result → 4:sufficiency → 5:plan → 6:dedup_skip → 7:sufficiency → 8:plan → 9:dedup_skip → 10:sufficiency → 11:synthesize → 12:run_complete`

**Groq complete() calls:** `0`

**Total Groq complete() calls (all 4 runs):** `0`
