"""Tests for reference question loader and batch runner helpers."""

from __future__ import annotations

from pathlib import Path

from scripts.reference_loader import load_reference_questions


def test_load_reference_questions_returns_eight_rows():
    rows = load_reference_questions()
    assert len(rows) == 8
    assert rows[0].question_ref == "Q1"
    assert rows[0].question_type == "single_source_factual"
    assert rows[6].question_ref == "Q7"
    assert rows[6].question_type == "out_of_scope"
    assert rows[7].question_type == "speculative"


def test_reference_question_fields():
    rows = load_reference_questions()
    q4 = next(r for r in rows if r.question_ref == "Q4")
    assert q4.question_type == "multi_source_synthesis"
    assert "2008" in q4.question
