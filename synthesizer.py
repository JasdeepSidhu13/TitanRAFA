"""Synthesizer LLM call with claim validation and mode enforcement."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Optional

from agentstate import AgentState, SufficiencyEvent, SynthesizeEvent, ToolResultEvent
from constants import GroqPolicy, load_groq_policy
from groq_client import GroqClient, parse_json_content
from offline_planner import offline_synthesize
from run_context import RunContext

SYNTH_CHAR_BUDGET = 6000


@dataclass
class SynthesizerOutcome:
    """Result of a synthesizer invocation."""

    event: Optional[SynthesizeEvent]
    degraded_reason: Optional[str] = None
    retry_exhausted_reason: Optional[str] = None


def _relevant_tool_results(
    state: AgentState, suff: Optional[SufficiencyEvent]
) -> list[ToolResultEvent]:
    if suff and suff.matched_event_ids:
        ids = set(suff.matched_event_ids)
        return [
            e
            for e in state.events
            if isinstance(e, ToolResultEvent) and e.event_id in ids
        ]
    return [e for e in state.events if isinstance(e, ToolResultEvent) and e.ok]


def _build_context(tool_results: list[ToolResultEvent]) -> tuple[str, list[int], int]:
    parts: list[str] = []
    ids: list[int] = []
    chars = 0
    for tr in tool_results:
        body = tr.content_full or tr.content_for_synthesis
        if not body:
            continue
        remaining = SYNTH_CHAR_BUDGET - chars
        if remaining <= 0:
            break
        snippet = body[:remaining]
        parts.append(f"[{tr.source_id}]\n{snippet}")
        ids.append(tr.event_id)
        chars += len(snippet)
    return "\n\n".join(parts), ids, chars


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
        if not inference:
            if not isinstance(source_id, str) or source_id not in valid_source_ids:
                errors.append(
                    f"claims[{idx}].source_id must reference a tool_result source_id"
                )
                continue
        validated.append(
            {
                "text": text.strip(),
                "source_id": source_id if isinstance(source_id, str) else None,
                "inference": inference,
            }
        )
    return validated, errors


def _enforce_mode(
    claims: list[dict[str, Any]], mode_model: str, speculative: bool
) -> str:
    if any(c.get("inference") for c in claims):
        return "caveated"
    if speculative and claims:
        claims[0] = dict(claims[0])
        claims[0]["inference"] = True
        return "caveated"
    if mode_model in {"grounded", "caveated", "refused"}:
        return mode_model
    return "caveated"


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
    """Produce a synthesize event or signal Groq degradation."""
    policy = policy or load_groq_policy()
    model_id = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")
    tool_results = _relevant_tool_results(state, suff)

    if offline:
        event = offline_synthesize(
            state_tool_results=tool_results,
            sufficiency_passed=sufficiency_passed,
            speculative=state.speculative,
            caused_by=caused_by,
            refine_round=state.refine_round,
        )
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

    context_text, context_ids, chars_fed = _build_context(tool_results)
    valid_source_ids = {
        tr.source_id for tr in tool_results if tr.ok and tr.source_id
    }

    system = (
        "You are a research synthesizer. Respond with JSON only: "
        '{"mode":"grounded|caveated","claims":[{"text":"...","source_id":"...","inference":false}],'
        '"citations":[{"source_id":"...","title":"...","url_or_id":"..."}]}. '
        "Every non-inference claim must cite a source_id from the evidence."
    )
    user = f"Question: {state.question}\n\nEvidence:\n{context_text or '(none)'}"
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    client = groq or GroqClient(policy)
    validation_errors: list[str] = []
    repair_count = 0
    claims_raw: list[dict[str, Any]] = []
    claims_validated: list[dict[str, Any]] = []
    mode_model = "caveated"

    for attempt in range(policy.max_output_repair_attempts + 1):
        if not ctx.has_budget(policy.timeout_s):
            ctx.aborted_reason = "run_timeout_s exceeded during synthesizer repair"
            return SynthesizerOutcome(
                event=None, retry_exhausted_reason=ctx.aborted_reason
            )

        result = client.chat_json(messages, ctx, model=model_id)
        if ctx.groq_degraded_reason:
            return SynthesizerOutcome(
                event=None, degraded_reason=ctx.groq_degraded_reason
            )
        if result.retry_exhausted:
            return SynthesizerOutcome(
                event=None, retry_exhausted_reason=result.reason
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

        mode_model = str(parsed.get("mode", "caveated"))
        claims_raw = parsed.get("claims", [])
        claims_validated, val_errors = _validate_claims(claims_raw, valid_source_ids)
        validation_errors.extend(val_errors)
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

    if not claims_validated:
        claims_validated = [
            {
                "text": "Insufficient validated evidence to answer.",
                "source_id": None,
                "inference": True,
            }
        ]
        mode_model = "caveated"

    mode_enforced = _enforce_mode(
        claims_validated, mode_model, state.speculative
    )

    event = SynthesizeEvent(
        refine_round=state.refine_round,
        caused_by=caused_by,
        mode_model=mode_model if mode_model in {"grounded", "caveated"} else "caveated",
        mode_enforced=mode_enforced,
        claims_raw=claims_raw or claims_validated,
        claims_validated=claims_validated,
        context_event_ids=context_ids,
        chars_fed=chars_fed,
        model_id=model_id,
    )
    _ = repair_count  # repair_count tracked in planner; synth uses same policy
    _ = validation_errors
    return SynthesizerOutcome(event=event)
