"""Registered tools available to the executor this session.

Description:
    FRED is Tier 3; until wired, data_retrieval sufficiency cannot pass.
"""

from __future__ import annotations

REGISTERED_TOOLS: frozenset[str] = frozenset({"wikipedia", "arxiv"})

DATA_SOURCE_BY_QUESTION_TYPE: dict[str, list[str]] = {
    "data_retrieval": ["fred"],
}
