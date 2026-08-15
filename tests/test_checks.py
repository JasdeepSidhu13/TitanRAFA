"""Tests for answerability, sufficiency, and dedup checks."""

from __future__ import annotations

import pytest

from agentstate import AgentState, PlanEvent, ToolResultEvent
from checks import (
    answerability_check,
    is_duplicate_call,
    make_dedup_skip_event,
    sufficiency_check,
)


def _wiki_event(event_id: int, title: str, content: str) -> ToolResultEvent:
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


def _arxiv_event(event_id: int, title: str, abstract: str) -> ToolResultEvent:
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


def test_answerability_out_of_scope_type():
    result = answerability_check("What is the best restaurant?", "out_of_scope")
    assert result.in_scope is False
    assert result.method == "rules"
    assert "question_type:out_of_scope" in result.matched_rules


def test_answerability_best_keyword():
    result = answerability_check("What is the best pizza?", "single_source_factual")
    assert result.in_scope is False
    assert any("best" in r for r in result.matched_rules)


def test_answerability_in_scope_speculative():
    result = answerability_check("Quantum encryption?", "speculative")
    assert result.in_scope is True
    assert result.speculative is True


def test_sufficiency_diversity_gate_fails_single_tool():
    state = AgentState(
        question="How did Fed policy differ between 2008 and COVID-19?",
        question_type="multi_source_synthesis",
    )
    state.events = [
        _wiki_event(3, "Federal_Reserve", "Federal Reserve monetary policy crisis"),
        _wiki_event(4, "COVID-19", "Federal Reserve COVID monetary response"),
    ]
    result = sufficiency_check(state, state.question, "multi_source_synthesis", plan_event_id=2)
    assert result.passed is False
    assert "diversity_gate deciding factor" in result.reason
    assert result.matched_event_ids == [3, 4]
    assert len(result.distinct_tools_matched) == 1


def test_sufficiency_diversity_passes_two_tools():
    state = AgentState(
        question="How did Fed policy differ between crises?",
        question_type="multi_source_synthesis",
    )
    state.events = [
        _wiki_event(3, "Federal_Reserve", "Federal Reserve monetary policy crisis"),
        _arxiv_event(4, "Fed COVID Policy", "monetary policy crisis federal reserve"),
    ]
    result = sufficiency_check(state, state.question, "multi_source_synthesis", plan_event_id=2)
    assert result.passed is True
    assert len(result.distinct_tools_matched) == 2


def test_sufficiency_data_retrieval_rejects_wikipedia():
    state = AgentState(
        question="What is the current US unemployment rate?",
        question_type="data_retrieval",
    )
    state.events = [
        _wiki_event(3, "Unemployment_in_the_United_States", "US unemployment historical"),
    ]
    result = sufficiency_check(state, state.question, "data_retrieval", plan_event_id=2)
    assert result.passed is False
    assert "data_retrieval" in result.reason
    assert result.matched_event_ids == []
    assert 3 in result.rejected_event_ids


def test_dedup_blocks_repeat_call():
    state = AgentState(question="test", question_type="single_source_factual")
    state.events = [
        ToolResultEvent(
            event_id=1,
            tool_name="wikipedia",
            query="Fed discount window",
            normalized_query="fed discount window",
            ok=True,
            reason="ok",
            source_id="wikipedia:Discount_window",
            content_full="discount window",
            content_for_synthesis="discount window",
        )
    ]
    assert is_duplicate_call(state, "wikipedia", "Fed discount window!") is True
    skip = make_dedup_skip_event(state, "wikipedia", "Fed discount window!", plan_event_id=5)
    assert skip.caused_by == 5
    assert skip.normalized_query == "fed discount window"
