"""arXiv tool via export API Atom feed.

Responsibility:
    Query arXiv export API with rate limiting persisted across process
    invocations (see tools/rate_limit.py). Honors Retry-After on 429.

Role in architecture:
    Tier 1 academic search tool per config/DESIGN.md §6.
"""

from __future__ import annotations

import re
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Optional

import httpx

from fixtures.loader import is_offline_mode, load_tool_fixture
from tools.base import Tool, ToolCitation, ToolResult
from tools.common import make_failure, make_success, title_overlap_score
from tools.policy import load_arxiv_retry_policy

ARXIV_EXPORT_API = "https://export.arxiv.org/api/query"
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


class ArxivTool(Tool):
    """Search arXiv and return the best matching paper abstract.

    Description:
        Uses arXiv Atom export API (no arxiv PyPI package). Returns first
        result with title overlap, or best overlap among top results.

    Input:
        Search query string.

    Output:
        ``ToolResult`` with ``source_id`` like ``arxiv:2301.00001`` and
        citation ``{title, url_or_id}``.

    When to use:
        Academic paper retrieval and cross-tool synthesis questions.

    When not to use:
        Current macro data (FRED); general encyclopedic facts (Wikipedia).
    """

    name = "arxiv"

    def __init__(self, policy=None) -> None:
        super().__init__(policy or load_arxiv_retry_policy())

    def invoke(self, query: str, deadline: Optional[float] = None) -> ToolResult:
        """Search arXiv for ``query`` without raising."""
        if is_offline_mode():
            return self._from_fixture(query)

        def operation() -> tuple[ToolResult, Optional[str]]:
            return self._fetch_live(query)

        result = self.policy.execute(operation, deadline=deadline)
        if not result.query:
            result.query = query
            result.normalized_query = self.normalize_query(query)
        return result

    def _from_fixture(self, query: str) -> ToolResult:
        data = load_tool_fixture(self.name, query)
        if not data.get("ok"):
            return make_failure(
                self.name,
                query,
                str(data.get("reason", "offline fixture failure")),
                data.get("failure_class", "empty_result"),
            )
        citation_data = data.get("citation", {})
        citation = ToolCitation(
            title=str(citation_data.get("title", "")),
            url_or_id=str(citation_data.get("url_or_id", "")),
        )
        return make_success(
            self.name,
            query,
            str(data["source_id"]),
            str(data.get("content_full", "")),
            citation,
            reason=str(data.get("reason", "offline fixture")),
        )

    def _fetch_live(self, query: str) -> tuple[ToolResult, Optional[str]]:
        params = {
            "search_query": f"all:{query}",
            "start": 0,
            "max_results": 5,
        }
        url = f"{ARXIV_EXPORT_API}?{urllib.parse.urlencode(params)}"

        try:
            with httpx.Client(timeout=self.policy.timeout_s) as client:
                resp = client.get(url, headers={"User-Agent": "TitanRAFA-research-agent/1.0"})
        except httpx.TimeoutException:
            return (
                make_failure(self.name, query, "arxiv request timed out", "timeout"),
                None,
            )
        except httpx.HTTPError as exc:
            return (
                make_failure(self.name, query, f"arxiv http error: {exc}", "parse_error"),
                None,
            )

        retry_after = resp.headers.get("Retry-After") if resp.status_code == 429 else None

        if resp.status_code == 429:
            return (
                make_failure(self.name, query, "arxiv rate limited (429)", "http_429"),
                retry_after,
            )
        if resp.status_code == 503:
            return (
                make_failure(self.name, query, "arxiv unavailable (503)", "http_429"),
                retry_after,
            )
        if resp.status_code != 200:
            return (
                make_failure(
                    self.name,
                    query,
                    f"arxiv unexpected status {resp.status_code}",
                    "parse_error",
                ),
                retry_after,
            )

        try:
            root = ET.fromstring(resp.text)
        except ET.ParseError:
            return (
                make_failure(self.name, query, "arxiv atom parse error", "parse_error"),
                None,
            )

        entries = root.findall("atom:entry", ATOM_NS)
        if not entries:
            return (
                make_failure(self.name, query, "arxiv search returned no entries", "empty_result"),
                None,
            )

        parsed_entries = [self._parse_entry(e) for e in entries]
        parsed_entries = [p for p in parsed_entries if p is not None]
        if not parsed_entries:
            return (
                make_failure(self.name, query, "arxiv entries lacked title/abstract", "empty_result"),
                None,
            )

        best = max(parsed_entries, key=lambda p: title_overlap_score(query, p["title"]))
        if title_overlap_score(query, best["title"]) < 1:
            best = parsed_entries[0]

        content = f"Title: {best['title']}\nAbstract: {best['abstract']}"
        citation = ToolCitation(title=best["title"], url_or_id=best["arxiv_id"])
        return (
            make_success(
                self.name,
                query,
                best["source_id"],
                content,
                citation,
                reason="arxiv atom export",
            ),
            None,
        )

    def _parse_entry(self, entry: ET.Element) -> Optional[dict[str, str]]:
        title_el = entry.find("atom:title", ATOM_NS)
        summary_el = entry.find("atom:summary", ATOM_NS)
        id_el = entry.find("atom:id", ATOM_NS)
        if title_el is None or summary_el is None or id_el is None:
            return None

        title = re.sub(r"\s+", " ", (title_el.text or "")).strip()
        abstract = re.sub(r"\s+", " ", (summary_el.text or "")).strip()
        raw_id = (id_el.text or "").rstrip("/")
        arxiv_id = raw_id.split("/abs/")[-1] if "/abs/" in raw_id else raw_id
        return {
            "title": title,
            "abstract": abstract,
            "arxiv_id": f"arxiv:{arxiv_id}",
            "source_id": f"arxiv:{arxiv_id}",
        }
