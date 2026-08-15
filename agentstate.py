"""AgentState and frozen trace event schema (trace_schema_version \"1\").

Responsibility:
    Append-only event log for a single agent run, JSONL export with
    run_header as first line and run_complete as terminal line. event_id
    is the only ID namespace — no step_id anywhere.

Role in architecture:
    Memory and trace contract per config/DESIGN.md §5 and §5e.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional

from constants import TRACE_SCHEMA_VERSION

ModeFinal = Literal["grounded", "caveated", "refused"]
OutcomeFinal = Literal[
    "completed",
    "aborted",
    "out_of_scope",
    "insufficient_evidence",
    "degraded",
]
Variant = Literal["single_pass", "refine"]
FailureClass = Literal["timeout", "http_429", "parse_error", "empty_result"]
EventKind = Literal[
    "run_header",
    "run_complete",
    "plan",
    "answerability",
    "dedup_skip",
    "tool_result",
    "sufficiency",
    "synthesize",
    "dropped_context",
    "error",
]


class AgentStateError(Exception):
    """Raised when trace invariants are violated at write time."""


@dataclass
class Timing:
    """Volatile timing metadata excluded from Tier 2 structural diffs."""

    timestamp_ms: int
    duration_ms: int


@dataclass
class RunConfig:
    """Pinned run configuration recorded in run_header."""

    model_id: str
    temperature: float
    policy_file_hash: str
    prompt_version: str


@dataclass
class EvidenceFingerprint:
    """Sorted evidence summary written in run_complete."""

    source_ids: list[str]
    tools_used: list[str]


@dataclass
class RunHeaderEvent:
    """First JSONL line — run metadata without terminal outcome fields."""

    kind: Literal["run_header"] = "run_header"
    event_id: int = 0
    run_id: str = ""
    question: str = ""
    question_ref: str = ""
    question_type: str = ""
    variant: Variant = "refine"
    experiment_id: Optional[str] = None
    refine_disabled: bool = False
    speculative: bool = False
    started_at: str = ""
    trace_schema_version: str = TRACE_SCHEMA_VERSION
    config: Optional[RunConfig] = None


@dataclass
class RunCompleteEvent:
    """Terminal JSONL line — all four required outcome fields per §7."""

    kind: Literal["run_complete"] = "run_complete"
    event_id: int = 0
    run_id: str = ""
    refine_round: int = 0
    caused_by: Optional[int] = None
    timing: Optional[Timing] = None
    mode_final: ModeFinal = "grounded"
    outcome_final: OutcomeFinal = "completed"
    refusal_reason: Optional[str] = None
    evidence_fingerprint: Optional[EvidenceFingerprint] = None


@dataclass
class AnswerabilityEvent:
    kind: Literal["answerability"] = "answerability"
    event_id: int = 0
    run_id: str = ""
    refine_round: int = 0
    caused_by: Optional[int] = None
    timing: Optional[Timing] = None
    in_scope: bool = True
    speculative: bool = False
    reason: str = ""


@dataclass
class PlanEvent:
    kind: Literal["plan"] = "plan"
    event_id: int = 0
    run_id: str = ""
    refine_round: int = 0
    caused_by: Optional[int] = None
    timing: Optional[Timing] = None
    tool_calls_proposed: list[dict[str, str]] = field(default_factory=list)
    tool_calls_after_validation: list[dict[str, str]] = field(default_factory=list)
    planner_input_summary: list[int] = field(default_factory=list)
    validation_errors: list[str] = field(default_factory=list)
    repair_count: int = 0
    model_id: str = ""


@dataclass
class DedupSkipEvent:
    kind: Literal["dedup_skip"] = "dedup_skip"
    event_id: int = 0
    run_id: str = ""
    refine_round: int = 0
    caused_by: Optional[int] = None
    timing: Optional[Timing] = None
    tool_name: str = ""
    query: str = ""
    normalized_query: str = ""


@dataclass
class ToolResultEvent:
    kind: Literal["tool_result"] = "tool_result"
    event_id: int = 0
    run_id: str = ""
    refine_round: int = 0
    caused_by: Optional[int] = None
    timing: Optional[Timing] = None
    tool_name: str = ""
    query: str = ""
    normalized_query: str = ""
    ok: bool = False
    reason: str = ""
    failure_class: Optional[FailureClass] = None
    source_id: Optional[str] = None
    content_full: str = ""
    content_for_synthesis: str = ""
    truncated: bool = False


@dataclass
class SufficiencyEvent:
    kind: Literal["sufficiency"] = "sufficiency"
    event_id: int = 0
    run_id: str = ""
    refine_round: int = 0
    caused_by: Optional[int] = None
    timing: Optional[Timing] = None
    passed: bool = False
    reason: str = ""
    matched_event_ids: list[int] = field(default_factory=list)
    rejected_event_ids: list[int] = field(default_factory=list)
    rejected_reasons: dict[str, str] = field(default_factory=dict)
    rule_version: str = "sufficiency_v1"


@dataclass
class SynthesizeEvent:
    kind: Literal["synthesize"] = "synthesize"
    event_id: int = 0
    run_id: str = ""
    refine_round: int = 0
    caused_by: Optional[int] = None
    timing: Optional[Timing] = None
    mode_model: ModeFinal = "grounded"
    mode_enforced: ModeFinal = "grounded"
    claims_raw: list[dict[str, Any]] = field(default_factory=list)
    claims_validated: list[dict[str, Any]] = field(default_factory=list)
    context_event_ids: list[int] = field(default_factory=list)
    chars_fed: int = 0
    model_id: str = ""


@dataclass
class DroppedContextEvent:
    kind: Literal["dropped_context"] = "dropped_context"
    event_id: int = 0
    run_id: str = ""
    refine_round: int = 0
    caused_by: Optional[int] = None
    timing: Optional[Timing] = None
    dropped_event_id: int = 0
    reason: str = ""


@dataclass
class ErrorEvent:
    kind: Literal["error"] = "error"
    event_id: int = 0
    run_id: str = ""
    refine_round: int = 0
    caused_by: Optional[int] = None
    timing: Optional[Timing] = None
    error_type: str = ""
    message: str = ""


AgentEvent = (
    RunHeaderEvent
    | RunCompleteEvent
    | AnswerabilityEvent
    | PlanEvent
    | DedupSkipEvent
    | ToolResultEvent
    | SufficiencyEvent
    | SynthesizeEvent
    | DroppedContextEvent
    | ErrorEvent
)


def _now_timing(duration_ms: int = 0) -> Timing:
    return Timing(timestamp_ms=int(time.time() * 1000), duration_ms=duration_ms)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _event_to_dict(event: AgentEvent) -> dict[str, Any]:
    data = asdict(event)
    # JSON null for optional refusal_reason on run_complete when not refused.
    return data


def validate_run_complete(
    mode_final: ModeFinal,
    outcome_final: OutcomeFinal,
    refusal_reason: Optional[str],
) -> None:
    """Enforce mode_final / outcome_final / refusal_reason invariants.

    Description:
        Validates terminal field combinations per DESIGN.md §7 including
        degraded mass-429 handling.

    Input:
        mode_final, outcome_final, refusal_reason: Terminal run fields.

    Output:
        None; raises AgentStateError on violation.

    When to use:
        Immediately before writing run_complete.

    When not to use:
        N/A.
    """
    if mode_final == "refused":
        if outcome_final not in {"out_of_scope", "degraded"}:
            raise AgentStateError(
                "mode_final=refused requires outcome_final in {out_of_scope, degraded}"
            )
        if not refusal_reason:
            raise AgentStateError("mode_final=refused requires non-null refusal_reason")
    else:
        if refusal_reason is not None:
            raise AgentStateError("refusal_reason must be null unless mode_final=refused")

    if outcome_final == "out_of_scope":
        if mode_final != "refused":
            raise AgentStateError("outcome_final=out_of_scope requires mode_final=refused")

    if outcome_final == "degraded":
        if mode_final not in {"caveated", "refused"}:
            raise AgentStateError(
                "outcome_final=degraded requires mode_final in {caveated, refused}"
            )

    if outcome_final == "insufficient_evidence":
        if mode_final != "caveated":
            raise AgentStateError(
                "outcome_final=insufficient_evidence requires mode_final=caveated"
            )


@dataclass
class AgentState:
    """Working memory and trace writer for one agent run.

    Description:
        Holds run header metadata and append-only events. Writes JSONL
        incrementally to traces/{run_id}.jsonl.

    Input:
        Constructed at run start with question metadata from batch runner
        or CLI.

    Output:
        Trace file path via ``trace_path``; serialized events.

    When to use:
        One instance per ``python agent.py`` invocation.

    When not to use:
        Do not share across runs or persist between invocations.
    """

    question: str
    question_ref: str = ""
    question_type: str = ""
    variant: Variant = "refine"
    experiment_id: Optional[str] = None
    refine_disabled: bool = False
    speculative: bool = False
    config: Optional[RunConfig] = None

    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    started_at: str = field(default_factory=_iso_now)
    refine_round: int = 0
    events: list[AgentEvent] = field(default_factory=list)
    _next_event_id: int = field(default=1, repr=False)
    _trace_file: Optional[Path] = field(default=None, repr=False)
    _header_written: bool = field(default=False, repr=False)
    _complete_written: bool = field(default=False, repr=False)
    plan_event_count: int = field(default=0, repr=False)

    @property
    def trace_path(self) -> Path:
        """Path to the JSONL trace file for this run."""
        if self._trace_file is None:
            traces_dir = Path("traces")
            traces_dir.mkdir(exist_ok=True)
            self._trace_file = traces_dir / f"{self.run_id}.jsonl"
        return self._trace_file

    def _append_line(self, payload: dict[str, Any]) -> None:
        with self.trace_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def write_run_header(self) -> RunHeaderEvent:
        """Write run_header as the first JSONL line.

        Description:
            Must be called once before any other events.

        Input:
            None — uses AgentState header fields.

        Output:
            The run_header event.

        When to use:
            At run start.

        When not to use:
            Never call twice.
        """
        if self._header_written:
            raise AgentStateError("run_header already written")
        header = RunHeaderEvent(
            event_id=0,
            run_id=self.run_id,
            question=self.question,
            question_ref=self.question_ref,
            question_type=self.question_type,
            variant=self.variant,
            experiment_id=self.experiment_id,
            refine_disabled=self.refine_disabled,
            speculative=self.speculative,
            started_at=self.started_at,
            trace_schema_version=TRACE_SCHEMA_VERSION,
            config=self.config,
        )
        self._append_line(_event_to_dict(header))
        self._header_written = True
        return header

    def append_event(self, event: AgentEvent) -> AgentEvent:
        """Assign event_id, append to log, and flush to JSONL.

        Description:
            Intermediate events only — not run_header or run_complete.

        Input:
            Event dataclass with kind set; event_id assigned here.

        Output:
            Same event with event_id populated.

        When to use:
            For answerability, plan, tool_result, sufficiency, etc.

        When not to use:
            Use write_run_header / write_run_complete for terminal lines.
        """
        if isinstance(event, (RunHeaderEvent, RunCompleteEvent)):
            raise AgentStateError("use write_run_header or write_run_complete")
        if not self._header_written:
            raise AgentStateError("run_header must be written first")

        event.event_id = self._next_event_id
        event.run_id = self.run_id
        if event.timing is None:
            event.timing = _now_timing()
        self._next_event_id += 1
        self.events.append(event)
        if isinstance(event, PlanEvent):
            self.plan_event_count += 1
        self._append_line(_event_to_dict(event))
        return event

    def compute_evidence_fingerprint(self) -> EvidenceFingerprint:
        """Build sorted evidence_fingerprint from ok=True tool_results.

        Description:
            Used by run_complete per DESIGN.md §5e.

        Input:
            None — scans self.events.

        Output:
            EvidenceFingerprint with sorted source_ids and tools_used.

        When to use:
            When writing run_complete.

        When not to use:
            N/A.
        """
        source_ids: set[str] = set()
        tools: set[str] = set()
        for ev in self.events:
            if isinstance(ev, ToolResultEvent) and ev.ok and ev.source_id:
                source_ids.add(ev.source_id)
                tools.add(ev.tool_name)
        return EvidenceFingerprint(
            source_ids=sorted(source_ids),
            tools_used=sorted(tools),
        )

    def has_ok_tool_results(self) -> bool:
        """Return True if any ok=True tool_result exists."""
        return any(
            isinstance(ev, ToolResultEvent) and ev.ok for ev in self.events
        )

    def write_run_complete(
        self,
        mode_final: ModeFinal,
        outcome_final: OutcomeFinal,
        refusal_reason: Optional[str] = None,
    ) -> RunCompleteEvent:
        """Write terminal run_complete JSONL line with all four outcome fields.

        Description:
            Validates invariants, computes evidence_fingerprint, appends
            as the last line.

        Input:
            mode_final, outcome_final, refusal_reason: Terminal taxonomy.

        Output:
            RunCompleteEvent.

        When to use:
            Once at run end.

        When not to use:
            Never call without run_header first.
        """
        if self._complete_written:
            raise AgentStateError("run_complete already written")
        if not self._header_written:
            raise AgentStateError("run_header must be written first")

        validate_run_complete(mode_final, outcome_final, refusal_reason)
        complete = RunCompleteEvent(
            event_id=self._next_event_id,
            run_id=self.run_id,
            refine_round=self.refine_round,
            caused_by=None,
            timing=_now_timing(),
            mode_final=mode_final,
            outcome_final=outcome_final,
            refusal_reason=refusal_reason,
            evidence_fingerprint=self.compute_evidence_fingerprint(),
        )
        self._next_event_id += 1
        self._complete_written = True
        self._append_line(_event_to_dict(complete))
        return complete

    @staticmethod
    def resolve_degraded_mode(state: "AgentState") -> ModeFinal:
        """Pick mode_final for outcome_final=degraded per §7.

        Description:
            caveated when partial evidence exists; refused when none.

        Input:
            state: Current run state.

        Output:
            mode_final value paired with degraded outcome.

        When to use:
            Groq mass-429 early termination path.

        When not to use:
            N/A.
        """
        return "caveated" if state.has_ok_tool_results() else "refused"
