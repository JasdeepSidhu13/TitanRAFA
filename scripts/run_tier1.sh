#!/usr/bin/env bash
# Tier 1 smoke: import every module and run pure-function + offline pipeline tests.
# Fails fast on import errors, missing dependencies, or test failures.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==> Importing all project modules..."
python3 - <<'PY'
import importlib
import sys

MODULES = [
    "agent",
    "agentstate",
    "checks",
    "constants",
    "groq_client",
    "offline_planner",
    "planner",
    "run_context",
    "synthesizer",
    "fixtures.loader",
    "tools",
    "tools.arxiv",
    "tools.base",
    "tools.common",
    "tools.policy",
    "tools.rate_limit",
    "tools.registry",
    "tools.wikipedia",
]

failed = []
for name in MODULES:
    try:
        importlib.import_module(name)
        print(f"  ok  {name}")
    except Exception as exc:  # noqa: BLE001 — collect all import failures
        failed.append((name, exc))

if failed:
    print("\nImport failures:", file=sys.stderr)
    for name, exc in failed:
        print(f"  {name}: {exc}", file=sys.stderr)
    sys.exit(1)
PY

echo "==> Running Tier 1 tests..."
python3 -m pytest tests/test_pure_functions.py -v --tb=short

echo "==> Tier 1 smoke passed."
