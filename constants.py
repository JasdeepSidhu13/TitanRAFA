"""Load loop bounds and policy configuration from config/tool_policy.yaml.

Responsibility:
    Single source of truth for runtime limits referenced by DESIGN.md §5b
    and the orchestrator. Values are read from YAML at import/startup, not
    hardcoded in tool or agent modules.

Role in architecture:
    Bridging layer between auditable config files and Python control flow.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

POLICY_PATH = Path(__file__).resolve().parent / "config" / "tool_policy.yaml"
TRACE_SCHEMA_VERSION = "1"


@dataclass(frozen=True)
class LoopBounds:
    """Runtime loop and deadline caps for a single agent run.

    Description:
        Mirrors ``loop_bounds`` in config/tool_policy.yaml. ``max_planner_cycles``
        is the total number of ``plan`` events permitted across all refine rounds.
        ``max_refine_rounds`` is the highest permitted ``refine_round`` index
        (0-indexed).

    Input:
        N/A — constructed by ``load_loop_bounds``.

    Output:
        Immutable bounds object consumed by the orchestrator.

    When to use:
        At run start and before each planner/refine iteration.

    When not to use:
        Do not instantiate manually with ad-hoc values; always load from YAML
        so traces remain attributable to policy file hash.
    """

    max_refine_rounds: int
    max_planner_cycles: int
    max_tool_calls_per_run: int
    run_timeout_s: int
    circuit_breaker_consecutive_failures: int
    per_tool_cumulative_time_cap_s: int


@dataclass(frozen=True)
class GroqPolicy:
    """Retry and mass-429 policy for Groq LLM calls."""

    timeout_s: float
    max_retries: int
    backoff_base_s: float
    max_output_repair_attempts: int
    mass_429_threshold: int
    honor_retry_after_header: bool


def load_policy() -> dict[str, Any]:
    """Load the full tool policy YAML as a dictionary.

    Description:
        Reads config/tool_policy.yaml from the repository root.

    Input:
        None.

    Output:
        Parsed YAML mapping.

    When to use:
        Tool init, constants loading, policy hash computation.

    When not to use:
        Do not call per tool invocation; load once per process/run.
    """
    with POLICY_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_loop_bounds() -> LoopBounds:
    """Load loop bound constants from config/tool_policy.yaml.

    Description:
        Extracts the ``loop_bounds`` section into a typed dataclass.

    Input:
        None.

    Output:
        ``LoopBounds`` instance.

    When to use:
        Orchestrator initialization.

    When not to use:
        N/A.
    """
    raw = load_policy()["loop_bounds"]
    return LoopBounds(
        max_refine_rounds=int(raw["max_refine_rounds"]),
        max_planner_cycles=int(raw["max_planner_cycles"]),
        max_tool_calls_per_run=int(raw["max_tool_calls_per_run"]),
        run_timeout_s=int(raw["run_timeout_s"]),
        circuit_breaker_consecutive_failures=int(
            raw["circuit_breaker_consecutive_failures"]
        ),
        per_tool_cumulative_time_cap_s=int(raw["per_tool_cumulative_time_cap_s"]),
    )


def load_groq_policy() -> GroqPolicy:
    """Load Groq LLM retry and mass-429 policy.

    Description:
        Extracts the ``groq`` section including ``mass_429_threshold`` for
        degraded termination per DESIGN.md §7.

    Input:
        None.

    Output:
        ``GroqPolicy`` instance.

    When to use:
        LLM client initialization.

    When not to use:
        N/A.
    """
    raw = load_policy()["groq"]
    return GroqPolicy(
        timeout_s=float(raw["timeout_s"]),
        max_retries=int(raw["max_retries"]),
        backoff_base_s=float(raw["backoff_base_s"]),
        max_output_repair_attempts=int(raw["max_output_repair_attempts"]),
        mass_429_threshold=int(raw.get("mass_429_threshold", 3)),
        honor_retry_after_header=bool(raw.get("honor_retry_after_header", True)),
    )
