"""Tests for synthesizer validation, mode enforcement, and context budget."""

from __future__ import annotations

from agentstate import AgentState, SufficiencyEvent, ToolResultEvent
from constants import load_loop_bounds
from run_context import RunContext
from synthesizer import (
    SYNTH_CHAR_BUDGET,
    _compute_mode_enforced,
    _ensure_speculative_claim,
    _select_context,
    _templated_fallback,
    _validate_claims,
    run_synthesizer,
)


def _wiki(event_id: int, source_id: str, content: str) -> ToolResultEvent:
    return ToolResultEvent(
        event_id=event_id,
        tool_name="wikipedia",
        query="fed",
        normalized_query="fed",
        ok=True,
        reason="ok",
        source_id=source_id,
        content_full=content,
        content_for_synthesis=content,
    )


def test_inference_forces_caveated_even_when_model_grounded():
    claims = [{"text": "maybe", "source_id": None, "inference": True}]
    assert _compute_mode_enforced("grounded", claims) == "caveated"


def test_speculative_adds_inference_claim():
    claims = [{"text": "fact", "source_id": "wikipedia:X", "inference": False}]
    updated = _ensure_speculative_claim(claims, "Future of quantum encryption?")
    assert any(c["inference"] for c in updated)
    assert len(updated) == 2


def test_validate_claims_rejects_bad_source_id():
    validated, errors = _validate_claims(
        [{"text": "x", "source_id": "wikipedia:Missing", "inference": False}],
        {"wikipedia:Real"},
    )
    assert not validated
    assert errors


def test_validate_claims_accepts_valid_source_id():
    validated, errors = _validate_claims(
        [{"text": "x", "source_id": "wikipedia:Real", "inference": False}],
        {"wikipedia:Real"},
    )
    assert validated
    assert not errors


def test_context_budget_drops_low_relevance():
    big = "x" * (SYNTH_CHAR_BUDGET - 50)
    high = _wiki(1, "wikipedia:Federal_Reserve", "federal reserve monetary policy " + big)
    low = _wiki(2, "wikipedia:Unrelated", "unrelated topic content " * 20)
    _text, _ids, chars, drops = _select_context(
        "federal reserve monetary policy", [high, low]
    )
    assert chars <= SYNTH_CHAR_BUDGET
    assert drops
    assert any(d.dropped_event_id == 2 for d in drops)


def test_templated_fallback_is_caveated():
    claims, mode_model, mode_enforced = _templated_fallback(
        question="test",
        tool_results=[],
        speculative=False,
        valid_source_ids=set(),
    )
    assert mode_model == "caveated"
    assert mode_enforced == "caveated"
    assert claims[0]["inference"] is True


def test_offline_synthesizer_sets_caused_by_and_modes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    state = AgentState(
        question="What is GDP?",
        question_type="single_source_factual",
        speculative=False,
    )
    state.write_run_header()
    state.events.append(
        _wiki(1, "wikipedia:GDP", "Gross domestic product measures economic output.")
    )
    suff = SufficiencyEvent(event_id=2, passed=True, caused_by=1)
    state.events.append(suff)
    ctx = RunContext.from_bounds(load_loop_bounds())

    outcome = run_synthesizer(
        state,
        ctx,
        offline=True,
        caused_by=suff.event_id,
        sufficiency_passed=True,
        suff=suff,
    )

    assert outcome.event is not None
    assert outcome.event.caused_by == 2
    assert outcome.event.mode_model in {"grounded", "caveated"}
    assert outcome.event.mode_enforced in {"grounded", "caveated"}
    synth_events = [e for e in state.events if e.kind == "synthesize"]
    assert len(synth_events) == 1
