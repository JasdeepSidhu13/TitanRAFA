"""Wikipedia tool via REST API with disambiguation handling.

Responsibility:
    Fetch article summaries directly from Wikipedia REST API (no PyPI
    wikipedia package). Disambiguation pages never pass as real content.

Role in architecture:
    Tier 1 factual retrieval tool per config/DESIGN.md §6.
"""

from __future__ import annotations

import urllib.parse
from typing import Any, Optional

import httpx

from fixtures.loader import is_offline_mode, load_tool_fixture
from tools.base import Tool, ToolCitation, ToolResult
from tools.common import make_failure, make_success, title_overlap_score
from tools.policy import load_wikipedia_retry_policy

WIKI_REST_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
WIKI_API_SEARCH = "https://en.wikipedia.org/w/api.php"


class WikipediaTool(Tool):
    """Retrieve Wikipedia article summaries by title or search query.

    Description:
        Calls REST summary endpoint; on disambiguation pages falls back to
        the search API and picks the best title-overlap match. Logs which
        path was taken in ``reason``.

    Input:
        Query string (article title or search terms).

    Output:
        ``ToolResult`` with ``source_id`` like ``wikipedia:Discount_window``
        and ``citation`` ``{title, url_or_id}``.

    When to use:
        Factual single-source and background retrieval.

    When not to use:
        Current numeric data series (use FRED); academic papers (use arXiv).
    """

    name = "wikipedia"

    def __init__(self, policy=None) -> None:
        super().__init__(policy or load_wikipedia_retry_policy())

    def invoke(self, query: str, deadline: Optional[float] = None) -> ToolResult:
        """Fetch Wikipedia content for ``query`` without raising."""
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
        title = query.strip().replace(" ", "_")
        encoded = urllib.parse.quote(title, safe="/")
        url = WIKI_REST_SUMMARY.format(title=encoded)

        try:
            with httpx.Client(timeout=self.policy.timeout_s) as client:
                resp = client.get(url, headers={"User-Agent": "TitanRAFA-research-agent/1.0"})
        except httpx.TimeoutException:
            return (
                make_failure(self.name, query, "wikipedia request timed out", "timeout"),
                None,
            )
        except httpx.HTTPError as exc:
            return (
                make_failure(self.name, query, f"wikipedia http error: {exc}", "parse_error"),
                None,
            )

        retry_after = resp.headers.get("Retry-After") if resp.status_code == 429 else None

        if resp.status_code == 429:
            return (
                make_failure(self.name, query, "wikipedia rate limited (429)", "http_429"),
                retry_after,
            )
        if resp.status_code == 404:
            return self._search_fallback(query, client=None, path_note="direct_summary_404")
        if resp.status_code >= 500:
            return (
                make_failure(
                    self.name,
                    query,
                    f"wikipedia server error {resp.status_code}",
                    "parse_error",
                ),
                retry_after,
            )
        if resp.status_code != 200:
            return (
                make_failure(
                    self.name,
                    query,
                    f"wikipedia unexpected status {resp.status_code}",
                    "parse_error",
                ),
                retry_after,
            )

        try:
            payload = resp.json()
        except ValueError:
            return (
                make_failure(self.name, query, "wikipedia invalid JSON", "parse_error"),
                None,
            )

        if self._is_disambiguation(payload):
            return self._search_fallback(
                query,
                path_note="disambiguation_page_rejected",
            )

        return self._result_from_summary(payload, query, path_note="direct_summary"), None

    def _search_fallback(
        self,
        query: str,
        *,
        client: Optional[httpx.Client] = None,
        path_note: str,
    ) -> tuple[ToolResult, Optional[str]]:
        """Search Wikipedia and pick best title-overlap match."""
        params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "format": "json",
            "srlimit": 5,
        }
        own_client = client is None
        if own_client:
            client = httpx.Client(timeout=self.policy.timeout_s)

        assert client is not None
        try:
            resp = client.get(WIKI_API_SEARCH, params=params)
        except httpx.TimeoutException:
            return (
                make_failure(self.name, query, "wikipedia search timed out", "timeout"),
                None,
            )
        except httpx.HTTPError as exc:
            return (
                make_failure(self.name, query, f"wikipedia search error: {exc}", "parse_error"),
                None,
            )
        finally:
            if own_client:
                client.close()

        retry_after = resp.headers.get("Retry-After") if resp.status_code == 429 else None
        if resp.status_code == 429:
            return (
                make_failure(self.name, query, "wikipedia search rate limited", "http_429"),
                retry_after,
            )
        if resp.status_code != 200:
            return (
                make_failure(
                    self.name,
                    query,
                    f"wikipedia search status {resp.status_code}",
                    "parse_error",
                ),
                retry_after,
            )

        try:
            data = resp.json()
        except ValueError:
            return (
                make_failure(self.name, query, "wikipedia search invalid JSON", "parse_error"),
                None,
            )

        results = data.get("query", {}).get("search", [])
        if not results:
            return (
                make_failure(
                    self.name,
                    query,
                    f"wikipedia {path_note}: search returned no results",
                    "empty_result",
                ),
                None,
            )

        best = max(results, key=lambda r: title_overlap_score(query, r.get("title", "")))
        if title_overlap_score(query, best.get("title", "")) < 1:
            return (
                make_failure(
                    self.name,
                    query,
                    f"wikipedia {path_note}: no title overlap in search results",
                    "empty_result",
                ),
                None,
            )

        title = best["title"].replace(" ", "_")
        encoded = urllib.parse.quote(title, safe="/")
        summary_url = WIKI_REST_SUMMARY.format(title=encoded)
        try:
            with httpx.Client(timeout=self.policy.timeout_s) as sum_client:
                sum_resp = sum_client.get(
                    summary_url,
                    headers={"User-Agent": "TitanRAFA-research-agent/1.0"},
                )
        except httpx.TimeoutException:
            return (
                make_failure(self.name, query, "wikipedia summary timed out", "timeout"),
                None,
            )
        except httpx.HTTPError as exc:
            return (
                make_failure(self.name, query, f"wikipedia summary error: {exc}", "parse_error"),
                None,
            )

        if sum_resp.status_code != 200:
            return (
                make_failure(
                    self.name,
                    query,
                    f"wikipedia search_fallback summary status {sum_resp.status_code}",
                    "parse_error",
                ),
                None,
            )

        try:
            payload = sum_resp.json()
        except ValueError:
            return (
                make_failure(self.name, query, "wikipedia summary invalid JSON", "parse_error"),
                None,
            )

        if self._is_disambiguation(payload):
            return (
                make_failure(
                    self.name,
                    query,
                    f"wikipedia {path_note}: search pick still disambiguation",
                    "empty_result",
                ),
                None,
            )

        note = f"wikipedia path={path_note} search_pick={best['title']}"
        return self._result_from_summary(payload, query, path_note=note), None

    @staticmethod
    def _is_disambiguation(payload: dict[str, Any]) -> bool:
        page_type = str(payload.get("type", "")).lower()
        title = str(payload.get("title", "")).lower()
        return page_type == "disambiguation" or title.endswith("(disambiguation)")

    def _result_from_summary(
        self,
        payload: dict[str, Any],
        query: str,
        *,
        path_note: str,
    ) -> ToolResult:
        title = str(payload.get("title", ""))
        extract = str(payload.get("extract", "")).strip()
        if not extract:
            return make_failure(
                self.name,
                query,
                f"wikipedia {path_note}: empty extract",
                "empty_result",
            )

        page_key = str(payload.get("titles", {}).get("canonical", title)).lstrip("/")
        page_key = page_key.replace(" ", "_")
        source_id = f"wikipedia:{page_key}"
        content_url = str(payload.get("content_urls", {}).get("desktop", {}).get("page", ""))
        if not content_url:
            content_url = f"https://en.wikipedia.org/wiki/{urllib.parse.quote(page_key)}"

        citation = ToolCitation(title=title, url_or_id=content_url)
        return make_success(
            self.name,
            query,
            source_id,
            extract,
            citation,
            reason=f"wikipedia {path_note}",
        )
