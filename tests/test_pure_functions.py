"""Pure-function and invariant tests for Tier 1 policy logic."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from agentstate import AgentState, AgentStateError, ToolResultEvent, validate_run_complete
from checks import answerability_check, is_duplicate_call, sufficiency_check
from synthesizer import _compute_mode_enforced, _validate_claims
from tools.base import Tool


# --- dedup normalization ---


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Fed Discount Window!", "fed discount window"),
        ("  Multiple   Spaces  ", "multiple spaces"),
        ("UPPER-case", "uppercase"),
        ("punctuation!!!", "punctuation"),
        ("Fed, Reserve; Window.", "fed reserve window"),
    ],
)
def test_dedup_normalize_query(raw: str, expected: str):
    assert Tool.normalize_query(raw) == expected


def test_dedup_detects_normalized_duplicate():
    state = AgentState(question="test", question_type="single_source_factual")
    state.events = [
        ToolResultEvent(
            event_id=1,
            tool_name="wikipedia",
            query="Fed discount window",
            normalized_query=Tool.normalize_query("Fed discount window"),
            ok=True,
            reason="ok",
            source_id="wikipedia:Discount_window",
            content_full="content",
            content_for_synthesis="content",
        )
    ]
    assert is_duplicate_call(state, "wikipedia", "FED discount window!!!") is True
    assert is_duplicate_call(state, "wikipedia", "completely different query") is False
    assert is_duplicate_call(state, "arxiv", "Fed discount window") is False


# --- answerability ---


def test_answerability_out_of_scope_by_question_type():
    result = answerability_check("Any text", "out_of_scope")
    assert result.in_scope is False
    assert result.method == "rules"
    assert "question_type:out_of_scope" in result.matched_rules


def test_answerability_keyword_best_blocks_in_scope():
    result = answerability_check("What is the best pizza in NYC?", "single_source_factual")
    assert result.in_scope is False
    assert any("best" in r for r in result.matched_rules)


def test_answerability_in_scope_factual():
    result = answerability_check("What is GDP?", "single_source_factual")
    assert result.in_scope is True
    assert result.speculative is False


# --- sufficiency: diversity gate (question_type primary) ---


def _wiki(event_id: int, title: str, content: str) -> ToolResultEvent:
    return ToolResultEvent(
        event_id=event_id,
        tool_name="wikipedia",
        query="fed policy",
        normalized_query="fed policy",
        ok=True,
        reason="ok",
        source_id=f"wikipedia:{title}",
        content_full=content,
        content_for_synthesis=content,
    )


def _arxiv(event_id: int, title: str, abstract: str) -> ToolResultEvent:
    content = f"Title: {title}\nAbstract: {abstract}"
    return ToolResultEvent(
        event_id=event_id,
        tool_name="arxiv",
        query="yield curve",
        normalized_query="yield curve",
        ok=True,
        reason="ok",
        source_id="arxiv:2301.00001",
        content_full=content,
        content_for_synthesis=content,
    )


def test_sufficiency_diversity_gate_requires_two_tools():
    state = AgentState(
        question="How did Fed policy differ between 2008 and COVID-19?",
        question_type="multi_source_synthesis",
    )
    state.events = [
        _wiki(3, "Federal_Reserve", "Federal Reserve monetary policy crisis"),
        _wiki(4, "COVID-19", "Federal Reserve COVID monetary response"),
    ]
    result = sufficiency_check(
        state, state.question, "multi_source_synthesis", plan_event_id=2
    )
    assert result.passed is False
    assert "diversity_gate deciding factor" in result.reason
    assert "question_type=multi_source_synthesis" in result.reason
    assert len(result.distinct_tools_matched) == 1


def test_sufficiency_diversity_gate_passes_with_two_tools():
    state = AgentState(
        question="How did Fed policy differ between crises?",
        question_type="multi_source_synthesis",
    )
    state.events = [
        _wiki(3, "Federal_Reserve", "Federal Reserve monetary policy crisis"),
        _arxiv(4, "Fed COVID Policy", "monetary policy crisis federal reserve"),
    ]
    result = sufficiency_check(
        state, state.question, "multi_source_synthesis", plan_event_id=2
    )
    assert result.passed is True
    assert len(result.distinct_tools_matched) == 2


# --- sufficiency: data_retrieval rule ---


def test_sufficiency_data_retrieval_rejects_wikipedia_substitute():
    state = AgentState(
        question="What is the current US unemployment rate?",
        question_type="data_retrieval",
    )
    state.events = [
        _wiki(3, "Unemployment_in_the_United_States", "US unemployment historical data"),
    ]
    result = sufficiency_check(state, state.question, "data_retrieval", plan_event_id=2)
    assert result.passed is False
    assert "data_retrieval" in result.reason
    assert result.matched_event_ids == []
    assert 3 in result.rejected_event_ids
    assert "fred" in result.rejected_reasons["3"].lower() or "substitute" in result.rejected_reasons["3"].lower()


# --- claim source_id validation ---


def test_validate_claims_rejects_unknown_source_id():
    validated, errors = _validate_claims(
        [{"text": "claim", "source_id": "wikipedia:Ghost", "inference": False}],
        {"wikipedia:Real"},
    )
    assert not validated
    assert errors


def test_validate_claims_accepts_known_source_id():
    validated, errors = _validate_claims(
        [{"text": "claim", "source_id": "wikipedia:Real", "inference": False}],
        {"wikipedia:Real"},
    )
    assert validated
    assert not errors


def test_validate_claims_allows_inference_without_source_id():
    validated, errors = _validate_claims(
        [{"text": "speculative", "source_id": None, "inference": True}],
        set(),
    )
    assert validated
    assert not errors


# --- mode_model vs mode_enforced ---


def test_mode_enforced_caveated_when_inference_present():
    claims = [{"text": "maybe", "source_id": None, "inference": True}]
    assert _compute_mode_enforced("grounded", claims) == "caveated"


def test_mode_enforced_grounded_when_all_grounded():
    claims = [{"text": "fact", "source_id": "wikipedia:X", "inference": False}]
    assert _compute_mode_enforced("grounded", claims) == "grounded"


def test_mode_enforced_never_trusts_grounded_model_with_inference():
    claims = [
        {"text": "fact", "source_id": "wikipedia:X", "inference": False},
        {"text": "guess", "source_id": None, "inference": True},
    ]
    assert _compute_mode_enforced("grounded", claims) == "caveated"


# --- run_complete cross-field invariants ---


@pytest.mark.parametrize(
    "mode_final,outcome_final,refusal_reason",
    [
        ("grounded", "completed", None),
        ("caveated", "insufficient_evidence", None),
        ("refused", "out_of_scope", "subjective question"),
        ("caveated", "degraded", None),
        ("refused", "degraded", "no evidence before groq failure"),
    ],
)
def test_validate_run_complete_accepts_valid_combinations(
    mode_final, outcome_final, refusal_reason
):
    validate_run_complete(mode_final, outcome_final, refusal_reason)


@pytest.mark.parametrize(
    "mode_final,outcome_final,refusal_reason,fragment",
    [
        ("grounded", "completed", "should be null", "refusal_reason must be null"),
        ("caveated", "out_of_scope", None, "out_of_scope requires mode_final=refused"),
        ("refused", "completed", "bad", "mode_final=refused requires outcome_final"),
        ("grounded", "insufficient_evidence", None, "insufficient_evidence requires mode_final=caveated"),
    ],
)
def test_validate_run_complete_rejects_invalid_combinations(
    mode_final, outcome_final, refusal_reason, fragment
):
    with pytest.raises(AgentStateError, match=fragment):
        validate_run_complete(mode_final, outcome_final, refusal_reason)


def test_validate_run_complete_rejects_refused_with_insufficient_evidence():
    with pytest.raises(AgentStateError):
        validate_run_complete("refused", "insufficient_evidence", "bad combo")


# --- offline pipeline smoke ---

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_offline_pipeline_smoke_produces_valid_run_complete():
    """End-to-end OFFLINE_MODE run with all four run_complete fields."""
    env = {**os.environ, "OFFLINE_MODE": "1"}
    result = subprocess.run(
        [
            sys.executable,
            "agent.py",
            "--offline",
            "What is the Federal Reserve discount window?",
            "--question-ref",
            "Q1",
            "--question-type",
            "single_source_factual",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr

    trace_files = sorted(
        (REPO_ROOT / "traces").glob("*.jsonl"), key=lambda p: p.stat().st_mtime
    )
    assert trace_files

    lines = trace_files[-1].read_text(encoding="utf-8").strip().splitlines()
    header = json.loads(lines[0])
    complete = json.loads(lines[-1])

    assert header["kind"] == "run_header"
    assert complete["kind"] == "run_complete"

    for field in ("mode_final", "outcome_final", "refusal_reason", "evidence_fingerprint"):
        assert field in complete

    assert complete["evidence_fingerprint"] is not None
    assert isinstance(complete["evidence_fingerprint"]["source_ids"], list)
    assert isinstance(complete["evidence_fingerprint"]["tools_used"], list)

    validate_run_complete(
        complete["mode_final"],
        complete["outcome_final"],
        complete["refusal_reason"],
    )
