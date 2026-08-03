"""
Central configuration for every ORDIS data adapter.

Keeping base URLs here (instead of scattered across modules) means a source
migration - e.g. Warframe Market's v1 -> v2 cutover - is a one-line change.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class OrdisConfig:
    # 1. Worldstate
    worldstate_base: str = "https://api.warframestat.us"
    platform: str = "pc"  # pc | ps4 | xb1 | switch

    # 2. Drop tables
    drops_base: str = "https://drops.warframestat.us/data"

    # 3. Warframe Market (v2 — v1 is deprecated, do not point this at
    # api.warframe.market/v1 for new code)
    market_base: str = "https://api.warframe.market/v2"
    market_docs: str = "https://docs.warframe.market/"
    # URL to prefix WFM's own relative icon paths (catalog items carry
    # i18n.en.icon like "items/images/en/secura_dual_cestra....png").
    # CONFIRMED (upgraded from an earlier unverified guess) via an
    # independent, actively-maintained npm package (`warframe-nexus-query`,
    # explicitly supporting v2, updated as recently as April 2026) whose
    # own real example output shows
    # `thumbnail: { url: 'https://warframe.market/static/assets/...' }` —
    # matches this value exactly. Still not something I fetched myself
    # live from this sandbox, so the frontend keeps its onerror fallback
    # regardless.
    market_image_base: str = "https://warframe.market/static/assets"

    # 3b. Warframe Market Rivens/Auctions — DELIBERATE EXCEPTION to "prefer
    # v2": as of this writing, v2's own docs (docs.warframe.market) list
    # NO Auctions or Rivens section at all — only Manifests, Orders,
    # Groups, Users, Achievements, Auth, Dashboard. Riven auction trading
    # has been on the stable, long-unchanged v1 API for years and there is
    # no v2 equivalent yet, so riven.py targets v1 specifically for this
    # one feature. Swap to v2 the moment it ships an equivalent.
    market_v1_base: str = "https://api.warframe.market/v1"

    # 4. Lore — Warframe Wiki
    wiki_api_base: str = "https://wiki.warframe.com/api.php"
    wiki_rest_base: str = "https://wiki.warframe.com/api/rest_v1"

    # 5. Builds — no official Overframe API; this is a placeholder only,
    # left here so the module has one obvious place to point if/when an
    # official or stable scraping target exists.
    overframe_base: str = "https://overframe.gg"

    # 6. Chat agent — OpenRouter (OpenAI-compatible chat + tool calling)
    # API key comes from the OPENROUTER_API_KEY env var, never hardcoded
    # here. Model is overridable via OPENROUTER_MODEL; pick any model slug
    # OpenRouter currently serves (check https://openrouter.ai/models —
    # their catalog changes over time, so this default may need updating).
    openrouter_base: str = "https://openrouter.ai/api/v1"
    openrouter_default_model: str = "openai/gpt-4o-mini"

    request_timeout: float = 10.0
    user_agent: str = "ProjectORDIS/0.1 (+https://github.com/your-org/ordis)"


DEFAULT_CONFIG = OrdisConfig()
