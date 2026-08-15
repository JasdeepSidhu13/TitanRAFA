"""Load per-tool RetryPolicy from config/tool_policy.yaml."""

from __future__ import annotations

from typing import Optional

from constants import load_policy
from tools.base import RetryPolicy
from tools.rate_limit import RateLimitStore

# Shared store: arXiv persists last-call across process invocations via
# .ratelimit_state.json. Wikipedia uses in-memory gate only (shorter interval).
_ARXIV_RATE_STORE = RateLimitStore("arxiv")


def load_retry_policy(
    tool_name: str,
    *,
    rate_store: Optional[RateLimitStore] = None,
) -> RetryPolicy:
    """Build a RetryPolicy from the YAML section for ``tool_name``.

    Description:
        Reads timeout, retry, backoff, min_interval, and
        honor_retry_after_header from config/tool_policy.yaml.

    Input:
        tool_name: Key in tool_policy.yaml (e.g. ``wikipedia``, ``arxiv``).
        rate_store: Optional cross-process rate limit store (arxiv uses this).

    Output:
        Configured ``RetryPolicy``.

    When to use:
        Tool ``__init__`` for each concrete Tool class.

    When not to use:
        N/A.
    """
    section = load_policy()[tool_name]
    return RetryPolicy(
        tool_name=tool_name,
        min_interval_s=float(section["min_interval_s"]),
        timeout_s=float(section["timeout_s"]),
        max_retries=int(section["max_retries"]),
        backoff_base_s=float(section["backoff_base_s"]),
        honor_retry_after_header=bool(section.get("honor_retry_after_header", False)),
        rate_store=rate_store,
    )


def load_arxiv_retry_policy() -> RetryPolicy:
    """RetryPolicy for arXiv with cross-process rate state persistence."""
    return load_retry_policy("arxiv", rate_store=_ARXIV_RATE_STORE)


def load_wikipedia_retry_policy() -> RetryPolicy:
    """RetryPolicy for Wikipedia (in-memory min_interval only)."""
    return load_retry_policy("wikipedia")
