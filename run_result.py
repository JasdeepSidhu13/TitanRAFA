"""Extract human-readable run output from AgentState and trace JSONL."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

from agentstate import (
    AgentState,
    AnswerabilityEvent,
    RunCompleteEvent,
    SynthesizeEvent,
    ToolResultEvent,
)


@dataclass
class Citation:
    """Citation derived from tool_result evidence."""

    source_id: str
    title: str
    url_or_id: str


@dataclass
class RunResult:
    """Structured outcome of a single agent run for CLI and batch output."""

    question: str
    question_ref: str
    question_type: str
    answer: str
    citations: list[Citation] = field(default_factory=list)
    mode_final: str = "caveated"
    outcome_final: str = "aborted"
    refusal_reason: Optional[str] = None
    evidence_fingerprint: Optional[dict[str, Any]] = None
    trace_path: str = ""
    variant: str = "refine"
    experiment_id: Optional[str] = None


def _tool_results_by_source(state: AgentState) -> dict[str, ToolResultEvent]:
    mapping: dict[str, ToolResultEvent] = {}
    for ev in state.events:
        if isinstance(ev, ToolResultEvent) and ev.ok and ev.source_id:
            mapping[ev.source_id] = ev
    return mapping


def _title_from_source_id(source_id: str) -> str:
    if ":" in source_id:
        return source_id.split(":", 1)[1].replace("_", " ")
    return source_id


def _url_from_source_id(source_id: str) -> str:
    if source_id.startswith("wikipedia:"):
        page = source_id.split(":", 1)[1]
        return f"https://en.wikipedia.org/wiki/{quote(page)}"
    if source_id.startswith("arxiv:"):
        arxiv_id = source_id.split(":", 1)[1]
        return f"https://arxiv.org/abs/{arxiv_id}"
    return source_id


def _citations_from_claims(
    claims: list[dict[str, Any]], tools_by_source: dict[str, ToolResultEvent]
) -> list[Citation]:
    seen: set[str] = set()
    citations: list[Citation] = []
    for claim in claims:
        source_id = claim.get("source_id")
        if not isinstance(source_id, str) or not source_id or source_id in seen:
            continue
        seen.add(source_id)
        tr = tools_by_source.get(source_id)
        title = _title_from_source_id(source_id)
        url = _url_from_source_id(source_id)
        if tr and tr.content_full:
            title_match = None
            if tr.tool_name == "arxiv":
                for line in tr.content_full.splitlines():
                    if line.startswith("Title:"):
                        title_match = line[len("Title:") :].strip()
                        break
            if title_match:
                title = title_match
        citations.append(Citation(source_id=source_id, title=title, url_or_id=url))
    return citations


def _answer_from_synthesize(synth: SynthesizeEvent) -> str:
    parts = [c.get("text", "") for c in synth.claims_validated if c.get("text")]
    return " ".join(parts).strip()


def _read_run_complete(trace_path: str) -> Optional[dict[str, Any]]:
    try:
        with open(trace_path, encoding="utf-8") as fh:
            lines = [ln for ln in fh if ln.strip()]
        if not lines:
            return None
        return json.loads(lines[-1])
    except (OSError, json.JSONDecodeError):
        return None


def extract_run_result(state: AgentState) -> RunResult:
    """Build RunResult from in-memory events and terminal trace line."""
    synth: Optional[SynthesizeEvent] = None
    answerability: Optional[AnswerabilityEvent] = None
    for ev in state.events:
        if isinstance(ev, SynthesizeEvent):
            synth = ev
        elif isinstance(ev, AnswerabilityEvent):
            answerability = ev

    complete_raw = _read_run_complete(str(state.trace_path)) or {}
    mode_final = complete_raw.get("mode_final", "caveated")
    outcome_final = complete_raw.get("outcome_final", "aborted")
    refusal_reason = complete_raw.get("refusal_reason")
    evidence_fingerprint = complete_raw.get("evidence_fingerprint")

    tools_by_source = _tool_results_by_source(state)
    if synth is not None:
        answer = _answer_from_synthesize(synth)
        citations = _citations_from_claims(synth.claims_validated, tools_by_source)
    elif mode_final == "refused" and refusal_reason:
        answer = refusal_reason
        citations = []
    elif answerability and not answerability.in_scope:
        answer = answerability.reason
        citations = []
    else:
        answer = "No synthesized answer available for this run."
        citations = []

    return RunResult(
        question=state.question,
        question_ref=state.question_ref,
        question_type=state.question_type,
        answer=answer,
        citations=citations,
        mode_final=mode_final,
        outcome_final=outcome_final,
        refusal_reason=refusal_reason,
        evidence_fingerprint=evidence_fingerprint,
        trace_path=str(state.trace_path),
        variant=state.variant,
        experiment_id=state.experiment_id,
    )


def format_cli_output(result: RunResult) -> str:
    """Format run result for stdout."""
    lines = [
        f"Answer: {result.answer}",
        "Citations:",
    ]
    if result.citations:
        for c in result.citations:
            lines.append(f"  - [{c.source_id}] {c.title} — {c.url_or_id}")
    else:
        lines.append("  (none)")
    lines.extend(
        [
            f"mode_final: {result.mode_final}",
            f"outcome_final: {result.outcome_final}",
            f"Trace: {result.trace_path}",
        ]
    )
    return "\n".join(lines)


def format_tier1_section(result: RunResult) -> str:
    """Format one question section for outputs/tier1_results.md."""
    ref = result.question_ref or "?"
    header = f"## {ref} — `{result.question_type}`"
    fp = result.evidence_fingerprint or {"source_ids": [], "tools_used": []}
    citation_lines = (
        "\n".join(f"- `{c.source_id}` — {c.title}" for c in result.citations)
        or "- (none)"
    )
    return "\n".join(
        [
            header,
            "",
            f"**Question:** {result.question}",
            "",
            f"**mode_final:** `{result.mode_final}`  ",
            f"**outcome_final:** `{result.outcome_final}`",
            "",
            "**evidence_fingerprint:**",
            f"- source_ids: `{fp.get('source_ids', [])}`",
            f"- tools_used: `{fp.get('tools_used', [])}`",
            "",
            "**Answer:**",
            "",
            result.answer,
            "",
            "**Citations:**",
            "",
            citation_lines,
            "",
            f"**Trace:** `{result.trace_path}`",
            "",
        ]
    )


def read_event_sequence(trace_path: str) -> str:
    """Return compact event_id:kind sequence from a trace JSONL file."""
    try:
        lines = Path(trace_path).read_text(encoding="utf-8").strip().splitlines()
    except OSError:
        return ""
    parts: list[str] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        event_id = ev.get("event_id")
        kind = ev.get("kind")
        if event_id is not None and kind:
            parts.append(f"{event_id}:{kind}")
    return " → ".join(parts)


def format_tier2_variant_section(
    result: RunResult,
    *,
    groq_calls: int,
    event_sequence: str,
) -> str:
    """Format one Tier 2 variant block for outputs/tier2_comparison.md."""
    fp = result.evidence_fingerprint or {"source_ids": [], "tools_used": []}
    return "\n".join(
        [
            f"### variant: `{result.variant}`",
            "",
            f"**mode_final:** `{result.mode_final}`  ",
            f"**outcome_final:** `{result.outcome_final}`",
            "",
            "**evidence_fingerprint:**",
            f"- source_ids: `{fp.get('source_ids', [])}`",
            f"- tools_used: `{fp.get('tools_used', [])}`",
            "",
            f"**Trace:** `{result.trace_path}`",
            "",
            f"**Event sequence:** `{event_sequence}`",
            "",
            f"**Groq complete() calls:** `{groq_calls}`",
            "",
        ]
    )


def format_tier2_question_section(
    question_ref: str,
    question_type: str,
    question: str,
    variant_sections: list[str],
) -> str:
    """Format Q4/Q6 comparison group with both variant blocks."""
    blocks = [
        f"## {question_ref} — `{question_type}`",
        "",
        f"**Question:** {question}",
        "",
    ]
    blocks.extend(variant_sections)
    return "\n".join(blocks)
