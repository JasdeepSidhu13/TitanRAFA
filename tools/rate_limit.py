"""Cross-process rate-limit timestamp persistence for arXiv.

Responsibility:
    Persists last-call epoch per tool to .ratelimit_state.json so
    min_interval_s is honored across separate ``python agent.py`` invocations.

Role in architecture:
    Fallback when the batch runner (DESIGN.md §6a) is not used. The batch
    runner — a single long-lived process for all reference questions — is
    the preferred mechanism for Tier 1 reference runs because it avoids
    file I/O and cannot race across concurrent processes. This file-backed
    store exists so standalone per-question invocations still respect arXiv
    ToU (1 req / 3s) until the batch runner lands later this session.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

RATE_LIMIT_STATE_PATH = Path(".ratelimit_state.json")


class RateLimitStore:
    """Read/write last-call timestamps for a single tool name.

    Description:
        Thread-safe enough for sequential agent use; not for parallel tool
        calls within one process (Tier 1 is sequential per DESIGN.md §5b).

    Input:
        tool_name: Tool key (e.g. ``arxiv``).

    Output:
        Store with get/set last call epoch.

    When to use:
        Passed to ``RetryPolicy`` for arXiv only.

    When not to use:
        Do not use for Wikipedia (1s gate, in-memory is sufficient).
    """

    def __init__(self, tool_name: str, path: Path = RATE_LIMIT_STATE_PATH) -> None:
        self.tool_name = tool_name
        self.path = path

    def get_last_call_epoch(self) -> float:
        """Return last recorded call epoch for this tool, or 0."""
        if not self.path.exists():
            return 0.0
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return float(data.get(self.tool_name, {}).get("last_call_epoch", 0.0))
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            return 0.0

    def set_last_call_epoch(self, epoch: float) -> None:
        """Persist last call epoch, merging with existing tool entries."""
        data: dict = {}
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                data = {}
        data.setdefault(self.tool_name, {})["last_call_epoch"] = epoch
        self.path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def seconds_since_last_call(self) -> float:
        """Wall-clock seconds since last persisted call."""
        last = self.get_last_call_epoch()
        if last <= 0:
            return float("inf")
        return time.time() - last

    def record_call_now(self) -> None:
        """Record current wall time as last call."""
        self.set_last_call_epoch(time.time())
