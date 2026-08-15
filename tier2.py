#!/usr/bin/env python3
"""Tier 2 comparison runner: Q4 and Q6 × single_pass vs refine.

Responsibility:
    Executes paired runs per question_ref with shared experiment_id and
    differing variant only; writes outputs/tier2_comparison.md.

Role in architecture:
    Tier 2 A/B per config/reference_questions.md and config/DESIGN.md §6b.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from agent import run_question
from env_loader import load_dotenv
from fixtures.loader import is_offline_mode, set_offline_mode
from groq_client import get_groq_complete_call_count, reset_groq_complete_call_count
from run_result import (
    RunResult,
    format_tier2_question_section,
    format_tier2_variant_section,
    read_event_sequence,
)
from scripts.reference_loader import ReferenceQuestion, load_reference_questions

OUTPUT_PATH = Path(__file__).resolve().parent / "outputs" / "tier2_comparison.md"
TIER2_QUESTION_REFS = frozenset({"Q4", "Q6"})


def load_tier2_questions() -> list[ReferenceQuestion]:
    """Return Q4 and Q6 rows from config/reference_questions.md."""
    questions = [
        q for q in load_reference_questions() if q.question_ref in TIER2_QUESTION_REFS
    ]
    if len(questions) != len(TIER2_QUESTION_REFS):
        found = {q.question_ref for q in questions}
        missing = TIER2_QUESTION_REFS - found
        raise RuntimeError(f"Missing Tier 2 reference questions: {sorted(missing)}")
    return sorted(questions, key=lambda q: q.number)


def run_tier2_comparison(
    *,
    offline: bool = False,
    experiment_id: str | None = None,
) -> Path:
    """Run Q4/Q6 single_pass vs refine pairs and write tier2_comparison.md.

    Description:
        Four runs total (2 questions × 2 variants). Each pair shares
        question_ref and experiment_id; variant differs for auto-pairing.

    Input:
        offline: Replay fixtures without API keys.
        experiment_id: Optional shared experiment id for all four runs.

    Output:
        Path to outputs/tier2_comparison.md.

    When to use:
        ``python tier2.py`` or ``python -m tier2``.

    When not to use:
        Full Tier 1 batch — use ``python -m scripts.run_reference``.
    """
    set_offline_mode(offline)
    load_dotenv()
    batch_id = experiment_id or f"tier2-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    questions = load_tier2_questions()

    sections: list[str] = [
        "# Tier 2 Comparison (Q4 & Q6: single_pass vs refine)",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        f"Experiment ID: `{batch_id}`",
        f"Offline mode: `{offline}`",
        "",
        "Paired runs share `question_ref` and `experiment_id`; they differ only by `variant`.",
        "",
    ]

    total_groq = 0
    for ref_q in questions:
        print(f"==> Tier 2 {ref_q.question_ref}: {ref_q.question[:60]}...", file=sys.stderr)
        variant_blocks: list[str] = []
        for single_pass, variant in ((True, "single_pass"), (False, "refine")):
            reset_groq_complete_call_count()
            label = "single_pass (refine disabled)" if single_pass else "refine (refine enabled)"
            print(f"    variant={variant} ({label})", file=sys.stderr)
            result = run_question(
                ref_q.question,
                question_ref=ref_q.question_ref,
                question_type=ref_q.question_type,
                offline=offline,
                variant=variant,
                experiment_id=batch_id,
                single_pass=single_pass,
            )
            groq_calls = get_groq_complete_call_count()
            total_groq += groq_calls
            event_sequence = read_event_sequence(result.trace_path)
            _assert_trace_pairing(result, variant=variant, experiment_id=batch_id)
            variant_blocks.append(
                format_tier2_variant_section(
                    result,
                    groq_calls=groq_calls,
                    event_sequence=event_sequence,
                )
            )
            print(
                f"      {variant} mode_final={result.mode_final} "
                f"outcome_final={result.outcome_final} groq={groq_calls} "
                f"trace={result.trace_path}",
                file=sys.stderr,
            )
        sections.append(
            format_tier2_question_section(
                ref_q.question_ref,
                ref_q.question_type,
                ref_q.question,
                variant_blocks,
            )
        )

    sections.append(f"**Total Groq complete() calls (all 4 runs):** `{total_groq}`")
    sections.append("")
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text("\n".join(sections), encoding="utf-8")
    print(f"Total Groq complete() call count: {total_groq}", file=sys.stderr)
    print(f"Wrote {OUTPUT_PATH}", file=sys.stderr)
    return OUTPUT_PATH


def _assert_trace_pairing(result: RunResult, *, variant: str, experiment_id: str) -> None:
    """Verify run_header fields needed for Tier 2 auto-pairing."""
    header = json.loads(Path(result.trace_path).read_text(encoding="utf-8").splitlines()[0])
    if header.get("question_ref") != result.question_ref:
        raise RuntimeError(f"trace question_ref mismatch: {result.trace_path}")
    if header.get("variant") != variant:
        raise RuntimeError(
            f"trace variant={header.get('variant')!r} expected {variant!r}: {result.trace_path}"
        )
    if header.get("experiment_id") != experiment_id:
        raise RuntimeError(f"trace experiment_id mismatch: {result.trace_path}")
    if variant == "single_pass" and not header.get("refine_disabled"):
        raise RuntimeError(f"single_pass run missing refine_disabled: {result.trace_path}")
    if variant == "refine" and header.get("refine_disabled"):
        raise RuntimeError(f"refine run has refine_disabled=true: {result.trace_path}")


def main(argv: list[str] | None = None) -> int:
    """CLI entry for Tier 2 comparison runner."""
    parser = argparse.ArgumentParser(
        description="Tier 2: Q4 and Q6 × single_pass vs refine comparison"
    )
    parser.add_argument("--offline", action="store_true", help="Replay offline fixtures")
    parser.add_argument("--experiment-id", default=None, help="Shared experiment id for pairing")
    args = parser.parse_args(argv)

    offline = is_offline_mode(args.offline)
    load_dotenv()
    try:
        run_tier2_comparison(offline=offline, experiment_id=args.experiment_id)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
