#!/usr/bin/env python3
"""Batch runner: all reference questions in one long-lived process.

Responsibility:
    Executes every question in config/reference_questions.md sequentially,
    preserving arXiv rate-limit state, and writes outputs/tier1_results.md.

Role in architecture:
    Required Tier-1 scaffolding per config/DESIGN.md §6a.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from agent import run_question
from fixtures.loader import is_offline_mode, set_offline_mode
from run_result import format_tier1_section
from scripts.reference_loader import load_reference_questions

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "outputs" / "tier1_results.md"


def run_tier1_batch(*, offline: bool = False, experiment_id: str | None = None) -> Path:
    """Run all reference questions and write tier1_results.md.

    Description:
        Single-process sequential execution. Sets question_ref and
        question_type on each run header from the reference table.

    Input:
        offline: Use OFFLINE_MODE fixtures.
        experiment_id: Optional batch experiment id for traces.

    Output:
        Path to outputs/tier1_results.md.

    When to use:
        ``python -m scripts.run_reference`` or ``make tier1``.

    When not to use:
        Single-question debugging — use ``python agent.py``.
    """
    set_offline_mode(offline)
    questions = load_reference_questions()
    if not questions:
        raise RuntimeError("No reference questions parsed from config/reference_questions.md")

    batch_id = experiment_id or f"tier1-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    sections: list[str] = [
        "# Tier 1 Reference Question Results",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        f"Experiment ID: `{batch_id}`",
        f"Offline mode: `{offline}`",
        "",
    ]

    for ref_q in questions:
        print(f"==> Running {ref_q.question_ref}: {ref_q.question[:60]}...", file=sys.stderr)
        result = run_question(
            ref_q.question,
            question_ref=ref_q.question_ref,
            question_type=ref_q.question_type,
            offline=offline,
            experiment_id=batch_id,
        )
        sections.append(format_tier1_section(result))
        print(format_cli_summary(result), file=sys.stderr)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text("\n".join(sections), encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH}", file=sys.stderr)
    return OUTPUT_PATH


def format_cli_summary(result) -> str:
    """One-line stderr summary per question."""
    return (
        f"  {result.question_ref} mode_final={result.mode_final} "
        f"outcome_final={result.outcome_final} trace={result.trace_path}"
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entry for batch runner."""
    parser = argparse.ArgumentParser(description="Run all reference questions (Tier 1)")
    parser.add_argument("--offline", action="store_true", help="Replay offline fixtures")
    parser.add_argument("--experiment-id", default=None, help="Batch experiment id")
    args = parser.parse_args(argv)

    offline = is_offline_mode(args.offline)
    try:
        run_tier1_batch(offline=offline, experiment_id=args.experiment_id)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
