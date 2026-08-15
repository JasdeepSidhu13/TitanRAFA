# Tier 1 Reference Question Results

Generated: 2026-08-15T16:07:04.133609+00:00
Experiment ID: `tier1-20260815-ua-fix`
Offline mode: `False`

## Post-fix spot-check (`spot-check-20260815`) — not a full batch re-verification

After planner single-tool routing fix, **Q1 only** was re-run live (refine variant):

| Q | mode_final | outcome_final | tools_used | Groq calls |
|---|------------|---------------|------------|------------|
| **Q1** | `grounded` | `completed` | `['wikipedia']` only | **2** |

Trace: `traces/0396332b-d792-4e5a-8e45-ff68b801b60d.jsonl`. Planner proposed **one** tool (`wikipedia`); no arXiv call. Full Tier 1 batch re-verification after this fix was **not** completed due to time.

Rows below are from batch `tier1-20260815-ua-fix` (pre planner-routing fix).

## Q1 — `single_source_factual`

**Question:** What is the Federal Reserve's discount window and how does it work?

**mode_final:** `grounded`  
**outcome_final:** `completed`

**evidence_fingerprint:**
- source_ids: `['wikipedia:Discount_window']`
- tools_used: `['wikipedia']`

**Answer:**

The Federal Reserve's discount window is an instrument of monetary policy. The discount window allows eligible institutions to borrow money from the central bank. The discount window is used to meet temporary shortages of liquidity caused by internal or external disruptions. The discount window is usually used on a short-term basis.

**Citations:**

- `wikipedia:Discount_window` — Discount window

**Trace:** `traces/74728a3d-9e33-4ce7-b0c2-48870792f595.jsonl`

## Q2 — `single_source_factual`

**Question:** What are the Basel III capital requirements for banks?

**mode_final:** `grounded`  
**outcome_final:** `completed`

**evidence_fingerprint:**
- source_ids: `['arxiv:1211.5517v1', 'wikipedia:Basel_III']`
- tools_used: `['arxiv', 'wikipedia']`

**Answer:**

Basel III is a framework that sets international standards and minimums for bank capital requirements, stress tests, liquidity regulations, and leverage. Basel III was developed in response to the deficiencies in financial regulation revealed by the 2008 financial crisis. Basel III introduces new capital charges for CVA. Basel III aims to mitigate the risk of bank runs and bank failures. CDSs can provide capital relief under Basel III. The capital relief provided by CDSs can be priced in, resulting in differential pricing for IMM and non-IMM banks. Up to 50% of observed CDS spread could be due to priced in capital relief.

**Citations:**

- `wikipedia:Basel_III` — Basel III
- `arxiv:1211.5517v1` — CDS pricing under Basel III: capital relief and default protection

**Trace:** `traces/cefee3f7-6a8a-40f8-8e96-2a601221e558.jsonl`

## Q3 — `academic_search`

**Question:** What recent academic research exists on using machine learning for credit risk assessment?

**mode_final:** `grounded`  
**outcome_final:** `completed`

**evidence_fingerprint:**
- source_ids: `['arxiv:2306.04338v1', 'wikipedia:Credit_risk']`
- tools_used: `['arxiv', 'wikipedia']`

**Answer:**

Recent academic research exists on using machine learning for credit risk assessment. Credit risk is the chance that a borrower does not repay a loan or fulfill a loan obligation. Measures of borrowing costs such as yield spreads can be used to infer credit risk levels based on assessments by market participants. Machine learning-based official statistics can maintain integrity, reliability, consistency, and relevance in policy-making, decision-making, and public discourse.

**Citations:**

- `arxiv:2306.04338v1` — Changing Data Sources in the Age of Machine Learning for Official Statistics
- `wikipedia:Credit_risk` — Credit risk

**Trace:** `traces/94dcd63c-7556-42a3-8e7f-b447888941b9.jsonl`

## Q4 — `multi_source_synthesis`

**Question:** How did the Federal Reserve's monetary policy response to the 2008 financial crisis differ from its response to COVID-19?

**mode_final:** `caveated`  
**outcome_final:** `completed`

**evidence_fingerprint:**
- source_ids: `['arxiv:2007.15419v1', 'wikipedia:Federal_Reserve']`
- tools_used: `['arxiv', 'wikipedia']`

**Answer:**

The Federal Reserve's monetary policy response to the 2008 financial crisis differed from its response to COVID-19. The Federal Reserve implemented expansionary monetary policy in response to the COVID-19 recession. The monetary expansion caused higher output growth and stock market returns in response to the COVID-19 recession. The Federal Reserve's monetary policy response to the 2008 financial crisis is not explicitly described in the provided evidence.

**Citations:**

- `arxiv:2007.15419v1` — Measuring the Effectiveness of US Monetary Policy during the COVID-19 Recession
- `wikipedia:Federal_Reserve` — Federal Reserve

**Trace:** `traces/8c39353c-5d1e-464b-a984-f00143c2b337.jsonl`

## Q5 — `data_retrieval`

**Question:** What is the current US unemployment rate and how has it changed over the past year?

**mode_final:** `caveated`  
**outcome_final:** `insufficient_evidence`

**evidence_fingerprint:**
- source_ids: `['arxiv:2304.00544v1', 'wikipedia:List_of_countries_by_unemployment_rate']`
- tools_used: `['arxiv', 'wikipedia']`

**Answer:**

The unemployment rate varies across countries due to differences in calculation and presentation methods. The cyclicality of occupational mobility shapes the aggregate unemployment rate and its duration distribution. The US unemployment rate has fluctuated over the business cycle.

**Citations:**

- `wikipedia:List_of_countries_by_unemployment_rate` — List of countries by unemployment rate
- `arxiv:2304.00544v1` — Unemployment and Endogenous Reallocation over the Business Cycle

**Trace:** `traces/bb755796-deb0-4d16-9958-cba635234c72.jsonl`

## Q6 — `cross_tool_synthesis`

**Question:** Explain the relationship between yield curve inversions and recessions. Are there recent academic papers on this topic?

**mode_final:** `caveated`  
**outcome_final:** `insufficient_evidence`

**evidence_fingerprint:**
- source_ids: `['wikipedia:Inverted_yield_curve', 'wikipedia:Yield_curve']`
- tools_used: `['wikipedia']`

**Answer:**

In finance, an inverted yield curve is a yield curve in which short-term debt instruments have a greater yield than longer term bonds. An inverted yield curve is an unusual phenomenon; bonds with shorter maturities generally provide lower yields than longer term bonds. A yield curve shows the relationship between yields and time to maturity for a set of comparable debt securities. In practice the term usually refers to curves built from a single issuer or market segment so that credit quality and other features are as similar as possible, for example the U.S. Trea A yield curve shows the relationship between yields and time to maturity for a set of comparable debt securities. In practice the term usually refers to curves built from a single issuer or market segment so that credit quality and other features are as similar as possible, for example the U.S. Trea

**Citations:**

- `wikipedia:Inverted_yield_curve` — Inverted yield curve
- `wikipedia:Yield_curve` — Yield curve

**Trace:** `traces/e9f2e325-d0af-4278-8769-2d69ec3df8ae.jsonl`

## Q7 — `out_of_scope`

**Question:** What is the best restaurant in New York City?

**mode_final:** `refused`  
**outcome_final:** `out_of_scope`

**evidence_fingerprint:**
- source_ids: `[]`
- tools_used: `[]`

**Answer:**

question_type=out_of_scope: subjective or non-citable question

**Citations:**

- (none)

**Trace:** `traces/fbc53f23-6893-40f4-8858-92b66e0fde13.jsonl`

## Q8 — `speculative`

**Question:** What are the implications of quantum computing for banking encryption?

**mode_final:** `caveated`  
**outcome_final:** `completed`

**evidence_fingerprint:**
- source_ids: `['arxiv:1109.3235v1']`
- tools_used: `['arxiv']`

**Answer:**

Quantum computing poses a threat to banking encryption. Signed quantum key establishment is a viable alternative to traditional public-key infrastructure. The implications of quantum computing for banking encryption are still being researched and developed.

**Citations:**

- `arxiv:1109.3235v1` — A new spin on quantum cryptography: Avoiding trapdoors and embracing public keys

**Trace:** `traces/36bed714-d7b9-406c-9945-624ac1fe8c9a.jsonl`

**Groq complete() calls (live HTTP successes):** `21`
