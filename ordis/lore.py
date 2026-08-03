"""
Lore adapter — Warframe Wiki (wiki.warframe.com)

Two tiers of content:
  - get_summary(topic): REST summary endpoint. Short prose, ideal for
    something Ordis would actually say out loud as a voice line.
  - get_page(topic): full MediaWiki `parse` endpoint. Wikitext or rendered
    HTML, for when a caller wants the whole article.

"Story and History" is a normal wiki page (Story_and_History), not a
separate API — fetch it with get_page("Story_and_History") like any other
topic.
"""

from typing import Any, Dict, List, Optional

import requests

from .config import DEFAULT_CONFIG, OrdisConfig


class LoreError(RuntimeError):
    """Raised when the wiki API returns an unexpected response."""


class Lore:
    def __init__(self, config: OrdisConfig = DEFAULT_CONFIG):
        self._config = config
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": config.user_agent})

    def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """MediaWiki search — use this to resolve a fuzzy topic name to an
        exact page title before calling get_page/get_summary."""
        params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": limit,
            "format": "json",
        }
        try:
            resp = self._session.get(
                self._config.wiki_api_base, params=params, timeout=self._config.request_timeout
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            raise LoreError(f"Wiki search failed for '{query}': {exc}") from exc
        return data.get("query", {}).get("search", [])

    def get_summary(self, page_title: str) -> Optional[str]:
        """Short, voice-line-length summary — best default for an in-chat
        Ordis response.

        Tries the REST summary endpoint first. If that comes back without
        an `extract` (seen in practice — the endpoint can 200 with an empty
        or missing extract for some titles, likely a redirect/disambig
        case), falls back to the MediaWiki TextExtracts API
        (action=query&prop=extracts), which is more forgiving about title
        matching. Returns None only if both fail.
        """
        extract = self._rest_summary(page_title)
        if extract:
            return extract
        return self._query_extract(page_title)

    def _rest_summary(self, page_title: str) -> Optional[str]:
        url = f"{self._config.wiki_rest_base}/page/summary/{page_title.replace(' ', '_')}"
        try:
            resp = self._session.get(url, timeout=self._config.request_timeout)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError):
            return None
        return data.get("extract") or None

    def _query_extract(self, page_title: str) -> Optional[str]:
        """Fallback via the standard MediaWiki TextExtracts API. More
        tolerant of redirects than the REST summary endpoint."""
        params = {
            "action": "query",
            "prop": "extracts",
            "exintro": 1,
            "explaintext": 1,
            "redirects": 1,
            "titles": page_title,
            "format": "json",
        }
        try:
            resp = self._session.get(
                self._config.wiki_api_base, params=params, timeout=self._config.request_timeout
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            raise LoreError(f"Wiki extract fallback failed for '{page_title}': {exc}") from exc
        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            extract = page.get("extract")
            if extract:
                return extract.strip()
        return None

    def get_page(self, page_title: str, form: str = "wikitext") -> Optional[str]:
        """Full article content. form='wikitext' (raw markup) or
        form='text' (rendered HTML). Use page_title='Story_and_History'
        for the lore overview page."""
        prop = "wikitext" if form == "wikitext" else "text"
        params = {
            "action": "parse",
            "page": page_title,
            "prop": prop,
            "format": "json",
        }
        try:
            resp = self._session.get(
                self._config.wiki_api_base, params=params, timeout=self._config.request_timeout
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            raise LoreError(f"Wiki page fetch failed for '{page_title}': {exc}") from exc
        if "error" in data:
            return None
        return data.get("parse", {}).get(prop, {}).get("*")


if __name__ == "__main__":
    lore = Lore()
    print(lore.get_summary("Rhino"))
