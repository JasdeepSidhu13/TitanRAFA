"""Shared helpers for concrete tool implementations."""

from __future__ import annotations

import re
from typing import Optional

from tools.base import SYNTHESIS_CHAR_LIMIT, FailureClass, ToolCitation, ToolResult

STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "of",
        "in",
        "on",
        "for",
        "to",
        "is",
        "are",
        "was",
        "were",
        "what",
        "how",
        "does",
        "do",
        "with",
        "from",
        "its",
        "it",
        "that",
        "this",
        "by",
        "as",
        "at",
        "be",
        "been",
        "have",
        "has",
        "had",
    }
)


def tokenize(text: str) -> set[str]:
    """Lowercase alphanumeric tokens excluding stopwords."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {w for w in words if w not in STOPWORDS and len(w) > 1}


def title_overlap_score(query: str, title: str) -> int:
    """Count overlapping non-stopword tokens between query and title."""
    q_tokens = tokenize(query)
    t_tokens = tokenize(title)
    return len(q_tokens & t_tokens)


def truncate_for_synthesis(content: str) -> tuple[str, bool]:
    """Truncate content to synthesis budget; return (text, truncated)."""
    if len(content) <= SYNTHESIS_CHAR_LIMIT:
        return content, False
    return content[:SYNTHESIS_CHAR_LIMIT], True


def make_failure(
    tool_name: str,
    query: str,
    reason: str,
    failure_class: FailureClass,
) -> ToolResult:
    """Build a failed ToolResult with normalized query and failure_class."""
    from tools.base import Tool

    return ToolResult(
        ok=False,
        reason=reason,
        tool_name=tool_name,
        query=query,
        normalized_query=Tool.normalize_query(query),
        failure_class=failure_class,
    )


def make_success(
    tool_name: str,
    query: str,
    source_id: str,
    content_full: str,
    citation: ToolCitation,
    reason: str = "ok",
) -> ToolResult:
    """Build a successful ToolResult with dual content views and citation."""
    from tools.base import Tool

    synth, truncated = truncate_for_synthesis(content_full)
    return ToolResult(
        ok=True,
        reason=reason,
        tool_name=tool_name,
        query=query,
        normalized_query=Tool.normalize_query(query),
        source_id=source_id,
        content_full=content_full,
        content_for_synthesis=synth,
        truncated=truncated,
        citation=citation,
    )
