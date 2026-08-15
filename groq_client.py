"""Groq LLM client with retry, repair, and mass-429 handling.

Responsibility:
    HTTP calls to Groq chat completions per config/tool_policy.yaml groq
    section. Honors Retry-After when honor_retry_after_header is true.
    Checks run deadline before each attempt and repair re-prompt.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Any, Optional

import httpx

from constants import GroqPolicy, load_groq_policy
from run_context import RunContext

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"


@dataclass
class GroqCallResult:
    """Outcome of a Groq chat completion attempt."""

    ok: bool
    content: str
    reason: str
    status_code: Optional[int] = None
    is_429: bool = False
    retry_exhausted: bool = False
    retry_after_s: Optional[float] = None


class GroqClient:
    """Groq chat client with policy-driven retry and deadline checks.

    Description:
        Used by planner and synthesizer. On retry exhaustion the caller
        sets outcome_final=degraded with reason recorded on the LLM event.

    Input:
        Optional policy override; defaults to YAML groq section.

    Output:
        Parsed JSON content or failure metadata.

    When to use:
        Live planner/synthesizer calls.

    When not to use:
        Offline mode — use fixtures instead.
    """

    def __init__(self, policy: Optional[GroqPolicy] = None) -> None:
        self.policy = policy or load_groq_policy()
        self._api_key = os.environ.get("GROQ_API_KEY", "").strip()

    def chat_json(
        self,
        messages: list[dict[str, str]],
        ctx: RunContext,
        *,
        model: Optional[str] = None,
    ) -> GroqCallResult:
        """Call Groq and return assistant message content.

        Description:
            Retries on 429/5xx with backoff honoring Retry-After. Checks
            ctx.has_budget() before each attempt and repair.

        Input:
            messages: OpenAI-format chat messages.
            ctx: Run context for deadline and mass-429 tracking.
            model: Override model id.

        Output:
            GroqCallResult with content or failure reason.

        When to use:
            Planner and synthesizer LLM calls.

        When not to use:
            Offline fixture replay.
        """
        model_id = model or os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")
        last: GroqCallResult = GroqCallResult(
            ok=False, content="", reason="no attempts made"
        )

        for attempt in range(self.policy.max_retries + 1):
            if not ctx.has_budget(self.policy.timeout_s):
                return GroqCallResult(
                    ok=False,
                    content="",
                    reason="run_timeout_s exceeded before groq call",
                    retry_exhausted=True,
                )

            result = self._post_once(messages, model_id, ctx)
            last = result

            if result.ok:
                ctx.clear_groq_429()
                return result

            if result.is_429:
                ctx.mark_groq_429(
                    result.reason, threshold=self.policy.mass_429_threshold
                )
                if ctx.groq_degraded_reason:
                    result.retry_exhausted = True
                    return result

            if attempt >= self.policy.max_retries:
                result.retry_exhausted = True
                return result

            backoff = self._backoff(attempt, result)
            if not ctx.sleep_if_allowed(backoff):
                result.retry_exhausted = True
                result.reason = ctx.aborted_reason or result.reason
                return result

        last.retry_exhausted = True
        return last

    def _backoff(self, attempt: int, result: GroqCallResult) -> float:
        if (
            result.is_429
            and self.policy.honor_retry_after_header
            and result.retry_after_s is not None
        ):
            return max(0.0, result.retry_after_s)
        return self.policy.backoff_base_s * (2**attempt)

    def _post_once(
        self,
        messages: list[dict[str, str]],
        model_id: str,
        ctx: RunContext,
    ) -> GroqCallResult:
        timeout = min(self.policy.timeout_s, ctx.remaining_s())
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model_id,
            "messages": messages,
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
        }
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(GROQ_CHAT_URL, headers=headers, json=payload)
        except httpx.TimeoutException:
            return GroqCallResult(ok=False, content="", reason="groq request timed out")
        except httpx.HTTPError as exc:
            return GroqCallResult(ok=False, content="", reason=f"groq http error: {exc}")

        retry_after = resp.headers.get("Retry-After")
        retry_after_s = self._parse_retry_after(retry_after)
        if resp.status_code == 429:
            reason = "groq rate limited (429)"
            if retry_after:
                reason = f"{reason}; Retry-After={retry_after}"
            return GroqCallResult(
                ok=False,
                content="",
                reason=reason,
                status_code=429,
                is_429=True,
                retry_after_s=retry_after_s,
            )
        if resp.status_code >= 500:
            return GroqCallResult(
                ok=False,
                content="",
                reason=f"groq server error {resp.status_code}",
                status_code=resp.status_code,
            )
        if resp.status_code != 200:
            return GroqCallResult(
                ok=False,
                content="",
                reason=f"groq unexpected status {resp.status_code}",
                status_code=resp.status_code,
            )

        try:
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
        except (KeyError, ValueError, TypeError) as exc:
            return GroqCallResult(ok=False, content="", reason=f"groq parse error: {exc}")

        return GroqCallResult(ok=True, content=content, reason="ok")

    @staticmethod
    def _parse_retry_after(header: Optional[str]) -> Optional[float]:
        if not header:
            return None
        try:
            if header.isdigit():
                return float(header)
            return max(0.0, parsedate_to_datetime(header).timestamp() - time.time())
        except (ValueError, OverflowError, OSError):
            return None


def parse_json_content(content: str) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    """Parse JSON object from model content; return (data, error)."""
    try:
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            return None, "response is not a JSON object"
        return parsed, None
    except json.JSONDecodeError as exc:
        return None, str(exc)
