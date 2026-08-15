#!/usr/bin/env python3
"""Research agent CLI entry point.

Responsibility:
    Orchestrates a single question run: run_header → loop → run_complete.
    Supports OFFLINE_MODE / --offline for inspectable traces without API keys.

Role in architecture:
    Orchestrator per config/DESIGN.md §4. Plain Python control flow around
    AgentState — planner and synthesizer are separate LLM calls (stubbed here).
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from typing import Optional

from agentstate import (
    AgentState,
    AnswerabilityEvent,
    PlanEvent,
    RunConfig,
    SufficiencyEvent,
    SynthesizeEvent,
    ToolResultEvent,
)
from constants import load_loop_bounds
from constants import load_policy
from fixtures.loader import (
    is_offline_mode,
    load_planner_fixture,
    load_synthesizer_fixture,
    set_offline_mode,
)
from checks import (
    answerability_check,
    is_duplicate_call,
    make_dedup_skip_event,
    sufficiency_check,
    sufficiency_to_event,
)
from tools import ArxivTool, WikipediaTool
from tools.base import Tool


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


def _execute_tool_calls(state: AgentState, plan: PlanEvent) -> None:
    """Execute planned tool calls with dedup_skip logging for blocked calls."""
    tool_classes = {"wikipedia": WikipediaTool, "arxiv": ArxivTool}
    for call in plan.tool_calls_after_validation:
        tool_name = call["tool"]
        query = call["query"]
        if is_duplicate_call(state, tool_name, query):
            state.append_event(
                make_dedup_skip_event(state, tool_name, query, plan.event_id)
            )
            continue
        tool_cls = tool_classes.get(tool_name)
        if tool_cls is None:
            continue
        result = tool_cls().invoke(query)
        state.append_event(
            ToolResultEvent(
                refine_round=state.refine_round,
                caused_by=plan.event_id,
                tool_name=result.tool_name,
                query=result.query,
                normalized_query=result.normalized_query,
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


def _run_offline(state: AgentState) -> None:
    """Execute a minimal offline happy-path producing a full JSONL trace.

    Description:
        Replays fixture planner/tool/synthesizer responses. Sufficient for
        Tier 1 offline inspectability before live tools are wired.

    Input:
        state: Initialized AgentState with run_header already written.

    Output:
        None; writes events and run_complete to trace file.

    When to use:
        OFFLINE_MODE=1 or --offline.

    When not to use:
        Live runs with real API keys and tools.
    """
    bounds = load_loop_bounds()

    answer = _append_answerability(state)
    if not answer.in_scope:
        state.write_run_complete(
            mode_final="refused",
            outcome_final="out_of_scope",
            refusal_reason=answer.reason,
        )
        return

    planner = load_planner_fixture()
    plan = PlanEvent(
        refine_round=0,
        caused_by=answer.event_id,
        tool_calls_proposed=planner["tool_calls_proposed"],
        tool_calls_after_validation=planner["tool_calls_after_validation"],
        planner_input_summary=[],
        validation_errors=planner["validation_errors"],
        repair_count=planner["repair_count"],
        model_id=planner["model_id"],
    )
    state.append_event(plan)

    if state.plan_event_count > bounds.max_planner_cycles:
        state.write_run_complete("caveated", "aborted", refusal_reason=None)
        return

    _execute_tool_calls(state, plan)
    suff = _append_sufficiency(state, plan)

    synth_fixture = load_synthesizer_fixture()
    synth = SynthesizeEvent(
        refine_round=0,
        caused_by=suff.event_id,
        mode_model=synth_fixture["mode_model"],
        mode_enforced=synth_fixture["mode_enforced"],
        claims_raw=synth_fixture["claims_raw"],
        claims_validated=synth_fixture["claims_validated"],
        context_event_ids=synth_fixture["context_event_ids"],
        chars_fed=synth_fixture["chars_fed"],
        model_id=synth_fixture["model_id"],
    )
    state.append_event(synth)

    state.write_run_complete(
        mode_final=synth.mode_enforced,
        outcome_final="completed",
        refusal_reason=None,
    )


def _run_live_stub(state: AgentState) -> None:
    """Placeholder live path — full orchestrator wired in subsequent milestones.

    Description:
        Writes answerability + error stub and completes as aborted until
        planner/tools/synthesizer are implemented.

    Input:
        state: AgentState with run_header written.

    Output:
        None.

    When to use:
        Live mode after GROQ_API_KEY validation.

    When not to use:
        Offline fixture runs.
    """
    answer = _append_answerability(state)

    if not answer.in_scope:
        state.write_run_complete(
            mode_final="refused",
            outcome_final="out_of_scope",
            refusal_reason=answer.reason,
        )
        return

    state.write_run_complete(
        mode_final="caveated",
        outcome_final="aborted",
        refusal_reason=None,
    )


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entry: parse args, run agent, print trace path.

    Description:
        Accepts a question string and optional metadata flags. Writes trace
        JSONL and prints its path on stdout.

    Input:
        argv: Command-line arguments (defaults to sys.argv).

    Output:
        Process exit code (0 on success).

    When to use:
        ``python agent.py "question"`` or batch runner subprocess.

    When not to use:
        N/A.
    """
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

    if offline:
        _run_offline(state)
    else:
        _run_live_stub(state)

    print(f"Trace written to: {state.trace_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
