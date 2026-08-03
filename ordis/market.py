"""
Warframe Market adapter — v2 API

Warframe Market v1 (api.warframe.market/v1) is DEPRECATED. New docs are not
being published for it. This module targets v2 exclusively.

v2 is pre-1.0 (currently documented at v0.25.0) and can introduce breaking
changes while it stabilizes. Everything version-specific is deliberately
kept inside this one file — every ORDIS tool should call the methods below,
never hit warframe.market URLs directly — so an upstream breaking change
means patching this module, not every caller.

IMPORTANT — confirmed against the live API: `/items` has NO server-side
search/filter parameter in either v1 or v2. It only ever returns the full
item catalog. search_item() fetches and caches that catalog once, then
filters client-side. Passing a 'search' query param (as an earlier version
of this file did) is silently ignored by the server, which looked like
broken/random results rather than an error.

Docs: https://docs.warframe.market/
  - Manifests & Collections: https://docs.warframe.market/docs/api/manifests
  - Orders:                  https://docs.warframe.market/docs/api/orders
  - Groups:                  https://docs.warframe.market/docs/api/groups
  - Users:                   https://docs.warframe.market/docs/api/users
  - Achievements:            https://docs.warframe.market/docs/api/achievements
  - Authentication:          https://docs.warframe.market/docs/api/authentication
  - Dashboard:                https://docs.warframe.market/docs/api/dashboard
  - WebSockets:               https://docs.warframe.market/docs/websockets/overview

NOTE on auth: OAuth 2.0 for third-party clients is NOT yet available in v2.
Any authenticated action (placing/editing orders, etc.) still has to go
through the legacy v1 auth flow for now. `place_order()` below is stubbed
and raises NotImplementedError until that's wired up, so it fails loudly
instead of silently doing nothing.

NOTE on price history: v2 has NO price-statistics/history endpoint —
checked its docs directly (Manifests, Orders, Groups, Users, Achievements,
Auth, Dashboard is the complete list; "Dashboard" is just mobile-app
featured-items content, not price stats). `get_price_history()` below is a
DELIBERATE EXCEPTION targeting v1's `/items/{slug}/statistics`, same
isolation approach as riven.py — confirmed the path exists via a community
Kotlin wrapper's full v1 endpoint list. The parsed response shape
(`statistics_closed.90days` daily buckets with avg/median/min/max/volume)
comes from the long-documented, stable v1 schema, not a live sample I
fetched myself this session — parsing is defensive.

Legacy v1 spec, reference only — do not build new code against it:
https://github.com/WFCD/market-api-spec

Community client libraries, if you'd rather not hand-roll this:
  Rust:   https://crates.io/crates/wf-market
  Python: https://github.com/leonardodalinky/pywmapi
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests

from .config import DEFAULT_CONFIG, OrdisConfig


class MarketError(RuntimeError):
    """Raised when the Warframe Market v2 API returns an unexpected response."""


@dataclass
class MarketOrder:
    item_slug: str
    platinum: int
    quantity: int
    order_type: str  # "sell" | "buy"
    user_status: Optional[str]
    seller_name: Optional[str]
    raw: Dict[str, Any]


@dataclass
class PricePoint:
    date: str
    avg_price: Optional[float]
    median: Optional[float]
    min_price: Optional[float]
    max_price: Optional[float]
    volume: Optional[int]


class Market:
    def __init__(self, config: OrdisConfig = DEFAULT_CONFIG):
        self._config = config
        self._item_catalog: Optional[List[Dict[str, Any]]] = None
        self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": config.user_agent,
                "Accept": "application/json",
                # v2 expects a Platform/Language header on most routes;
                # confirm current header names against the live docs before
                # shipping, since this API is still pre-1.0.
                "Platform": "pc",
                "Language": "en",
            }
        )

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        url = f"{self._config.market_base}/{path.lstrip('/')}"
        try:
            resp = self._session.get(url, params=params, timeout=self._config.request_timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            raise MarketError(
                f"Market v2 request failed for {url}: {exc}. "
                f"v2 is pre-1.0 (see {self._config.market_docs}) — verify the "
                f"endpoint/response shape hasn't changed."
            ) from exc

    def _get_v1(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """v1-only requests — currently just get_price_history(). See the
        module docstring for why this exception exists."""
        url = f"{self._config.market_v1_base}/{path.lstrip('/')}"
        try:
            resp = self._session.get(url, params=params, timeout=self._config.request_timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            raise MarketError(f"Market v1 request failed for {url}: {exc}") from exc

    def get_price_history(self, item_slug: str, days: int = 14) -> List[PricePoint]:
        """Daily sell-price history for an item over the last `days` days.

        Targets v1 (see module docstring — v2 has no equivalent). Response
        shape is `payload.statistics_closed.90days`, a list of daily
        aggregate buckets tagged by order_type; parsing is defensive since
        I haven't confirmed this against a live call from this environment.
        """
        data = self._get_v1(f"items/{item_slug}/statistics")
        payload = data.get("payload", {}) if isinstance(data, dict) else {}
        closed = payload.get("statistics_closed", {})
        daily = closed.get("90days") or closed.get("48hours") or []
        if not isinstance(daily, list):
            return []

        points = []
        for entry in daily:
            if entry.get("order_type") not in (None, "sell"):
                continue  # only want sell-side history, same principle as get_price()
            points.append(
                PricePoint(
                    date=entry.get("datetime", ""),
                    avg_price=entry.get("avg_price"),
                    median=entry.get("median"),
                    min_price=entry.get("min_price"),
                    max_price=entry.get("max_price"),
                    volume=entry.get("volume"),
                )
            )
        points.sort(key=lambda p: p.date, reverse=True)
        return points[:days]

    # --- Manifests / item lookup ------------------------------------------
    def _load_item_catalog(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Fetch and cache the full tradable item catalog (~3-4k items).

        Confirmed against the v1 spec (https://github.com/WFCD/market-api-spec)
        and every v2 client library surveyed (Rust `wf-market`, Python
        `pywmapi`/`warframe-market.py`): the `/items` endpoint has NO
        server-side search or filter parameter, in either API version — it
        only ever returns the complete catalog. A `search=` query param is
        silently ignored, which is why an earlier version of this method
        appeared to return unrelated items instead of erroring.

        So: fetch the whole list once, cache it in memory, and filter
        client-side. The catalog only changes on game updates, so caching
        is safe — call with force_refresh=True to bust it if needed.
        """
        if self._item_catalog is not None and not force_refresh:
            return self._item_catalog
        data = self._get("items")
        items = data.get("data", data) if isinstance(data, dict) else data
        if not isinstance(items, list):
            items = []
        for item in items:
            en = (item.get("i18n") or {}).get("en") or {}
            item["display_name"] = en.get("name")
            icon_path = en.get("icon")
            item["icon_path"] = icon_path  # raw relative path, e.g. "items/images/en/xxx.png"
            # Best-effort URL — see market_image_base caveat in config.py.
            item["image_url"] = f"{self._config.market_image_base}/{icon_path}" if icon_path else None
        self._item_catalog = items
        return items

    def search_item(self, name: str) -> List[Dict[str, Any]]:
        """Case-insensitive substring search over the cached item catalog
        (name or slug). See _load_item_catalog() for why this is filtered
        client-side rather than via a query param."""
        needle = name.lower().strip()
        if not needle:
            return []
        catalog = self._load_item_catalog()
        return [
            item
            for item in catalog
            if needle in (item.get("display_name") or "").lower()
            or needle in (item.get("slug") or "").lower()
        ]

    # --- Orders -------------------------------------------------------------
    def get_price(self, item_slug: str, order_type: Optional[str] = "sell") -> List[MarketOrder]:
        """Return current live orders for an item slug (e.g. 'ash_prime_set'),
        filtered to `order_type` ('sell' or 'buy'), or unfiltered if None.

        CONFIRMED BUG FIX: an earlier version of this method requested
        orders with a query param, then labeled every single returned
        order with that requested type unconditionally — it never checked
        what type each order actually was. Cross-referenced three
        independent v2 client implementations (the community
        `warframe_market` Rust crate's `PostOrder { r#type: Type::Sell }`,
        `wfm.py`'s parsed Order objects, and the v1->v2 field rename) to
        confirm: v2 orders carry their real type under the field `type`
        (v1 used `order_type`), and `/orders/item/{slug}` returns BOTH buy
        and sell orders together — same "no server-side filtering, filter
        client-side" pattern already confirmed for `/items` in
        _load_item_catalog(). Trusting the request param instead of the
        real per-order field meant buy orders (near-universally priced
        around 1 platinum, since buyers lowball) were silently counted as
        "sell" orders, which is why lowest_sell_price() was returning ~1p
        for nearly everything regardless of item.
        """
        data = self._get(f"orders/item/{item_slug}")
        orders_raw = data.get("data", []) if isinstance(data, dict) else data
        if not isinstance(orders_raw, list):
            orders_raw = []
        orders = []
        for o in orders_raw:
            real_type = o.get("type") or o.get("order_type")  # tolerate either field name
            if order_type is not None and real_type != order_type:
                continue
            quantity = o.get("quantity", 1)
            if quantity is not None and quantity <= 0:
                continue  # sold out / not actually available right now
            user = o.get("user") or {}
            # NOTE: I could not confirm the exact v2 username field from a
            # raw payload (only post-processed wrapper libraries surfaced
            # it, normalized to a plain "user" string) — a community Rust
            # crate example shows `order.user.ingame_name` working, which
            # is why that's tried first, but if sellers are showing up
            # nameless in practice, this guess may still be wrong for your
            # region/platform. Trying every plausible field name rather
            # than betting on one:
            seller_name = (
                user.get("ingame_name")
                or user.get("username")
                or user.get("displayName")
                or user.get("display_name")
                or user.get("name")
            )
            if not seller_name:
                # Fall back to a short id fragment so sellers are at least
                # distinguishable from each other, instead of a generic
                # "unknown seller" that hides real data (a user id) we do
                # have.
                uid = user.get("id") or user.get("user_id")
                seller_name = f"seller-{str(uid)[:8]}" if uid else None
            orders.append(
                MarketOrder(
                    item_slug=item_slug,
                    platinum=o.get("platinum", 0),
                    quantity=quantity,
                    order_type=real_type or "unknown",
                    user_status=user.get("status"),
                    seller_name=seller_name,
                    raw=o,
                )
            )
        return orders

    def top_sellers(self, item_slug: str, limit: int = 10, online_only: bool = False) -> List[MarketOrder]:
        """Top N live sell orders for an item, cheapest first."""
        orders = self.get_price(item_slug, order_type="sell")
        if online_only:
            orders = [o for o in orders if o.user_status in ("ingame", "online")]
        return sorted(orders, key=lambda o: o.platinum)[:limit]

    def lowest_sell_price(self, item_slug: str, online_only: bool = True) -> Optional[int]:
        orders = self.get_price(item_slug, order_type="sell")
        if online_only:
            orders = [o for o in orders if o.user_status in ("ingame", "online")]
        if not orders:
            return None
        return min(o.platinum for o in orders)

    # --- Write actions (require auth — legacy v1 flow for now) --------------
    def place_order(self, *args, **kwargs):
        raise NotImplementedError(
            "Authenticated write actions aren't supported yet: Market v2 has no "
            "third-party OAuth flow as of this build. Placing orders currently "
            "requires the legacy v1 auth flow — wire that up separately if/when "
            "this feature is needed, and don't route it through this adapter's "
            "v2 session."
        )


if __name__ == "__main__":
    m = Market()
    hits = m.search_item("ash prime")
    print(hits[:3] if isinstance(hits, list) else hits)
