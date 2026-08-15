"""Rule-based planner and synthesizer for OFFLINE_MODE (no Groq)."""

from __future__ import annotations

import re
from typing import Any

from agentstate import PlanEvent


def _extract_topic(question: str) -> str:
    q = question.strip()
    for prefix in (
        "What is ",
        "What are ",
        "Who is ",
        "Who was ",
        "Define ",
        "Explain ",
    ):
        if q.lower().startswith(prefix.lower()):
            q = q[len(prefix) :]
    q = re.sub(r"\?$", "", q).strip()
    return q or question


def offline_plan(
    *,
    question: str,
    question_type: str,
    refine_round: int,
    prior_tool_results: list[ToolResultEvent],
) -> PlanEvent:
    """Emit a deterministic plan for fixture replay."""
    topic = _extract_topic(question)
    qtype = question_type or "single_source_factual"
    tool_calls: list[dict[str, str]] = []

    used_tools = {tr.tool_name for tr in prior_tool_results if tr.ok}

    if qtype == "multi_source_synthesis" and refine_round == 0:
        tool_calls = [
            {"tool": "wikipedia", "query": topic},
            {"tool": "wikipedia", "query": f"{topic} overview"},
        ]
    elif (
        qtype == "multi_source_synthesis"
        and refine_round >= 1
        and "arxiv" not in used_tools
    ):
        tool_calls = [{"tool": "arxiv", "query": topic}]
    elif qtype == "data_retrieval":
        tool_calls = [{"tool": "fred", "query": topic}]
    elif "arxiv" in question.lower() or "paper" in question.lower():
        tool_calls = [{"tool": "arxiv", "query": topic}]
    else:
        tool_calls = [{"tool": "wikipedia", "query": topic}]

    return PlanEvent(
        refine_round=refine_round,
        tool_calls_proposed=tool_calls,
        tool_calls_after_validation=tool_calls,
        planner_input_summary=[],
        validation_errors=[],
        repair_count=0,
        model_id="offline-fixture",
    )
