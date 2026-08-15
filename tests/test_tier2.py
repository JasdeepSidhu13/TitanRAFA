"""Tier 2 single_pass flag and comparison runner tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from agent import run_question
from run_result import read_event_sequence
from tier2 import OUTPUT_PATH, load_tier2_questions, run_tier2_comparison

REPO = Path(__file__).resolve().parent.parent


def test_load_tier2_questions_q4_q6():
    rows = load_tier2_questions()
    refs = [r.question_ref for r in rows]
    assert refs == ["Q4", "Q6"]
    assert rows[0].question_type == "multi_source_synthesis"
    assert rows[1].question_type == "cross_tool_synthesis"


def test_single_pass_sets_refine_disabled_in_trace():
    result = run_question(
        "How did the Federal Reserve respond to 2008 vs COVID-19?",
        question_ref="Q4",
        question_type="multi_source_synthesis",
        offline=True,
        experiment_id="tier2-test-single-pass",
        single_pass=True,
        variant="single_pass",
    )
    header = json.loads(Path(result.trace_path).read_text(encoding="utf-8").splitlines()[0])
    assert header["variant"] == "single_pass"
    assert header["refine_disabled"] is True
    assert header["experiment_id"] == "tier2-test-single-pass"
    plan_count = sum(
        1
        for ln in Path(result.trace_path).read_text(encoding="utf-8").splitlines()
        if json.loads(ln).get("kind") == "plan"
    )
    assert plan_count == 1


def test_refine_variant_enables_refine_in_trace():
    result = run_question(
        "How did the Federal Reserve respond to 2008 vs COVID-19?",
        question_ref="Q4",
        question_type="multi_source_synthesis",
        offline=True,
        experiment_id="tier2-test-refine",
        single_pass=False,
        variant="refine",
    )
    header = json.loads(Path(result.trace_path).read_text(encoding="utf-8").splitlines()[0])
    assert header["variant"] == "refine"
    assert header["refine_disabled"] is False
    plan_count = sum(
        1
        for ln in Path(result.trace_path).read_text(encoding="utf-8").splitlines()
        if json.loads(ln).get("kind") == "plan"
    )
    assert plan_count >= 2


def test_cli_single_pass_flag():
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO / "agent.py"),
            "--offline",
            "--single-pass",
            "What is GDP?",
            "--question-ref",
            "Q1",
            "--question-type",
            "single_source_factual",
            "--experiment-id",
            "tier2-cli-single-pass",
        ],
        capture_output=True,
        text=True,
        cwd=REPO,
        env={**os.environ, "OFFLINE_MODE": "1"},
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    trace_line = next(ln for ln in proc.stdout.splitlines() if ln.startswith("Trace:"))
    trace_path = REPO / trace_line.split("Trace:", 1)[1].strip()
    header = json.loads(trace_path.read_text(encoding="utf-8").splitlines()[0])
    assert header["variant"] == "single_pass"
    assert header["refine_disabled"] is True


def test_offline_tier2_comparison_writes_markdown_and_pairs_traces():
    out = run_tier2_comparison(offline=True, experiment_id="tier2-offline-test")
    assert out == OUTPUT_PATH
    text = OUTPUT_PATH.read_text(encoding="utf-8")
    assert "Experiment ID: `tier2-offline-test`" in text
    assert "### variant: `single_pass`" in text
    assert "### variant: `refine`" in text
    assert "**Event sequence:**" in text
    assert "**Groq complete() calls:**" in text
    assert text.count("## Q4") == 1
    assert text.count("## Q6") == 1

    traces: dict[tuple[str, str], dict] = {}
    for path in REPO.glob("traces/*.jsonl"):
        header = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
        if header.get("experiment_id") != "tier2-offline-test":
            continue
        key = (header["question_ref"], header["variant"])
        traces[key] = header

    assert set(ref for ref, _ in traces) == {"Q4", "Q6"}
    for ref in ("Q4", "Q6"):
        assert (ref, "single_pass") in traces
        assert (ref, "refine") in traces
        for variant in ("single_pass", "refine"):
            assert traces[(ref, variant)]["experiment_id"] == "tier2-offline-test"


def test_read_event_sequence_format():
    result = run_question(
        "test",
        question_ref="Q1",
        question_type="single_source_factual",
        offline=True,
        single_pass=True,
    )
    seq = read_event_sequence(result.trace_path)
    assert seq.startswith("0:run_header")
    assert "answerability" in seq
    assert "run_complete" in seq
