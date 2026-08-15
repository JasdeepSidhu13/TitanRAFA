"""Planner LLM call with schema validation and repair."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Optional

from agentstate import AgentState, PlanEvent, ToolResultEvent
from constants import GroqPolicy, load_groq_policy
from groq_client import GroqClient, parse_json_content
from offline_planner import offline_plan
from run_context import RunContext
from tools.registry import REGISTERED_TOOLS

PLANNER_PROMPT_VERSION = "v1"


@dataclass
class PlannerOutcome:
    """Result of a planner invocation."""

    plan: Optional[PlanEvent]
    degraded_reason: Optional[str] = None
    retry_exhausted_reason: Optional[str] = None


def _summarize_tool_results(events: list[ToolResultEvent]) -> str:
    lines: list[str] = []
    for ev in events:
        status = "ok" if ev.ok else "failed"
        lines.append(f"- {ev.tool_name} ({status}): {ev.query[:80]}")
    return "\n".join(lines) or "(no prior tool results)"


def _validate_tool_calls(raw: Any) -> tuple[list[dict[str, str]], list[str]]:
    errors: list[str] = []
    if not isinstance(raw, list):
        return [], ["tool_calls must be a JSON array"]
    validated: list[dict[str, str]] = []
    for idx, call in enumerate(raw):
        if not isinstance(call, dict):
            errors.append(f"tool_calls[{idx}] must be an object")
            continue
        tool = call.get("tool")
        query = call.get("query")
        if not isinstance(tool, str) or not tool.strip():
            errors.append(f"tool_calls[{idx}].tool must be a non-empty string")
            continue
        if not isinstance(query, str) or not query.strip():
            errors.append(f"tool_calls[{idx}].query must be a non-empty string")
            continue
        validated.append({"tool": tool.strip(), "query": query.strip()})
    return validated, errors


def _planner_messages(
    state: AgentState,
    prior_tool_results: list[ToolResultEvent],
    sufficiency_reason: Optional[str],
) -> list[dict[str, str]]:
    tools = ", ".join(sorted(REGISTERED_TOOLS))
    system = (
        "You are a research planner. Respond with JSON only: "
        '{"tool_calls":[{"tool":"wikipedia|arxiv","query":"..."}],"reasoning":"..."}. '
        f"Registered tools: {tools}. Propose at most 2 tool calls. "
        "arXiv must not run in parallel with other tools."
    )
    user_parts = [
        f"Question: {state.question}",
        f"question_type: {state.question_type or 'unknown'}",
        f"refine_round: {state.refine_round}",
        f"Prior tool results:\n{_summarize_tool_results(prior_tool_results)}",
    ]
    if sufficiency_reason:
        user_parts.append(f"Prior sufficiency failure: {sufficiency_reason}")
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "\n".join(user_parts)},
    ]


def run_planner(
    state: AgentState,
    ctx: RunContext,
    *,
    offline: bool,
    caused_by: Optional[int],
    prior_tool_results: list[ToolResultEvent],
    sufficiency_reason: Optional[str] = None,
    groq: Optional[GroqClient] = None,
    policy: Optional[GroqPolicy] = None,
) -> PlannerOutcome:
    """Produce a validated plan event or signal Groq degradation."""
    policy = policy or load_groq_policy()
    model_id = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")

    if offline:
        plan = offline_plan(
            question=state.question,
            question_type=state.question_type,
            refine_round=state.refine_round,
            prior_tool_results=prior_tool_results,
        )
        plan.caused_by = caused_by
        return PlannerOutcome(plan=plan)

    if ctx.groq_degraded_reason:
        return PlannerOutcome(plan=None, degraded_reason=ctx.groq_degraded_reason)

    if not ctx.has_budget(policy.timeout_s):
        ctx.aborted_reason = "run_timeout_s exceeded before planner call"
        return PlannerOutcome(plan=None, retry_exhausted_reason=ctx.aborted_reason)

    client = groq or GroqClient(policy)
    messages = _planner_messages(state, prior_tool_results, sufficiency_reason)
    validation_errors: list[str] = []
    repair_count = 0
    proposed: list[dict[str, str]] = []
    validated: list[dict[str, str]] = []

    for attempt in range(policy.max_output_repair_attempts + 1):
        if not ctx.has_budget(policy.timeout_s):
            ctx.aborted_reason = "run_timeout_s exceeded during planner repair"
            return PlannerOutcome(
                plan=None, retry_exhausted_reason=ctx.aborted_reason
            )

        result = client.chat_json(messages, ctx, model=model_id)
        if ctx.groq_degraded_reason:
            return PlannerOutcome(plan=None, degraded_reason=ctx.groq_degraded_reason)
        if result.retry_exhausted:
            return PlannerOutcome(
                plan=None, retry_exhausted_reason=result.reason
            )
        if not result.ok:
            validation_errors.append(result.reason)
            break

        parsed, parse_err = parse_json_content(result.content)
        if parse_err or parsed is None:
            validation_errors.append(parse_err or "invalid JSON")
            if attempt < policy.max_output_repair_attempts:
                repair_count += 1
                messages.append(
                    {
                        "role": "user",
                        "content": f"Validation error: {parse_err}. Fix JSON.",
                    }
                )
                continue
            break

        proposed, val_errors = _validate_tool_calls(parsed.get("tool_calls", []))
        validation_errors.extend(val_errors)
        validated = [c for c in proposed if c["tool"] in REGISTERED_TOOLS]
        if not val_errors:
            break
        if attempt < policy.max_output_repair_attempts:
            repair_count += 1
            messages.append(
                {
                    "role": "user",
                    "content": "Validation errors: "
                    + "; ".join(val_errors)
                    + ". Return corrected JSON.",
                }
            )
            continue
        break

    if not validated and not validation_errors:
        validation_errors.append("planner returned empty tool_calls after validation")

    plan = PlanEvent(
        refine_round=state.refine_round,
        caused_by=caused_by,
        tool_calls_proposed=proposed,
        tool_calls_after_validation=validated,
        planner_input_summary=[e.event_id for e in prior_tool_results[-5:]],
        validation_errors=validation_errors,
        repair_count=repair_count,
        model_id=model_id,
    )
    return PlannerOutcome(plan=plan)
