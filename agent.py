#!/usr/bin/env python3
"""Research agent CLI entry point.

Responsibility:
    Orchestrates a single question run: run_header → loop → run_complete.
    Supports OFFLINE_MODE / --offline for inspectable traces without API keys.

Role in architecture:
    Orchestrator per config/DESIGN.md §4. Plain Python control flow around
    AgentState — planner and synthesizer are separate LLM calls.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
import time
from typing import Optional

from agentstate import (
    AgentState,
    AnswerabilityEvent,
    ErrorEvent,
    PlanEvent,
    RunConfig,
    SufficiencyEvent,
    SynthesizeEvent,
    ToolResultEvent,
)
from checks import (
    answerability_check,
    is_duplicate_call,
    make_dedup_skip_event,
    sufficiency_check,
    sufficiency_to_event,
)
from constants import load_groq_policy, load_loop_bounds
from constants import load_policy
from fixtures.loader import is_offline_mode, set_offline_mode
from planner import run_planner
from run_context import RunContext
from synthesizer import run_synthesizer
from tools import ArxivTool, WikipediaTool
from tools.base import Tool


def _policy_file_hash() -> str:
    raw = open("config/tool_policy.yaml", "rb").read()
    return hashlib.sha256(raw).hexdigest()[:16]


def _require_groq_key(offline: bool) -> None:
    """Fail fast when GROQ_API_KEY missing unless offline mode is active."""
    if offline:
        return
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if not key:
        print(
            "ERROR: GROQ_API_KEY is not set. "
            "Use OFFLINE_MODE=1 or --offline for an inspectable trace without a key.",
            file=sys.stderr,
        )
        sys.exit(1)


def _append_answerability(state: AgentState) -> AnswerabilityEvent:
    """Run answerability_check and append the answerability event."""
    result = answerability_check(state.question, state.question_type)
    event = AnswerabilityEvent(
        refine_round=state.refine_round,
        caused_by=None,
        method=result.method,
        in_scope=result.in_scope,
        speculative=result.speculative,
        matched_rules=result.matched_rules,
        reason=result.reason,
    )
    state.append_event(event)
    return event


def _tool_result_events(state: AgentState) -> list[ToolResultEvent]:
    return [e for e in state.events if isinstance(e, ToolResultEvent)]


def _last_sufficiency(state: AgentState) -> Optional[SufficiencyEvent]:
    for ev in reversed(state.events):
        if isinstance(ev, SufficiencyEvent):
            return ev
    return None


def _execute_tool_calls(
    state: AgentState, plan: PlanEvent, ctx: RunContext
) -> None:
    """Execute planned tool calls sequentially with dedup and caps."""
    tool_instances: dict[str, Tool] = {
        "wikipedia": WikipediaTool(),
        "arxiv": ArxivTool(),
    }
    deadline = ctx.deadline_for_tools()

    for call in plan.tool_calls_after_validation:
        if not ctx.has_budget():
            ctx.aborted_reason = "run_timeout_s exceeded before tool execution"
            return
        if ctx.tool_calls_executed >= ctx.bounds.max_tool_calls_per_run:
            return

        tool_name = call.get("tool", "")
        query = call.get("query", "")

        if is_duplicate_call(state, tool_name, query):
            state.append_event(
                make_dedup_skip_event(state, tool_name, query, plan.event_id)
            )
            continue

        if ctx.circuit_open(tool_name):
            state.append_event(
                ToolResultEvent(
                    refine_round=state.refine_round,
                    caused_by=plan.event_id,
                    tool_name=tool_name,
                    query=query,
                    normalized_query=Tool.normalize_query(query),
                    ok=False,
                    reason=f"circuit breaker open for {tool_name}",
                    failure_class="timeout",
                )
            )
            continue

        if ctx.tool_time_cap_hit(tool_name):
            state.append_event(
                ToolResultEvent(
                    refine_round=state.refine_round,
                    caused_by=plan.event_id,
                    tool_name=tool_name,
                    query=query,
                    normalized_query=Tool.normalize_query(query),
                    ok=False,
                    reason=f"per-tool cumulative time cap hit for {tool_name}",
                    failure_class="timeout",
                )
            )
            continue

        tool = tool_instances.get(tool_name)
        if tool is None:
            state.append_event(
                ToolResultEvent(
                    refine_round=state.refine_round,
                    caused_by=plan.event_id,
                    tool_name=tool_name,
                    query=query,
                    normalized_query=Tool.normalize_query(query),
                    ok=False,
                    reason=f"tool {tool_name} not registered",
                    failure_class="empty_result",
                )
            )
            continue

        start = time.monotonic()
        result = tool.invoke(query, deadline=deadline)
        duration_s = time.monotonic() - start
        ctx.tool_calls_executed += 1
        ctx.record_tool_result(tool_name, result.ok, duration_s)

        state.append_event(
            ToolResultEvent(
                refine_round=state.refine_round,
                caused_by=plan.event_id,
                tool_name=result.tool_name,
                query=result.query or query,
                normalized_query=result.normalized_query
                or Tool.normalize_query(query),
                ok=result.ok,
                reason=result.reason,
                failure_class=result.failure_class,
                source_id=result.source_id,
                content_full=result.content_full,
                content_for_synthesis=result.content_for_synthesis,
                truncated=result.truncated,
            )
        )


def _append_sufficiency(state: AgentState, plan: PlanEvent) -> SufficiencyEvent:
    """Run sufficiency_check and append the sufficiency event."""
    result = sufficiency_check(
        state, state.question, state.question_type, plan.event_id
    )
    event = sufficiency_to_event(result, state, plan.event_id)
    state.append_event(event)
    return event


def _can_plan(state: AgentState, ctx: RunContext) -> bool:
    if state.plan_event_count >= ctx.bounds.max_planner_cycles:
        return False
    return ctx.has_budget()


def _can_refine(state: AgentState, ctx: RunContext) -> bool:
    if state.refine_disabled:
        return False
    return state.refine_round < ctx.bounds.max_refine_rounds


def _write_degraded_complete(
    state: AgentState, reason: str, *, groq_retry_exhausted: bool = False
) -> None:
    """Terminate with outcome_final=degraded per DESIGN.md §7."""
    mode = AgentState.resolve_degraded_mode(state)
    refusal: Optional[str] = None
    if mode == "refused":
        refusal = reason
    state.append_event(
        ErrorEvent(
            refine_round=state.refine_round,
            error_type="groq_degraded" if not groq_retry_exhausted else "groq_retry_exhausted",
            message=reason,
        )
    )
    state.write_run_complete(
        mode_final=mode,
        outcome_final="degraded",
        refusal_reason=refusal,
    )


def _write_insufficient_complete(
    state: AgentState,
    synth: Optional[SynthesizeEvent],
) -> None:
    mode = synth.mode_enforced if synth else "caveated"
    state.write_run_complete(
        mode_final=mode,
        outcome_final="insufficient_evidence",
        refusal_reason=None,
    )


def _write_completed(state: AgentState, synth: SynthesizeEvent) -> None:
    state.write_run_complete(
        mode_final=synth.mode_enforced,
        outcome_final="completed",
        refusal_reason=None,
    )


def _run_agent(state: AgentState, ctx: RunContext, *, offline: bool) -> None:
    """Full orchestrator loop with guaranteed run_complete on all paths."""
    answer = _append_answerability(state)

    if not answer.in_scope:
        state.write_run_complete(
            mode_final="refused",
            outcome_final="out_of_scope",
            refusal_reason=answer.reason,
        )
        return

    if not ctx.has_budget():
        ctx.aborted_reason = "run_timeout_s exceeded before planning"
        _write_insufficient_complete(state, None)
        return

    plan_caused_by: Optional[int] = None
    sufficiency_reason: Optional[str] = None
    last_suff: Optional[SufficiencyEvent] = None
    last_plan: Optional[PlanEvent] = None
    sufficiency_passed = False

    while True:
        if not _can_plan(state, ctx):
            break

        prior_results = _tool_result_events(state)
        planner_out = run_planner(
            state,
            ctx,
            offline=offline,
            caused_by=plan_caused_by,
            prior_tool_results=prior_results,
            sufficiency_reason=sufficiency_reason,
        )

        if planner_out.degraded_reason:
            _write_degraded_complete(state, planner_out.degraded_reason)
            return
        if planner_out.retry_exhausted_reason:
            _write_degraded_complete(
                state,
                planner_out.retry_exhausted_reason,
                groq_retry_exhausted=True,
            )
            return
        if planner_out.plan is None:
            break

        plan = planner_out.plan
        state.append_event(plan)
        last_plan = plan

        if not ctx.has_budget():
            ctx.aborted_reason = "run_timeout_s exceeded after plan"
            break

        _execute_tool_calls(state, plan, ctx)
        last_suff = _append_sufficiency(state, plan)
        sufficiency_passed = last_suff.passed

        if sufficiency_passed:
            break

        if not _can_refine(state, ctx):
            break

        if not ctx.has_budget():
            ctx.aborted_reason = "run_timeout_s exceeded before refine"
            break

        plan_caused_by = last_suff.event_id
        sufficiency_reason = last_suff.reason
        state.refine_round += 1

    if last_suff is not None:
        synth_caused_by = last_suff.event_id
    elif last_plan is not None:
        synth_caused_by = last_plan.event_id
    else:
        synth_caused_by = answer.event_id

    synth_out = run_synthesizer(
        state,
        ctx,
        offline=offline,
        caused_by=synth_caused_by,
        sufficiency_passed=sufficiency_passed,
        suff=last_suff,
    )

    if synth_out.degraded_reason:
        _write_degraded_complete(state, synth_out.degraded_reason)
        return
    if synth_out.retry_exhausted_reason:
        _write_degraded_complete(
            state,
            synth_out.retry_exhausted_reason,
            groq_retry_exhausted=True,
        )
        return

    synth = synth_out.event
    if synth is None:
        return

    if sufficiency_passed:
        _write_completed(state, synth)
    else:
        _write_insufficient_complete(state, synth)


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entry: parse args, run agent, print trace path."""
    parser = argparse.ArgumentParser(description="Banking research agent")
    parser.add_argument("question", help="Natural-language research question")
    parser.add_argument("--offline", action="store_true", help="Replay offline fixtures")
    parser.add_argument("--question-ref", default="", help="e.g. Q4")
    parser.add_argument("--question-type", default="", help="Canonical question_type tag")
    parser.add_argument(
        "--variant",
        choices=["single_pass", "refine"],
        default="refine",
        help="Tier 2 variant",
    )
    parser.add_argument("--experiment-id", default=None, help="Optional batch experiment id")
    args = parser.parse_args(argv)

    offline = is_offline_mode(args.offline)
    set_offline_mode(offline)
    _require_groq_key(offline)

    refine_disabled = os.environ.get("SINGLE_PASS", "") == "1"
    variant = "single_pass" if refine_disabled else args.variant
    speculative = args.question_type == "speculative"

    _ = load_policy()
    _ = load_groq_policy()
    bounds = load_loop_bounds()
    ctx = RunContext.from_bounds(bounds)

    state = AgentState(
        question=args.question,
        question_ref=args.question_ref,
        question_type=args.question_type,
        variant=variant,
        experiment_id=args.experiment_id,
        refine_disabled=refine_disabled,
        speculative=speculative,
        config=RunConfig(
            model_id=os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant"),
            temperature=0.0,
            policy_file_hash=_policy_file_hash(),
            prompt_version="v1",
        ),
    )

    state.write_run_header()

    try:
        _run_agent(state, ctx, offline=offline)
    except Exception as exc:  # noqa: BLE001 — ensure run_complete on crash
        if not state._complete_written:
            state.append_event(
                ErrorEvent(
                    refine_round=state.refine_round,
                    error_type=type(exc).__name__,
                    message=str(exc),
                )
            )
            state.write_run_complete(
                mode_final="caveated",
                outcome_final="aborted",
                refusal_reason=None,
            )
    finally:
        if not state._complete_written:
            state.write_run_complete(
                mode_final="caveated",
                outcome_final="aborted",
                refusal_reason=None,
            )

    print(f"Trace written to: {state.trace_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
