"""Abstract tool interface and shared retry policy.

Responsibility:
    Defines the Tool contract, RetryPolicy enforcement, and ToolResult
    return type. All outbound tool calls self-enforce rate limits, timeouts,
    and retries without raising into the orchestrator loop.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from typing import Any, Callable, Literal, Optional

FailureClass = Literal["timeout", "http_429", "parse_error", "empty_result"]

SYNTHESIS_CHAR_LIMIT = 1500


@dataclass
class ToolCitation:
    """Citation metadata returned with every successful tool invocation."""

    title: str
    url_or_id: str


@dataclass
class ToolResult:
    """Normalized result from a single tool invocation.

    Description:
        Returned by every ``Tool.invoke`` call. Failures never raise;
        ``ok=False`` carries ``failure_class`` for machine diagnosis.

    Input:
        Populated by concrete tools and RetryPolicy wrappers.

    Output:
        Consumed by executor and logged as ``tool_result`` events.

    When to use:
        Always as the return type of ``Tool.invoke``.

    When not to use:
        Do not use as an event log record directly; convert in agentstate.
    """

    ok: bool
    reason: str
    tool_name: str
    query: str
    normalized_query: str
    source_id: Optional[str] = None
    content_full: str = ""
    content_for_synthesis: str = ""
    truncated: bool = False
    failure_class: Optional[FailureClass] = None
    citation: Optional[ToolCitation] = None

    def __post_init__(self) -> None:
        if not self.ok and self.failure_class is None:
            raise ValueError("failure_class is required when ok=False")


@dataclass
class RetryPolicy:
    """Per-tool retry, rate-limit, and timeout policy.

    Description:
        Loaded from config/tool_policy.yaml per tool section. Enforces
        ``min_interval_s`` before every outbound call and retries with
        exponential backoff, honoring ``Retry-After`` when present.

    Input:
        Policy fields from YAML plus optional shared last-call timestamp map.

    Output:
        Configured policy used by ``execute``.

    When to use:
        One instance per Tool at initialization.

    When not to use:
        Do not share one RetryPolicy across tools with different names unless
        rate state should be shared intentionally.
    """

    tool_name: str
    min_interval_s: float
    timeout_s: float
    max_retries: int
    backoff_base_s: float
    honor_retry_after_header: bool = False
    rate_store: Optional[Any] = None  # RateLimitStore, optional cross-process gate
    _last_call_monotonic: float = field(default=0.0, repr=False)

    def wait_for_interval(self, deadline: Optional[float] = None) -> bool:
        """Sleep until min_interval_s elapsed since last call.

        Description:
            Client-side rate gate applied before every outbound request.

        Input:
            deadline: Optional monotonic deadline; returns False if insufficient
                budget remains for the sleep.

        Output:
            True if gate satisfied; False if deadline prevents waiting.

        When to use:
            Before each tool HTTP call inside ``execute``.

        When not to use:
            N/A.
        """
        if self.rate_store is not None:
            import time as _time

            since = self.rate_store.seconds_since_last_call()
            remaining = self.min_interval_s - since
            if remaining <= 0:
                return True
            if deadline is not None and _time.monotonic() + remaining > deadline:
                return False
            _time.sleep(remaining)
            return True

        elapsed = time.monotonic() - self._last_call_monotonic
        remaining = self.min_interval_s - elapsed
        if remaining <= 0:
            return True
        if deadline is not None and time.monotonic() + remaining > deadline:
            return False
        time.sleep(remaining)
        return True

    def compute_backoff(
        self, attempt: int, retry_after_header: Optional[str] = None
    ) -> float:
        """Compute sleep duration before next retry.

        Description:
            Honors ``Retry-After`` when parseable; otherwise exponential
            backoff from ``backoff_base_s``.

        Input:
            attempt: Zero-based retry index.
            retry_after_header: Optional HTTP Retry-After header value.

        Output:
            Seconds to sleep.

        When to use:
            Between retry attempts in ``execute``.

        When not to use:
            N/A.
        """
        if retry_after_header and self.honor_retry_after_header:
            try:
                if retry_after_header.isdigit():
                    return float(retry_after_header)
                return max(
                    0.0,
                    parsedate_to_datetime(retry_after_header).timestamp()
                    - time.time(),
                )
            except (ValueError, OverflowError, OSError):
                pass
        return self.backoff_base_s * (2**attempt)

    def execute(
        self,
        operation: Callable[[], tuple[ToolResult, Optional[str]]],
        deadline: Optional[float] = None,
    ) -> ToolResult:
        """Run an operation with rate gate, timeout, and retries.

        Description:
            Never raises. On exhaustion returns ``ToolResult(ok=False)`` with
            ``failure_class`` set.

        Input:
            operation: Callable returning ``(ToolResult, retry_after_header)``.
                The header is used only when ``ok=False`` and retry is considered.
            deadline: Optional monotonic run deadline.

        Output:
            Final ``ToolResult`` after success or retry exhaustion.

        When to use:
            Wrap every outbound tool HTTP call.

        When not to use:
            Do not wrap LLM calls; use a separate Groq client policy.
        """
        if not self.wait_for_interval(deadline):
            return ToolResult(
                ok=False,
                reason="deadline exceeded before rate gate",
                tool_name=self.tool_name,
                query="",
                normalized_query="",
                failure_class="timeout",
            )

        last_result: Optional[ToolResult] = None
        for attempt in range(self.max_retries + 1):
            self._last_call_monotonic = time.monotonic()
            if self.rate_store is not None:
                self.rate_store.record_call_now()
            try:
                result, retry_after = operation()
            except Exception as exc:  # noqa: BLE001 — tool layer must not raise
                result = ToolResult(
                    ok=False,
                    reason=str(exc),
                    tool_name=self.tool_name,
                    query="",
                    normalized_query="",
                    failure_class="parse_error",
                )
                retry_after = None

            if result.ok:
                return result

            last_result = result
            if attempt >= self.max_retries:
                break

            backoff = self.compute_backoff(attempt, retry_after)
            if deadline is not None and time.monotonic() + backoff > deadline:
                break
            time.sleep(backoff)
            if not self.wait_for_interval(deadline):
                break

        assert last_result is not None
        if last_result.failure_class is None:
            last_result.failure_class = "timeout"
        return last_result


class Tool(ABC):
    """Abstract base for Wikipedia, arXiv, and FRED tools.

    Description:
        Each tool owns a ``RetryPolicy`` and implements ``invoke`` without
        raising to the orchestrator.

    Input:
        Query strings from planner tool_calls.

    Output:
        ``ToolResult`` instances.

    When to use:
        Subclass for each external data source.

    When not to use:
        Do not use for LLM or state management calls.
    """

    name: str

    def __init__(self, policy: RetryPolicy) -> None:
        self.policy = policy

    @abstractmethod
    def invoke(self, query: str, deadline: Optional[float] = None) -> ToolResult:
        """Execute a tool query and return a normalized result.

        Description:
            Must not raise. Enforces retry policy internally or via
            ``self.policy.execute``.

        Input:
            query: Raw query string from planner.
            deadline: Optional monotonic run deadline.

        Output:
            ``ToolResult`` with ``failure_class`` when ``ok=False``.

        When to use:
            Called by executor for each proposed tool call.

        When not to use:
            N/A.
        """

    @staticmethod
    def normalize_query(query: str) -> str:
        """Normalize a query for dedup comparisons.

        Description:
            Lowercase, collapse whitespace, strip punctuation per DESIGN.md §5.

        Input:
            query: Raw query string.

        Output:
            Normalized string.

        When to use:
            Before dedup checks and tool_result logging.

        When not to use:
            N/A.
        """
        import re
        import string

        lowered = query.lower()
        collapsed = re.sub(r"\s+", " ", lowered).strip()
        return collapsed.translate(str.maketrans("", "", string.punctuation))
