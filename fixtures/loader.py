"""Offline fixture loading for inspectable runs without API keys.

Responsibility:
    When OFFLINE_MODE=1 or --offline is set, replay canned tool and LLM
    responses from tests/fixtures/ so a full trace is produced without
    network access. Part of Tier 1 happy path per DESIGN.md §10.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# Recorded tool fixtures live under tests/fixtures/ (Tier 1 baseline).
FIXTURES_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures"

# Module-level offline flag set by agent CLI via set_offline_mode().
_offline_cli_flag: bool = False


def set_offline_mode(enabled: bool) -> None:
    """Set CLI --offline flag for tools to read without circular imports."""
    global _offline_cli_flag
    _offline_cli_flag = enabled


def is_offline_mode(cli_offline: bool = False) -> bool:
    """Return True when offline replay mode is active.

    Description:
        Checks CLI flag (set via set_offline_mode), --offline arg, or
        OFFLINE_MODE env var (1/true/yes).

    Input:
        cli_offline: Value of argparse --offline flag when calling directly.

    Output:
        True if offline fixtures should be used.

    When to use:
        Tool invoke paths and agent startup.

    When not to use:
        N/A.
    """
    if cli_offline or _offline_cli_flag:
        return True
    return os.environ.get("OFFLINE_MODE", "").lower() in {"1", "true", "yes"}


def load_tool_fixture(tool_name: str, query: str) -> dict[str, Any]:
    """Load a recorded tool response from tests/fixtures/{tool_name}.json.

    Description:
        Primary offline data source for WikipediaTool and ArxivTool.

    Input:
        tool_name: e.g. ``wikipedia``, ``arxiv``.
        query: Query string (reserved for per-query fixture selection).

    Output:
        Dict with ToolResult-compatible fields including citation.

    When to use:
        Inside tool ``invoke`` when offline mode is active.

    When not to use:
        Live API runs.
    """
    path = FIXTURES_DIR / f"{tool_name}.json"
    if path.exists():
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)

    return {
        "ok": False,
        "reason": f"no offline fixture at {path}",
        "failure_class": "empty_result",
        "source_id": None,
        "content_full": "",
        "content_for_synthesis": "",
        "truncated": False,
    }


def load_planner_fixture() -> dict[str, Any]:
    """Return canned planner output for offline mode."""
    return {
        "tool_calls_proposed": [
            {"tool": "wikipedia", "query": "Federal Reserve discount window"}
        ],
        "tool_calls_after_validation": [
            {"tool": "wikipedia", "query": "Federal Reserve discount window"}
        ],
        "validation_errors": [],
        "repair_count": 0,
        "model_id": "offline-fixture",
    }


def load_synthesizer_fixture() -> dict[str, Any]:
    """Return canned synthesizer output for offline mode."""
    return {
        "mode_model": "grounded",
        "mode_enforced": "grounded",
        "claims_raw": [
            {
                "text": "The discount window lets banks borrow reserves from the Fed.",
                "source_id": "wikipedia:Discount_window",
                "inference": False,
            }
        ],
        "claims_validated": [
            {
                "text": "The discount window lets banks borrow reserves from the Fed.",
                "source_id": "wikipedia:Discount_window",
                "inference": False,
            }
        ],
        "context_event_ids": [],
        "chars_fed": 0,
        "model_id": "offline-fixture",
    }
