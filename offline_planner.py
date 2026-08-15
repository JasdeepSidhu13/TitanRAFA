"""Rule-based planner and synthesizer for OFFLINE_MODE (no Groq)."""

from __future__ import annotations

import re
from typing import Any

from agentstate import PlanEvent, SynthesizeEvent, ToolResultEvent


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


def offline_synthesize(
    *,
    state_tool_results: list[ToolResultEvent],
    sufficiency_passed: bool,
    speculative: bool,
    caused_by: int,
    refine_round: int,
) -> SynthesizeEvent:
    """Build a citation-backed offline answer from tool results."""
    ok_results = [tr for tr in state_tool_results if tr.ok]
    claims: list[dict[str, Any]] = []
    context_ids: list[int] = []
    chars_fed = 0

    for tr in ok_results:
        context_ids.append(tr.event_id)
        snippet = (tr.content_for_synthesis or tr.content_full)[:500]
        chars_fed += len(snippet)
        claims.append(
            {
                "text": snippet[:300] if snippet else f"Evidence from {tr.source_id}",
                "source_id": tr.source_id,
                "inference": False,
            }
        )

    if speculative and claims:
        claims.append(
            {
                "text": "Forward-looking implications remain uncertain without live data.",
                "source_id": None,
                "inference": True,
            }
        )

    if not ok_results:
        claims = [
            {
                "text": "Insufficient evidence in offline fixtures to answer this question.",
                "source_id": None,
                "inference": True,
            }
        ]
        mode_model = "caveated"
    else:
        mode_model = "grounded" if sufficiency_passed and not speculative else "caveated"

    mode_enforced = mode_model
    if any(c.get("inference") for c in claims):
        mode_enforced = "caveated"

    return SynthesizeEvent(
        refine_round=refine_round,
        caused_by=caused_by,
        mode_model=mode_model,
        mode_enforced=mode_enforced,
        claims_raw=claims,
        claims_validated=claims,
        context_event_ids=context_ids,
        chars_fed=chars_fed,
        model_id="offline-fixture",
    )
