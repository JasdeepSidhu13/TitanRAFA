"""Synthesizer LLM call with claim validation, mode enforcement, and context budget.

Responsibility:
    Produce a synthesize event with both mode_model and mode_enforced recorded.
    mode_enforced is authoritative for run_complete.mode_final. Validates claims
    against this run's tool_result source_ids; logs dropped_context events when
    the char budget excludes evidence.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Literal, Optional

from agentstate import (
    AgentState,
    DroppedContextEvent,
    SufficiencyEvent,
    SynthesizeEvent,
    ToolResultEvent,
)
from constants import GroqPolicy, load_groq_policy
from groq_client import GroqClient, parse_json_content
from run_context import RunContext
from tools.common import title_overlap_score

SYNTH_CHAR_BUDGET = 6000
ModeFinal = Literal["grounded", "caveated", "refused"]


@dataclass
class DroppedContextItem:
    """Evidence excluded from synthesizer input due to char budget."""

    dropped_event_id: int
    reason: str


@dataclass
class SynthesizerOutcome:
    """Result of a synthesizer invocation (event always appended when not degraded)."""

    event: Optional[SynthesizeEvent]
    degraded_reason: Optional[str] = None
    retry_exhausted_reason: Optional[str] = None


def _tool_results_in_run(state: AgentState) -> list[ToolResultEvent]:
    return [e for e in state.events if isinstance(e, ToolResultEvent)]


def _valid_source_ids(state: AgentState) -> set[str]:
    return {
        e.source_id
        for e in _tool_results_in_run(state)
        if e.ok and e.source_id
    }


def _relevant_tool_results(
    state: AgentState, suff: Optional[SufficiencyEvent]
) -> list[ToolResultEvent]:
    ok_results = [e for e in _tool_results_in_run(state) if e.ok]
    if suff and suff.matched_event_ids:
        ids = set(suff.matched_event_ids)
        matched = [e for e in ok_results if e.event_id in ids]
        if matched:
            return matched
    return ok_results


def _relevance_score(question: str, tr: ToolResultEvent) -> int:
    title = ""
    if tr.source_id and ":" in tr.source_id:
        title = tr.source_id.split(":", 1)[1].replace("_", " ")
    content_head = (tr.content_full or "")[:500]
    title_match = re.search(r"^Title:\s*(.+)$", content_head, re.MULTILINE)
    if title_match:
        title = title_match.group(1).strip()
    return max(
        title_overlap_score(question, title),
        title_overlap_score(question, content_head),
    )


def _select_context(
    question: str, tool_results: list[ToolResultEvent]
) -> tuple[str, list[int], int, list[DroppedContextItem]]:
    """Include whole tool_result events until char budget; drop lowest relevance first."""
    if not tool_results:
        return "", [], 0, []

    ranked = sorted(
        tool_results,
        key=lambda tr: _relevance_score(question, tr),
        reverse=True,
    )
    included: list[ToolResultEvent] = []
    dropped: list[DroppedContextItem] = []
    chars = 0

    for tr in ranked:
        body = tr.content_full or tr.content_for_synthesis or ""
        if not body:
            dropped.append(
                DroppedContextItem(
                    dropped_event_id=tr.event_id,
                    reason="empty content_full; excluded from synthesizer input",
                )
            )
            continue
        if chars + len(body) > SYNTH_CHAR_BUDGET:
            dropped.append(
                DroppedContextItem(
                    dropped_event_id=tr.event_id,
                    reason=(
                        f"char budget ({SYNTH_CHAR_BUDGET}) exceeded; "
                        f"relevance_score={_relevance_score(question, tr)}"
                    ),
                )
            )
            continue
        included.append(tr)
        chars += len(body)

    parts: list[str] = []
    ids: list[int] = []
    for tr in included:
        body = tr.content_full or tr.content_for_synthesis or ""
        parts.append(f"[{tr.source_id}]\n{body}")
        ids.append(tr.event_id)

    return "\n\n".join(parts), ids, chars, dropped


def _validate_claims(
    claims: Any, valid_source_ids: set[str]
) -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    if not isinstance(claims, list):
        return [], ["claims must be a JSON array"]
    validated: list[dict[str, Any]] = []
    for idx, claim in enumerate(claims):
        if not isinstance(claim, dict):
            errors.append(f"claims[{idx}] must be an object")
            continue
        text = claim.get("text")
        if not isinstance(text, str) or not text.strip():
            errors.append(f"claims[{idx}].text required")
            continue
        inference = bool(claim.get("inference", False))
        source_id = claim.get("source_id")
        if inference:
            if source_id is not None and (
                not isinstance(source_id, str) or source_id not in valid_source_ids
            ):
                errors.append(
                    f"claims[{idx}].source_id must be null or a valid tool_result source_id"
                )
                continue
            validated.append(
                {
                    "text": text.strip(),
                    "source_id": source_id if isinstance(source_id, str) else None,
                    "inference": True,
                }
            )
            continue
        if not isinstance(source_id, str) or source_id not in valid_source_ids:
            errors.append(
                f"claims[{idx}].source_id must reference an ok=True tool_result source_id"
            )
            continue
        validated.append(
            {
                "text": text.strip(),
                "source_id": source_id,
                "inference": False,
            }
        )
    return validated, errors


def _ensure_speculative_claim(
    claims: list[dict[str, Any]], question: str
) -> list[dict[str, Any]]:
    """Q8-style: require >=1 inference:true claim when speculative flag is set."""
    if any(c.get("inference") for c in claims):
        return claims
    updated = list(claims)
    updated.append(
        {
            "text": (
                f"Forward-looking implications regarding '{question[:120]}' "
                "remain uncertain and are not fully grounded in retrieved evidence."
            ),
            "source_id": None,
            "inference": True,
        }
    )
    return updated


def _compute_mode_enforced(
    mode_model: str, claims: list[dict[str, Any]]
) -> ModeFinal:
    """Never trust mode_model alone — inference claims always force caveated."""
    if any(c.get("inference") for c in claims):
        return "caveated"
    if mode_model == "grounded":
        return "grounded"
    if mode_model == "refused":
        return "refused"
    return "caveated"


def _templated_fallback(
    *,
    question: str,
    tool_results: list[ToolResultEvent],
    speculative: bool,
    valid_source_ids: set[str],
) -> tuple[list[dict[str, Any]], str, ModeFinal]:
    """Deterministic caveated fallback after validation/repair exhaustion."""
    claims: list[dict[str, Any]] = []
    for tr in tool_results:
        if not tr.ok or not tr.source_id or tr.source_id not in valid_source_ids:
            continue
        snippet = (tr.content_for_synthesis or tr.content_full or "")[:300].strip()
        if snippet:
            claims.append(
                {
                    "text": snippet,
                    "source_id": tr.source_id,
                    "inference": False,
                }
            )

    if not claims:
        claims.append(
            {
                "text": (
                    f"Unable to produce a validated answer for: {question}. "
                    "Retrieved evidence did not pass claim validation."
                ),
                "source_id": None,
                "inference": True,
            }
        )

    if speculative:
        claims = _ensure_speculative_claim(claims, question)

    mode_model = "caveated"
    mode_enforced = _compute_mode_enforced(mode_model, claims)
    return claims, mode_model, mode_enforced


def _append_synthesize_with_drops(
    state: AgentState,
    event: SynthesizeEvent,
    drops: list[DroppedContextItem],
) -> SynthesizeEvent:
    """Append synthesize then dropped_context events (incremental JSONL flush)."""
    state.append_event(event)
    for drop in drops:
        state.append_event(
            DroppedContextEvent(
                refine_round=state.refine_round,
                caused_by=event.event_id,
                dropped_event_id=drop.dropped_event_id,
                reason=drop.reason,
            )
        )
    return event


def _build_synthesize_event(
    *,
    state: AgentState,
    caused_by: int,
    mode_model: str,
    claims_raw: list[dict[str, Any]],
    claims_validated: list[dict[str, Any]],
    context_event_ids: list[int],
    chars_fed: int,
    model_id: str,
) -> SynthesizeEvent:
    if state.speculative:
        claims_validated = _ensure_speculative_claim(claims_validated, state.question)
    mode_enforced = _compute_mode_enforced(mode_model, claims_validated)
    safe_mode_model: ModeFinal = (
        mode_model if mode_model in {"grounded", "caveated", "refused"} else "caveated"
    )
    return SynthesizeEvent(
        refine_round=state.refine_round,
        caused_by=caused_by,
        mode_model=safe_mode_model,
        mode_enforced=mode_enforced,
        claims_raw=claims_raw,
        claims_validated=claims_validated,
        context_event_ids=context_event_ids,
        chars_fed=chars_fed,
        model_id=model_id,
    )


def run_synthesizer(
    state: AgentState,
    ctx: RunContext,
    *,
    offline: bool,
    caused_by: int,
    sufficiency_passed: bool,
    suff: Optional[SufficiencyEvent],
    groq: Optional[GroqClient] = None,
    policy: Optional[GroqPolicy] = None,
) -> SynthesizerOutcome:
    """Produce synthesize (+ dropped_context) events; append incrementally to trace."""
    policy = policy or load_groq_policy()
    model_id = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")
    tool_results = _relevant_tool_results(state, suff)
    valid_ids = _valid_source_ids(state)

    context_text, context_ids, chars_fed, drops = _select_context(
        state.question, tool_results
    )

    if offline:
        event = _offline_synthesize(
            state=state,
            tool_results=tool_results,
            context_ids=context_ids,
            chars_fed=chars_fed,
            caused_by=caused_by,
            sufficiency_passed=sufficiency_passed,
            model_id="offline-fixture",
        )
        _append_synthesize_with_drops(state, event, drops)
        return SynthesizerOutcome(event=event)

    if ctx.groq_degraded_reason:
        return SynthesizerOutcome(
            event=None, degraded_reason=ctx.groq_degraded_reason
        )

    if not ctx.has_budget(policy.timeout_s):
        ctx.aborted_reason = "run_timeout_s exceeded before synthesizer call"
        return SynthesizerOutcome(
            event=None, retry_exhausted_reason=ctx.aborted_reason
        )

    system = (
        "You are a research synthesizer. Respond with JSON only: "
        '{"mode":"grounded|caveated","claims":[{"text":"...","source_id":"...","inference":false}],'
        '"citations":[{"source_id":"...","title":"...","url_or_id":"..."}]}. '
        "Every non-inference claim must cite a source_id from the evidence block. "
        "Use inference:true only for claims not directly supported by evidence."
    )
    if state.speculative:
        system += (
            " This question is speculative: include at least one inference:true claim "
            "for forward-looking implications."
        )

    user = f"Question: {state.question}\n\nEvidence:\n{context_text or '(none)'}"
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    client = groq or GroqClient(policy)
    claims_raw: list[dict[str, Any]] = []
    claims_validated: list[dict[str, Any]] = []
    mode_model = "caveated"
    validation_failed = False

    for attempt in range(policy.max_output_repair_attempts + 1):
        if not ctx.has_budget(policy.timeout_s):
            ctx.aborted_reason = "run_timeout_s exceeded during synthesizer repair"
            return SynthesizerOutcome(
                event=None, retry_exhausted_reason=ctx.aborted_reason
            )

        result = client.complete(messages, ctx, model=model_id)
        if ctx.groq_degraded_reason:
            return SynthesizerOutcome(
                event=None, degraded_reason=ctx.groq_degraded_reason
            )
        if result.retry_exhausted:
            return SynthesizerOutcome(
                event=None, retry_exhausted_reason=result.reason
            )
        if not result.ok:
            validation_failed = True
            break

        parsed, parse_err = parse_json_content(result.content)
        if parse_err or parsed is None:
            if attempt < policy.max_output_repair_attempts:
                messages.append(
                    {
                        "role": "user",
                        "content": f"Validation error: {parse_err}. Fix JSON.",
                    }
                )
                continue
            validation_failed = True
            break

        mode_model = str(parsed.get("mode", "caveated"))
        claims_raw = parsed.get("claims", [])
        claims_validated, val_errors = _validate_claims(claims_raw, valid_ids)
        if not val_errors:
            break
        if attempt < policy.max_output_repair_attempts:
            messages.append(
                {
                    "role": "user",
                    "content": "Validation errors: "
                    + "; ".join(val_errors)
                    + ". Return corrected JSON.",
                }
            )
            continue
        validation_failed = True
        break

    if validation_failed or not claims_validated:
        claims_validated, mode_model, _ = _templated_fallback(
            question=state.question,
            tool_results=tool_results,
            speculative=state.speculative,
            valid_source_ids=valid_ids,
        )
        claims_raw = claims_validated

    event = _build_synthesize_event(
        state=state,
        caused_by=caused_by,
        mode_model=mode_model,
        claims_raw=claims_raw,
        claims_validated=claims_validated,
        context_event_ids=context_ids,
        chars_fed=chars_fed,
        model_id=model_id,
    )
    _append_synthesize_with_drops(state, event, drops)
    return SynthesizerOutcome(event=event)


def _offline_synthesize(
    *,
    state: AgentState,
    tool_results: list[ToolResultEvent],
    context_ids: list[int],
    chars_fed: int,
    caused_by: int,
    sufficiency_passed: bool,
    model_id: str,
) -> SynthesizeEvent:
    """Offline synthesizer using the same validation and mode enforcement rules."""
    valid_ids = {tr.source_id for tr in tool_results if tr.ok and tr.source_id}
    claims: list[dict[str, Any]] = []
    for tr in tool_results:
        if not tr.ok or not tr.source_id:
            continue
        snippet = (tr.content_for_synthesis or tr.content_full or "")[:300]
        claims.append(
            {
                "text": snippet or f"Evidence from {tr.source_id}",
                "source_id": tr.source_id,
                "inference": False,
            }
        )

    claims_validated, val_errors = _validate_claims(claims, valid_ids)
    if val_errors or not claims_validated:
        claims_validated, mode_model, _ = _templated_fallback(
            question=state.question,
            tool_results=tool_results,
            speculative=state.speculative,
            valid_source_ids=valid_ids,
        )
        claims_raw = claims_validated
    else:
        claims_raw = claims
        mode_model = (
            "grounded" if sufficiency_passed and not state.speculative else "caveated"
        )

    return _build_synthesize_event(
        state=state,
        caused_by=caused_by,
        mode_model=mode_model,
        claims_raw=claims_raw,
        claims_validated=claims_validated,
        context_event_ids=context_ids,
        chars_fed=chars_fed,
        model_id=model_id,
    )
