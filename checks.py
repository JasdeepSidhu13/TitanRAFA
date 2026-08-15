"""Answerability, sufficiency, and dedup checks per config/DESIGN.md §5a/§5d.

Responsibility:
    Deterministic pre-tool and post-executor gates. No LLM calls in Tier 1
    answerability (rules only). Sufficiency uses question_type as the
    primary diversity signal.

Role in architecture:
    Called by the orchestrator between plan/executor and refine decisions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal, Optional

from agentstate import AgentState, DedupSkipEvent, SufficiencyEvent, ToolResultEvent
from tools.base import Tool
from tools.common import title_overlap_score
from tools.registry import DATA_SOURCE_BY_QUESTION_TYPE, REGISTERED_TOOLS

RULE_VERSION = "sufficiency_v1"

AnswerabilityMethod = Literal["rules", "llm"]

OUT_OF_SCOPE_QUESTION_TYPE = "out_of_scope"
SPECULATIVE_QUESTION_TYPE = "speculative"

DIVERSITY_QUESTION_TYPES = frozenset({"multi_source_synthesis", "cross_tool_synthesis"})

DIVERSITY_KEYWORDS = frozenset(
    {"research", "papers", "academic", "studies", "compare", "differ"}
)

OUT_OF_SCOPE_KEYWORD_RULES: list[tuple[str, str]] = [
    (r"\bbest\b", "keyword:best"),
    (r"\bfavorite\b", "keyword:favorite"),
    (r"\bfavourite\b", "keyword:favourite"),
    (r"\bshould i\b", "keyword:should_i"),
    (r"\brecommend(?:ation)?\b", "keyword:recommend"),
]


@dataclass
class AnswerabilityResult:
    """Outcome of answerability_check for event emission."""

    method: AnswerabilityMethod
    in_scope: bool
    speculative: bool
    matched_rules: list[str]
    reason: str


@dataclass
class SufficiencyResult:
    """Outcome of sufficiency_check for event emission."""

    passed: bool
    reason: str
    matched_event_ids: list[int] = field(default_factory=list)
    rejected_event_ids: list[int] = field(default_factory=list)
    rejected_reasons: dict[str, str] = field(default_factory=dict)
    rule_version: str = RULE_VERSION
    distinct_tools_matched: list[str] = field(default_factory=list)


def answerability_check(question: str, question_type: str) -> AnswerabilityResult:
    """Classify whether a question is answerable before any tool calls.

    Description:
        Rule-based only (method=rules). Uses question_type=out_of_scope as
        primary signal; keyword fallback for subjective preference questions.

    Input:
        question: Natural-language question text.
        question_type: Canonical tag from reference_questions.md.

    Output:
        AnswerabilityResult with in_scope, speculative, matched_rules.

    When to use:
        Immediately after run_header, before first plan event.

    When not to use:
        Do not use for evidence quantity — that is sufficiency_check.
    """
    matched_rules: list[str] = []
    speculative = question_type == SPECULATIVE_QUESTION_TYPE

    if question_type == OUT_OF_SCOPE_QUESTION_TYPE:
        matched_rules.append("question_type:out_of_scope")
        return AnswerabilityResult(
            method="rules",
            in_scope=False,
            speculative=False,
            matched_rules=matched_rules,
            reason="question_type=out_of_scope: subjective or non-citable question",
        )

    lowered = question.lower()
    for pattern, rule_id in OUT_OF_SCOPE_KEYWORD_RULES:
        if re.search(pattern, lowered):
            matched_rules.append(rule_id)

    if matched_rules:
        return AnswerabilityResult(
            method="rules",
            in_scope=False,
            speculative=False,
            matched_rules=matched_rules,
            reason=f"out_of_scope via rules: {', '.join(matched_rules)}",
        )

    if speculative:
        matched_rules.append("question_type:speculative")

    return AnswerabilityResult(
        method="rules",
        in_scope=True,
        speculative=speculative,
        matched_rules=matched_rules or ["question_type:in_scope"],
        reason="in_scope: factual/academic/data question answerable by tools",
    )


def _tool_result_events(state: AgentState) -> list[ToolResultEvent]:
    return [e for e in state.events if isinstance(e, ToolResultEvent)]


def _wikipedia_relevant(question: str, event: ToolResultEvent) -> bool:
    title = ""
    if event.source_id and event.source_id.startswith("wikipedia:"):
        title = event.source_id.split(":", 1)[1].replace("_", " ")
    overlap_title = title_overlap_score(question, title) if title else 0
    overlap_content = title_overlap_score(question, event.content_full[:500])
    return overlap_title >= 1 or overlap_content >= 1


def _arxiv_relevant(question: str, event: ToolResultEvent) -> bool:
    content = event.content_full
    title_match = re.search(r"^Title:\s*(.+)$", content, re.MULTILINE)
    abstract_match = re.search(r"^Abstract:\s*(.+)$", content, re.MULTILINE | re.DOTALL)
    title = title_match.group(1).strip() if title_match else ""
    abstract = abstract_match.group(1).strip() if abstract_match else content
    return title_overlap_score(question, title) >= 1 or title_overlap_score(question, abstract) >= 1


def _tool_relevant(question: str, event: ToolResultEvent) -> tuple[bool, str]:
    if not event.ok:
        return False, "ok=False tool failure"
    if event.tool_name == "wikipedia":
        if _wikipedia_relevant(question, event):
            return True, "wikipedia relevance passed"
        return False, "wikipedia: insufficient title/summary keyword overlap"
    if event.tool_name == "arxiv":
        if _arxiv_relevant(question, event):
            return True, "arxiv relevance passed"
        return False, "arxiv: insufficient title/abstract keyword overlap"
    if event.tool_name == "fred":
        return True, "fred data source result"
    return False, f"unknown tool {event.tool_name}"


def _diversity_gate_applies(question: str, question_type: str) -> tuple[bool, str]:
    if question_type in DIVERSITY_QUESTION_TYPES:
        return True, f"question_type={question_type}"
    if question_type:
        return False, ""
    q_lower = question.lower()
    hits = [kw for kw in DIVERSITY_KEYWORDS if kw in q_lower]
    if hits:
        return True, f"keyword_fallback:{','.join(hits)}"
    return False, ""


def sufficiency_check(
    state: AgentState,
    question: str,
    question_type: str,
    plan_event_id: int,
) -> SufficiencyResult:
    """Evaluate whether collected evidence is sufficient to proceed.

    Description:
        Implements DESIGN.md §5a: per-tool relevance, data_retrieval source
        requirement, and question_type-primary diversity gate.

    Input:
        state: Current AgentState with tool_result events.
        question: Run question text.
        question_type: Canonical question type tag.
        plan_event_id: plan event that triggered this check (caused_by).

    Output:
        SufficiencyResult with matched/rejected event ids and explicit reason.

    When to use:
        After executor appends tool_result events for a plan cycle.

    When not to use:
        Before any tool calls — use answerability_check instead.
    """
    _ = plan_event_id  # caused_by set on event by caller
    matched_ids: list[int] = []
    rejected_ids: list[int] = []
    rejected_reasons: dict[str, str] = {}

    candidates = [e for e in _tool_result_events(state) if e.ok]
    if not candidates:
        return SufficiencyResult(
            passed=False,
            reason="no ok=True tool_result events",
            rejected_event_ids=[],
            rejected_reasons={},
        )

    data_sources = DATA_SOURCE_BY_QUESTION_TYPE.get(question_type, [])
    deciding_factor = ""

    if question_type == "data_retrieval":
        for event in candidates:
            if event.tool_name in data_sources:
                rel, rel_reason = _tool_relevant(question, event)
                if rel:
                    matched_ids.append(event.event_id)
                else:
                    rejected_ids.append(event.event_id)
                    rejected_reasons[str(event.event_id)] = rel_reason
            else:
                rejected_ids.append(event.event_id)
                rejected_reasons[str(event.event_id)] = (
                    "data_retrieval: generic wikipedia/arxiv cannot substitute for fred"
                )
        if not matched_ids:
            if "fred" not in REGISTERED_TOOLS:
                deciding_factor = "data_retrieval"
                return SufficiencyResult(
                    passed=False,
                    reason=(
                        "data_retrieval rule: deciding factor — fred not registered "
                        "(pre-Tier-3); no ok=True fred tool_result"
                    ),
                    matched_event_ids=[],
                    rejected_event_ids=rejected_ids,
                    rejected_reasons=rejected_reasons,
                    distinct_tools_matched=[],
                )
            deciding_factor = "data_retrieval"
            return SufficiencyResult(
                passed=False,
                reason="data_retrieval rule: deciding factor — no ok=True fred tool_result",
                matched_event_ids=matched_ids,
                rejected_event_ids=rejected_ids,
                rejected_reasons=rejected_reasons,
                distinct_tools_matched=[],
            )
        distinct = sorted({e.tool_name for e in candidates if e.event_id in matched_ids})
        return SufficiencyResult(
            passed=True,
            reason="data_retrieval rule satisfied: ok=True fred tool_result present",
            matched_event_ids=matched_ids,
            rejected_event_ids=rejected_ids,
            rejected_reasons=rejected_reasons,
            distinct_tools_matched=distinct,
        )

    for event in candidates:
        rel, rel_reason = _tool_relevant(question, event)
        if rel:
            matched_ids.append(event.event_id)
        else:
            rejected_ids.append(event.event_id)
            rejected_reasons[str(event.event_id)] = rel_reason

    if not matched_ids:
        return SufficiencyResult(
            passed=False,
            reason="no relevant ok=True tool_result after per-tool rules",
            matched_event_ids=[],
            rejected_event_ids=rejected_ids,
            rejected_reasons=rejected_reasons,
            distinct_tools_matched=[],
        )

    matched_events = [e for e in candidates if e.event_id in matched_ids]
    distinct_tools = sorted({e.tool_name for e in matched_events})

    diversity_applies, diversity_trigger = _diversity_gate_applies(question, question_type)
    if diversity_applies:
        if len(distinct_tools) < 2:
            deciding_factor = "diversity_gate"
            return SufficiencyResult(
                passed=False,
                reason=(
                    f"diversity_gate deciding factor ({diversity_trigger}): "
                    f"requires >=2 distinct tools among matched evidence; "
                    f"got {len(distinct_tools)} ({', '.join(distinct_tools) or 'none'}) "
                    f"from {len(matched_ids)} matched tool_result event(s)"
                ),
                matched_event_ids=matched_ids,
                rejected_event_ids=rejected_ids,
                rejected_reasons=rejected_reasons,
                distinct_tools_matched=distinct_tools,
            )
        return SufficiencyResult(
            passed=True,
            reason=(
                f"diversity_gate satisfied ({diversity_trigger}): "
                f"{len(distinct_tools)} distinct tools among matched evidence "
                f"({', '.join(distinct_tools)})"
            ),
            matched_event_ids=matched_ids,
            rejected_event_ids=rejected_ids,
            rejected_reasons=rejected_reasons,
            distinct_tools_matched=distinct_tools,
        )

    return SufficiencyResult(
        passed=True,
        reason=(
            f"relevance satisfied: {len(matched_ids)} matched event(s), "
            f"distinct tools={', '.join(distinct_tools)}"
        ),
        matched_event_ids=matched_ids,
        rejected_event_ids=rejected_ids,
        rejected_reasons=rejected_reasons,
        distinct_tools_matched=distinct_tools,
    )


def is_duplicate_call(
    state: AgentState,
    tool_name: str,
    query: str,
) -> bool:
    """Return True if (tool_name, normalized_query) was already executed.

    Description:
        Dedup normalization per DESIGN.md §5: lowercase, collapse
        whitespace, strip punctuation.

    Input:
        state: Run state with prior tool_result events.
        tool_name: Proposed tool.
        query: Proposed query string.

    Output:
        True if duplicate should be skipped.

    When to use:
        Before executing each planned tool call.

    When not to use:
        N/A.
    """
    normalized = Tool.normalize_query(query)
    for event in _tool_result_events(state):
        if event.tool_name == tool_name and event.normalized_query == normalized:
            return True
    return False


def make_dedup_skip_event(
    state: AgentState,
    tool_name: str,
    query: str,
    plan_event_id: int,
) -> DedupSkipEvent:
    """Build a dedup_skip event for a blocked tool call.

    Description:
        caused_by must be the plan event that proposed the blocked call.

    Input:
        state: Current run (for refine_round).
        tool_name: Blocked tool name.
        query: Blocked query.
        plan_event_id: Parent plan event_id.

    Output:
        DedupSkipEvent ready for state.append_event.

    When to use:
        When is_duplicate_call returns True.

    When not to use:
        N/A.
    """
    return DedupSkipEvent(
        refine_round=state.refine_round,
        caused_by=plan_event_id,
        tool_name=tool_name,
        query=query,
        normalized_query=Tool.normalize_query(query),
    )


def sufficiency_to_event(
    result: SufficiencyResult,
    state: AgentState,
    plan_event_id: int,
) -> SufficiencyEvent:
    """Convert SufficiencyResult to a SufficiencyEvent for logging."""
    return SufficiencyEvent(
        refine_round=state.refine_round,
        caused_by=plan_event_id,
        passed=result.passed,
        reason=result.reason,
        matched_event_ids=result.matched_event_ids,
        rejected_event_ids=result.rejected_event_ids,
        rejected_reasons=result.rejected_reasons,
        rule_version=result.rule_version,
    )
