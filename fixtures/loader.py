"""Offline fixture loading for inspectable runs without API keys.

Responsibility:
    When OFFLINE_MODE=1 or --offline is set, replay canned tool and LLM
    responses so a full trace (run_header through run_complete) is produced
    without network access. Part of Tier 1 happy path per DESIGN.md §10.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

FIXTURES_DIR = Path(__file__).resolve().parent / "data"


def is_offline_mode(cli_offline: bool = False) -> bool:
    """Return True when offline replay mode is active.

    Description:
        Checks ``--offline`` flag or ``OFFLINE_MODE`` env var (1/true/yes).

    Input:
        cli_offline: Value of argparse --offline flag.

    Output:
        True if offline fixtures should be used.

    When to use:
        At agent startup before Groq key validation.

    When not to use:
        N/A.
    """
    if cli_offline:
        return True
    return os.environ.get("OFFLINE_MODE", "").lower() in {"1", "true", "yes"}


def load_tool_fixture(tool_name: str, query: str) -> dict[str, Any]:
    """Load a canned tool response for offline mode.

    Description:
        Stub loader: returns embedded defaults or reads
        ``fixtures/data/<tool_name>.json`` when present.

    Input:
        tool_name: e.g. ``wikipedia``, ``arxiv``.
        query: Query string (may select fixture variant in future).

    Output:
        Dict with keys matching successful ToolResult fields.

    When to use:
        Offline executor path only.

    When not to use:
        Live runs with real API keys.
    """
    path = FIXTURES_DIR / f"{tool_name}.json"
    if path.exists():
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        return data

    # Minimal inline defaults so offline always produces inspectable output.
    defaults: dict[str, dict[str, Any]] = {
        "wikipedia": {
            "ok": True,
            "reason": "offline fixture",
            "source_id": "wikipedia:Discount_window",
            "content_full": (
                "The discount window is a lending facility that allows "
                "eligible institutions to borrow reserves from the Federal Reserve."
            ),
            "content_for_synthesis": (
                "The discount window is a lending facility that allows "
                "eligible institutions to borrow reserves from the Federal Reserve."
            ),
            "truncated": False,
        },
        "arxiv": {
            "ok": True,
            "reason": "offline fixture",
            "source_id": "arxiv:2301.00001",
            "content_full": "Offline arXiv fixture abstract for credit risk research.",
            "content_for_synthesis": "Offline arXiv fixture abstract for credit risk research.",
            "truncated": False,
        },
    }
    return defaults.get(
        tool_name,
        {
            "ok": False,
            "reason": f"no offline fixture for tool={tool_name}",
            "failure_class": "empty_result",
            "source_id": None,
            "content_full": "",
            "content_for_synthesis": "",
            "truncated": False,
        },
    )


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
