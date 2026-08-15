#!/usr/bin/env python3
"""One-off check: run_complete cross-field invariants for trace JSONL files."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from agentstate import validate_run_complete


def main() -> int:
    trace_dir = REPO / "traces"
    paths = sorted(trace_dir.glob("*.jsonl"))
    if not paths:
        print("No trace files found in traces/")
        return 1

    failures = 0
    for path in paths:
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        complete = json.loads(lines[-1])
        if complete.get("kind") != "run_complete":
            print(f"FAIL {path.name}: last line is not run_complete")
            failures += 1
            continue

        mf = complete.get("mode_final")
        of = complete.get("outcome_final")
        rr = complete.get("refusal_reason")

        checks: list[str] = []
        if mf == "refused":
            if rr is None:
                checks.append("refused but refusal_reason is null")
            if of not in {"out_of_scope", "degraded"}:
                checks.append(f"refused but outcome_final={of}")
        else:
            if rr is not None:
                checks.append(f"mode_final={mf} but refusal_reason={rr!r}")

        if of == "out_of_scope" and mf != "refused":
            checks.append(f"out_of_scope but mode_final={mf}")

        if of == "insufficient_evidence" and mf != "caveated":
            checks.append(f"insufficient_evidence but mode_final={mf}")

        try:
            validate_run_complete(mf, of, rr)
            status = "PASS"
        except Exception as exc:
            status = "FAIL"
            checks.append(str(exc))

        if checks:
            status = "FAIL"
            failures += 1

        print(
            f"{status} {path.name}: mode_final={mf} outcome_final={of} "
            f"refusal_reason={'null' if rr is None else repr(rr)}"
        )
        for c in checks:
            print(f"       -> {c}")

    print(f"\nTotal: {len(paths)} traces, {failures} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
