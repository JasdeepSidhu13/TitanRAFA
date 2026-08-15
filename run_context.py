"""Run deadline and loop-counter state for the orchestrator.

Responsibility:
    Enforces RUN_TIMEOUT_S as a checked monotonic deadline and tracks
    plan/tool/refine counters per DESIGN.md §5b.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from constants import LoopBounds


@dataclass
class RunContext:
    """Mutable per-run counters and deadline for orchestration.

    Description:
        ``max_planner_cycles`` counts total ``plan`` events across all refine
        rounds. ``max_refine_rounds`` is the highest permitted ``refine_round``
        index (0-indexed).

    Input:
        bounds: Loaded loop_bounds from tool_policy.yaml.

    Output:
        Context passed through plan/execute/sufficiency/synthesize.

    When to use:
        Created once at run start; threaded through the agent loop.

    When not to use:
        N/A.
    """

    bounds: LoopBounds
    deadline_monotonic: float = field(default=0.0)
    tool_calls_executed: int = 0
    consecutive_tool_failures: dict[str, int] = field(default_factory=dict)
    tool_cumulative_seconds: dict[str, float] = field(default_factory=dict)
    groq_consecutive_429: int = 0
    groq_degraded_reason: Optional[str] = None
    aborted_reason: Optional[str] = None

    @classmethod
    def from_bounds(cls, bounds: LoopBounds) -> RunContext:
        """Create context with deadline set from run_timeout_s."""
        return cls(
            bounds=bounds,
            deadline_monotonic=time.monotonic() + bounds.run_timeout_s,
        )

    def remaining_s(self) -> float:
        """Seconds remaining before run deadline."""
        return max(0.0, self.deadline_monotonic - time.monotonic())

    def has_budget(self, needed_s: float = 0.0) -> bool:
        """Return False when remaining time is insufficient for needed_s."""
        return self.remaining_s() > needed_s

    def deadline_for_tools(self) -> float:
        """Monotonic deadline passed to tool RetryPolicy."""
        return self.deadline_monotonic

    def mark_groq_429(self, reason: str, *, threshold: int) -> None:
        """Track consecutive Groq 429 responses for mass-429 degradation."""
        self.groq_consecutive_429 += 1
        if self.groq_consecutive_429 >= threshold:
            self.groq_degraded_reason = reason

    def clear_groq_429(self) -> None:
        """Reset consecutive 429 counter after a successful Groq call."""
        self.groq_consecutive_429 = 0

    def circuit_open(self, tool_name: str) -> bool:
        """Return True when consecutive failures tripped the circuit breaker."""
        return (
            self.consecutive_tool_failures.get(tool_name, 0)
            >= self.bounds.circuit_breaker_consecutive_failures
        )

    def tool_time_cap_hit(self, tool_name: str) -> bool:
        """Return True when per-tool cumulative time cap is exhausted."""
        return (
            self.tool_cumulative_seconds.get(tool_name, 0.0)
            >= self.bounds.per_tool_cumulative_time_cap_s
        )

    def record_tool_result(self, tool_name: str, ok: bool, duration_s: float) -> None:
        """Update failure streaks and cumulative tool time."""
        self.tool_cumulative_seconds[tool_name] = (
            self.tool_cumulative_seconds.get(tool_name, 0.0) + duration_s
        )
        if ok:
            self.consecutive_tool_failures[tool_name] = 0
        else:
            self.consecutive_tool_failures[tool_name] = (
                self.consecutive_tool_failures.get(tool_name, 0) + 1
            )

    def sleep_if_allowed(self, seconds: float) -> bool:
        """Sleep up to seconds if deadline permits; return False if not."""
        if seconds <= 0:
            return True
        if not self.has_budget(seconds):
            self.aborted_reason = "run_timeout_s exceeded during backoff sleep"
            return False
        time.sleep(seconds)
        return True
