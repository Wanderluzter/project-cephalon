"""
Riven & Kuva Lich adapter — Warframe Market v1 Auctions.

DELIBERATE EXCEPTION to this project's "prefer v2" rule: v2's own
documentation (docs.warframe.market) currently lists NO Auctions or
Rivens section at all — only Manifests, Orders, Groups, Users,
Achievements, Auth, Dashboard. Riven mod AND Kuva Lich/Sister of Parvos
trading both live on the same v1 `/auctions/search` endpoint (confirmed —
the site's own lich search URL is `/auctions/search?type=lich&...`, same
family as `type=riven`), and there's no v2 equivalent to migrate to yet.
This module is isolated exactly like market.py so that whenever v2 does
ship auction support, only this one file needs to change.

CAVEAT ON RESPONSE SHAPE: I could not make a live call to
api.warframe.market from this environment to confirm the exact current
auction JSON shape for either type. The Riven fields (item.weapon_url_name,
item.positive_stats, item.negative_stats, item.polarity, item.mod_rank,
item.mastery_level, item.re_rolls, buyout_price, starting_price, owner,
is_direct_sell) come from the long-documented, historically stable v1
riven auction schema used consistently across multiple independent
community tools for years. The Lich fields (element, having_ephemera,
quirks, damage) are inferred from the site's own lich search query
parameters, not a fetched response body, so treat those as a rougher
guess than the Riven fields. Parsing is defensive (.get() everywhere) so
a shape drift degrades gracefully instead of crashing.

NOT IMPLEMENTED — checked and deliberately skipped: DE's own "Weekly
Riven Mods Trade Data" feed (weeklyRivensPC.json) looked like a promising
supplementary data source, but the Warframe Wiki's own Riven Mods article
states it hasn't been updated since 13 May 2024 — over two years stale as
of this writing. Wiring it in would mean silently serving old data
labeled as "weekly." Also skipped: DE's "Annual Warframe and Weapon Usage
Data" feed — the most recent confirmed file is from 2023, with nothing
found for 2024-2026 despite the "annual" cadence, so its freshness is
unverified too.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests

from .config import DEFAULT_CONFIG, OrdisConfig


class RivenError(RuntimeError):
    """Raised when the auction API returns an unexpected response."""


@dataclass
class RivenAuction:
    auction_id: str
    weapon: Optional[str]
    weapon_url_name: Optional[str]
    positive_stats: List[Dict[str, Any]]
    negative_stat: Optional[Dict[str, Any]]
    polarity: Optional[str]
    mod_rank: Optional[int]
    mastery_level: Optional[int]
    re_rolls: Optional[int]
    starting_price: Optional[int]
    buyout_price: Optional[int]
    is_direct_sell: bool
    seller_name: Optional[str]
    seller_status: Optional[str]
    raw: Dict[str, Any]


@dataclass
class LichAuction:
    auction_id: str
    weapon: Optional[str]
    weapon_url_name: Optional[str]
    element: Optional[str]
    has_ephemera: bool
    ephemera: Optional[str]
    quirks: List[str]
    damage: Optional[float]
    starting_price: Optional[int]
    buyout_price: Optional[int]
    is_direct_sell: bool
    seller_name: Optional[str]
    seller_status: Optional[str]
    raw: Dict[str, Any]


class Riven:
    def __init__(self, config: OrdisConfig = DEFAULT_CONFIG):
        self._config = config
        self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": config.user_agent,
                "Accept": "application/json",
                "Platform": "pc",
                "Language": "en",
            }
        )

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        url = f"{self._config.market_v1_base}/{path.lstrip('/')}"
        try:
            resp = self._session.get(url, params=params, timeout=self._config.request_timeout)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            raise RivenError(f"Riven auction request failed for {url}: {exc}") from exc
        return data

    def search(
        self,
        weapon_url_name: Optional[str] = None,
        positive_stats: Optional[List[str]] = None,
        negative_stats: Optional[List[str]] = None,
        polarity: Optional[str] = None,
        mastery_rank_min: Optional[int] = None,
        mastery_rank_max: Optional[int] = None,
        re_rolls_min: Optional[int] = None,
        re_rolls_max: Optional[int] = None,
        buyout_policy: Optional[str] = None,  # "direct" | "with_buyout" | None
        sort_by: str = "price_asc",
        limit: int = 20,
    ) -> List[RivenAuction]:
        """Search live riven auctions. `weapon_url_name` is the WFM slug
        for the weapon (e.g. 'braton_prime', 'war') — use market.py's
        search_item()/catalog to resolve a display name to a slug first if
        needed; riven weapon slugs generally match weapon item slugs.

        FIX (confirmed via live testing): the v1 spec lists `platform` as
        a required search parameter — sending it only as a `Platform`
        header (as this module originally did) causes a 400 Bad Request.
        It must also be sent as an explicit query param.
        """
        params: Dict[str, Any] = {"type": "riven", "sort_by": sort_by, "platform": "pc"}
        if weapon_url_name:
            params["weapon_url_name"] = weapon_url_name
        if positive_stats:
            params["positive_stats"] = ",".join(positive_stats)
        if negative_stats:
            params["negative_stats"] = ",".join(negative_stats)
        if polarity:
            params["polarity"] = polarity
        if mastery_rank_min is not None:
            params["mastery_rank_min"] = mastery_rank_min
        if mastery_rank_max is not None:
            params["mastery_rank_max"] = mastery_rank_max
        if re_rolls_min is not None:
            params["re_rolls_min"] = re_rolls_min
        if re_rolls_max is not None:
            params["re_rolls_max"] = re_rolls_max
        if buyout_policy:
            params["buyout_policy"] = buyout_policy

        data = self._get("auctions/search", params=params)
        entries = data.get("payload", {}).get("auctions", []) if isinstance(data, dict) else data
        if not isinstance(entries, list):
            entries = []

        auctions = []
        for a in entries[:limit]:
            item = a.get("item") or {}
            owner = a.get("owner") or {}
            positive = item.get("positive_stats") or []
            negative = item.get("negative_stats")
            negative_single = negative[0] if isinstance(negative, list) and negative else negative
            auctions.append(
                RivenAuction(
                    auction_id=a.get("id", ""),
                    weapon=item.get("name") or item.get("weapon_url_name"),
                    weapon_url_name=item.get("weapon_url_name"),
                    positive_stats=positive,
                    negative_stat=negative_single,
                    polarity=item.get("polarity"),
                    mod_rank=item.get("mod_rank"),
                    mastery_level=item.get("mastery_level"),
                    re_rolls=item.get("re_rolls"),
                    starting_price=a.get("starting_price"),
                    buyout_price=a.get("buyout_price"),
                    is_direct_sell=bool(a.get("is_direct_sell")),
                    seller_name=owner.get("ingame_name"),
                    seller_status=owner.get("status"),
                    raw=a,
                )
            )
        return auctions

    def search_liches(
        self,
        weapon_url_name: Optional[str] = None,
        element: Optional[str] = None,
        having_ephemera: Optional[bool] = None,
        buyout_policy: Optional[str] = None,
        sort_by: str = "price_asc",
        limit: int = 20,
    ) -> List[LichAuction]:
        """Search live Kuva Lich / Sister of Parvos weapon auctions.
        Same v1 auctions endpoint as riven search(), type='lich' instead.
        `element` is the elemental damage type (e.g. 'toxin', 'electricity',
        'heat', 'cold', 'blast', 'radiation', 'viral', 'corrosive',
        'magnetic', 'gas')."""
        params: Dict[str, Any] = {"type": "lich", "sort_by": sort_by, "platform": "pc"}
        if weapon_url_name:
            params["weapon_url_name"] = weapon_url_name
        if element:
            params["element"] = element
        if having_ephemera is not None:
            params["having_ephemera"] = "true" if having_ephemera else "false"
        if buyout_policy:
            params["buyout_policy"] = buyout_policy

        data = self._get("auctions/search", params=params)
        entries = data.get("payload", {}).get("auctions", []) if isinstance(data, dict) else data
        if not isinstance(entries, list):
            entries = []

        auctions = []
        for a in entries[:limit]:
            item = a.get("item") or {}
            owner = a.get("owner") or {}
            quirks = item.get("quirks") or []
            if isinstance(quirks, str):
                quirks = [quirks]
            auctions.append(
                LichAuction(
                    auction_id=a.get("id", ""),
                    weapon=item.get("name") or item.get("weapon_url_name"),
                    weapon_url_name=item.get("weapon_url_name"),
                    element=item.get("element"),
                    has_ephemera=bool(item.get("ephemera") or item.get("having_ephemera")),
                    ephemera=item.get("ephemera"),
                    quirks=quirks,
                    damage=item.get("damage"),
                    starting_price=a.get("starting_price"),
                    buyout_price=a.get("buyout_price"),
                    is_direct_sell=bool(a.get("is_direct_sell")),
                    seller_name=owner.get("ingame_name"),
                    seller_status=owner.get("status"),
                    raw=a,
                )
            )
        return auctions


if __name__ == "__main__":
    r = Riven()
    for auc in r.search(weapon_url_name="war", limit=5):
        print(auc)
    for lich in r.search_liches(having_ephemera=True, limit=5):
        print(lich)
