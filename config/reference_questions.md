# Reference Test Questions

Run all 8. Include outputs in submission (`outputs/tier1_results.md`).
Type tags indicate what the question is meant to exercise — not a
guarantee of a "correct" answer per the brief ("agent does not need to
ace every question — they evaluate how it handles each type").

| # | Question | Type | Expected synthesizer mode |
|---|---|---|---|
| 1 | What is the Federal Reserve's discount window and how does it work? | Single-source factual | grounded |
| 2 | What are the Basel III capital requirements for banks? | Single-source factual | grounded |
| 3 | What recent academic research exists on using machine learning for credit risk assessment? | Academic search | grounded |
| 4 | How did the Federal Reserve's monetary policy response to the 2008 financial crisis differ from its response to COVID-19? | Multi-source synthesis | grounded (multi-step) |
| 5 | What is the current US unemployment rate and how has it changed over the past year? | Data retrieval (FRED) | grounded (Tier 3 only; caveated/refused pre-Tier-3 with note that FRED isn't wired up yet) |
| 6 | Explain the relationship between yield curve inversions and recessions. Are there recent academic papers on this topic? | Cross-tool synthesis | grounded (multi-step) |
| 7 | What is the best restaurant in New York City? | Out-of-scope | refused |
| 8 | What are the implications of quantum computing for banking encryption? | Speculative / emerging | caveated |

## Notes for the multi-step comparison (Tier 2)

Run Q4 and Q6 twice each: once with `SINGLE_PASS=1` (refine disabled),
once with refine enabled. Both outputs go in `outputs/tier2_comparison.md`
alongside their trace file paths.
