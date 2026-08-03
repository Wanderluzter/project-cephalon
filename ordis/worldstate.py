"""
Worldstate adapter — api.warframestat.us

Stable, well-documented source for live game state: cycles, fissures,
sortie, nightwave, steel path, void trader, arbitration, invasions,
syndicate missions.

Docs:   https://docs.warframestat.us/
Spec:   https://github.com/WFCD/api-spec
Parser: https://github.com/WFCD/warframe-worldstate-parser (raw DE feed,
        only needed if you want to bypass this API entirely)
"""

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests

from .config import DEFAULT_CONFIG, OrdisConfig


class WorldstateError(RuntimeError):
    """Raised when the worldstate API returns an unexpected response."""


class Worldstate:
    # Endpoints that only change once a day (or slower) in-game — cached
    # for 24h so a dashboard polling every minute doesn't hammer the API
    # for data that hasn't moved. Everything else gets a short default TTL
    # just to de-duplicate rapid repeat calls, not to hide real changes.
    _DAILY_ENDPOINTS = {
        "cetus-cycle", "vallis-cycle", "cambion-cycle", "zariman-cycle",
        "duviri-cycle", "earth-cycle",
        "daily-deals", "flash-sales", "global-upgrades", "events", "alerts",
        "conclave-challenges", "archon-hunt", "archimedeas", "calendar",
        "weekly-challenges", "clan-weekly-initiative",
    }
    _TTL_DAILY = 24 * 3600
    _TTL_DEFAULT = 60

    def __init__(self, config: OrdisConfig = DEFAULT_CONFIG, platform: Optional[str] = None):
        self._config = config
        self._platform = platform or config.platform
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": config.user_agent})
        self._cache: Dict[str, Tuple[float, Any]] = {}

    def _get(self, path: str = "") -> Any:
        url = f"{self._config.worldstate_base}/{self._platform}"
        if path:
            url = f"{url}/{path.lstrip('/')}"
        try:
            resp = self._session.get(url, timeout=self._config.request_timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            raise WorldstateError(f"Worldstate request failed for {url}: {exc}") from exc

    # --- Full state -----------------------------------------------------
    def get_full_state(self) -> Dict[str, Any]:
        return self._get()

    # --- Server status ----------------------------------------------------
    # Platform codes confirmed from the original data-source reference this
    # project was built from: "Swap `pc` for `ps4`, `xb1`, or `switch` for
    # other platforms."
    PLATFORMS = ("pc", "ps4", "xb1", "switch")

    def check_platform_status(self, platforms: Optional[List[str]] = None, timeout: float = 5.0) -> Dict[str, Dict[str, Any]]:
        """Ping each platform's worldstate endpoint and measure latency.
        Uses a lightweight endpoint (simaris — small payload) rather than
        the full state dump, since this is meant to be a quick health
        check, not a data fetch."""
        platforms = platforms or list(self.PLATFORMS)
        results: Dict[str, Dict[str, Any]] = {}
        for platform in platforms:
            url = f"{self._config.worldstate_base}/{platform}/simaris"
            start = time.monotonic()
            try:
                resp = self._session.get(url, timeout=timeout)
                resp.raise_for_status()
                latency_ms = round((time.monotonic() - start) * 1000, 1)
                results[platform] = {"status": "up", "latency_ms": latency_ms}
            except requests.RequestException as exc:
                results[platform] = {"status": "down", "error": str(exc)}
        return results

    # --- Individual endpoints --------------------------------------------
    def get_fissures(self) -> List[Dict[str, Any]]:
        return self._get("fissures")

    def get_sortie(self) -> Dict[str, Any]:
        return self._get("sortie")

    def get_nightwave(self) -> Dict[str, Any]:
        return self._get("nightwave")

    def get_steel_path(self) -> Dict[str, Any]:
        return self._get("steelPath")

    def get_void_trader(self) -> Dict[str, Any]:
        return self._get("voidTrader")

    def get_arbitration(self) -> Dict[str, Any]:
        return self._get("arbitration")

    def get_invasions(self) -> List[Dict[str, Any]]:
        return self._get("invasions")

    def get_syndicate_missions(self) -> List[Dict[str, Any]]:
        return self._get("syndicateMissions")

    # --- Open-world cycles (hourly/rotating) --------------------------------
    def get_cetus_cycle(self) -> Dict[str, Any]:
        """Day/night cycle on Earth (Cetus/Plains of Eidolon)."""
        return self._get("cetusCycle")

    def get_vallis_cycle(self) -> Dict[str, Any]:
        """Warm/cold cycle on Venus (Orb Vallis)."""
        return self._get("vallisCycle")

    def get_cambion_cycle(self) -> Dict[str, Any]:
        """Fass/Vome cycle on Deimos (Cambion Drift)."""
        return self._get("cambionCycle")

    def get_zariman_cycle(self) -> Dict[str, Any]:
        """Corpus/Grineer cycle on the Zariman."""
        return self._get("zarimanCycle")

    def get_duviri_cycle(self) -> Dict[str, Any]:
        """Current mood/weather rotation in Duviri."""
        return self._get("duviriCycle")

    def get_earth_cycle(self) -> Dict[str, Any]:
        """Day/night cycle for the regular Earth tileset (separate from
        the Cetus cycle)."""
        return self._get("earthCycle")

    # --- Daily / weekly-ish rotating content ---------------------------------
    def get_daily_deals(self) -> List[Dict[str, Any]]:
        """Darvo's daily deal(s)."""
        return self._get("dailyDeals")

    def get_flash_sales(self) -> List[Dict[str, Any]]:
        return self._get("flashSales")

    def get_global_upgrades(self) -> List[Dict[str, Any]]:
        """Active double-XP / resource-booster style global upgrades."""
        return self._get("globalUpgrades")

    def get_events(self) -> List[Dict[str, Any]]:
        """Active in-game operations/events (score-based events, etc)."""
        return self._get("events")

    def get_alerts(self) -> List[Dict[str, Any]]:
        """Legacy alert system — usually empty in current game versions but
        kept for completeness."""
        return self._get("alerts")

    def get_dark_sectors(self) -> List[Dict[str, Any]]:
        return self._get("darkSectors")

    def get_conclave_challenges(self) -> List[Dict[str, Any]]:
        return self._get("conclaveChallenges")

    # --- World/persistent entities ------------------------------------------
    def get_persistent_enemies(self) -> List[Dict[str, Any]]:
        """Currently-spawned Kuva Liches / Sisters of Parvos."""
        return self._get("persistentEnemies")

    def get_sentient_outposts(self) -> Dict[str, Any]:
        return self._get("sentientOutposts")

    def get_simaris(self) -> Dict[str, Any]:
        """Simaris' current synthesis target."""
        return self._get("simaris")

    def get_news(self) -> List[Dict[str, Any]]:
        return self._get("news")

    def get_kinepage(self) -> Dict[str, Any]:
        """Netracell / Kinepage rotating info."""
        return self._get("kinepage")

    def get_vault_trader(self) -> Dict[str, Any]:
        """Prime Vault trader rotation (distinct from Baro's voidTrader)."""
        return self._get("vaultTrader")

    def get_archon_hunt(self) -> Dict[str, Any]:
        """Weekly Archon Hunt (three linked missions vs. an Archon boss)."""
        return self._get("archonHunt")

    def get_archimedeas(self) -> List[Dict[str, Any]]:
        """Deep Archimedea / Temporal Archimedea weekly modes. CONFIRMED
        present in a live fetch as `archimedeas` — each entry has a `type`
        key distinguishing the variant, plus `missions` with deviations and
        risks."""
        return self._get("archimedeas")

    def get_calendar(self) -> Dict[str, Any]:
        """The 1999 Calendar (Höllvania/Hex faction reward system — 'KIM'
        rewards, seasonal to-dos, Hex Overrides, birthdays). CONFIRMED real
        via the official OpenAPI spec (schema `CalendarDto`) — this is what
        was missing when 'the 1999/Hex weekly rewards' were requested."""
        return self._get("calendar")

    def get_weekly_challenges(self) -> Dict[str, Any]:
        """CONFIRMED real endpoint (schema `WeeklyChallengeDto`) that
        wasn't wired into this app before."""
        return self._get("weeklyChallenges")

    def get_clan_weekly_initiative(self) -> Dict[str, Any]:
        """Clan Weekly Initiative rewards. CONFIRMED real endpoint that
        wasn't wired into this app before."""
        return self._get("clanWeeklyInitiative")

    def get_kuva_missions(self) -> List[Dict[str, Any]]:
        """Active Kuva Siphon/Flood missions."""
        return self._get("kuva")

    # --- Generic dispatch ---------------------------------------------------
    # Single source of truth for "which hyphenated endpoint name maps to
    # which method" — used by both the Flask routes in app.py and the chat
    # agent's tool schema, so they can't drift out of sync with each other.
    ENDPOINTS = {
        "sortie": "get_sortie",
        "nightwave": "get_nightwave",
        "fissures": "get_fissures",
        "steel-path": "get_steel_path",
        "void-trader": "get_void_trader",
        "vault-trader": "get_vault_trader",
        "arbitration": "get_arbitration",
        "invasions": "get_invasions",
        "syndicate-missions": "get_syndicate_missions",
        "cetus-cycle": "get_cetus_cycle",
        "vallis-cycle": "get_vallis_cycle",
        "cambion-cycle": "get_cambion_cycle",
        "zariman-cycle": "get_zariman_cycle",
        "duviri-cycle": "get_duviri_cycle",
        "earth-cycle": "get_earth_cycle",
        "daily-deals": "get_daily_deals",
        "flash-sales": "get_flash_sales",
        "global-upgrades": "get_global_upgrades",
        "events": "get_events",
        "alerts": "get_alerts",
        "dark-sectors": "get_dark_sectors",
        "conclave-challenges": "get_conclave_challenges",
        "persistent-enemies": "get_persistent_enemies",
        "sentient-outposts": "get_sentient_outposts",
        "simaris": "get_simaris",
        "news": "get_news",
        "kinepage": "get_kinepage",
        "archon-hunt": "get_archon_hunt",
        "archimedeas": "get_archimedeas",
        "calendar": "get_calendar",
        "weekly-challenges": "get_weekly_challenges",
        "clan-weekly-initiative": "get_clan_weekly_initiative",
        "kuva": "get_kuva_missions",
    }

    def call(self, endpoint: str, force_refresh: bool = False) -> Any:
        method_name = self.ENDPOINTS.get(endpoint)
        if not method_name:
            raise WorldstateError(
                f"Unknown worldstate endpoint '{endpoint}'. Valid options: {sorted(self.ENDPOINTS)}"
            )

        ttl = self._TTL_DAILY if endpoint in self._DAILY_ENDPOINTS else self._TTL_DEFAULT
        now = time.monotonic()
        cached = self._cache.get(endpoint)
        if cached is not None and not force_refresh and (now - cached[0]) < ttl:
            if self._payload_still_valid(cached[1]):
                return cached[1]
            # Cached within TTL, but the payload's own `expiry` timestamp
            # has already passed — e.g. a cycle (cetus-cycle etc.) cached
            # for up to 24h that has since flipped to its next state.
            # Without this check, a 24h cache TTL would silently keep
            # serving an already-expired state, which defeats client-side
            # countdown timers that are supposed to refresh once they hit
            # zero. Falling through to a real fetch below.

        data = getattr(self, method_name)()
        self._cache[endpoint] = (now, data)
        return data

    @staticmethod
    def _payload_still_valid(payload: Any) -> bool:
        """True unless `payload` is a dict with an `expiry` timestamp
        that's already in the past. Non-dict payloads (lists, etc.) and
        dicts without an `expiry` field are always considered valid —
        this only guards the single-object endpoints (cycles, sortie,
        etc.) that carry their own expiry."""
        if not isinstance(payload, dict):
            return True
        expiry = payload.get("expiry")
        if not expiry:
            return True
        try:
            expiry_dt = datetime.fromisoformat(str(expiry).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return True  # can't parse — don't force-invalidate on a guess
        return expiry_dt > datetime.now(timezone.utc)


if __name__ == "__main__":
    ws = Worldstate()
    print(ws.get_sortie())
