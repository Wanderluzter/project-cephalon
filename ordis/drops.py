"""
Drop table adapter — drops.warframestat.us

IMPORTANT: this is NOT a flat array of records. It's a single JSON object
keyed by table type (missionRewards, relics, cetusBountyRewards,
keyRewards, modLocations, ...). Confirmed against a live fetch:

- missionRewards is nested: {planet: {missionNode: {gameMode, isEvent,
  rewards}}}. `rewards` is itself irregular — a dict keyed by rotation
  ("A"/"B"/"C") for multi-rotation mission types (Survival, Defense,
  Excavation, ...), but a plain flat list for single-reward types
  (Capture, Assassination, Exterminate, ...). Both are handled.
- Reward entries use the field "itemName" (not "item" as some docs claim).

Shapes differ per table, so find_drop() builds a normalized in-memory index
once (at construction or on refresh()) instead of re-scanning the full
~20MB dump on every lookup. Table shapes we haven't explicitly verified are
indexed best-effort and skipped (not crashed) if they don't match.

Source: https://github.com/WFCD/warframe-drop-data
Web UI (manual lookups): https://drops.warframestat.us/
"""

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests

from .config import DEFAULT_CONFIG, OrdisConfig

# Field names actually used across drops.warframestat.us tables for the
# item's display name, in priority order. Confirmed against a live fetch of
# missionRewards.json: reward entries use "itemName", not "item" as the
# original doc assumed.
_NAME_FIELDS = ("itemName", "item", "name")

# Tables that are flat lists of records containing an item-like name field.
# (missionRewards is handled separately below since it's deeply nested and
# has an irregular shape.)
_LIST_TABLES = [
    "cetusBountyRewards",
    "solarisBountyRewards",
    "zarimanRewards",
    "sortieRewards",
    "transientRewards",
    "keyRewards",
    "modLocations",
    "blueprintLocations",
    "enemyBlueprintTables",
    "enemyModTables",
    "syndicates",
]


def _entry_name(entry: Dict[str, Any]) -> Optional[str]:
    for field in _NAME_FIELDS:
        val = entry.get(field)
        if val:
            return val
    return None


@dataclass
class DropResult:
    item: str
    table: str
    location: Optional[str]
    chance: Optional[float]
    rotation: Optional[str]
    rarity: Optional[str]
    raw: Dict[str, Any]


# Ducat value by rarity — DE's ducat trade-in values for Prime component
# blueprints have been stable for years (this is a fixed game rule, not
# live/fetched data, similar in kind to "how many players are on a squad"
# — it doesn't need a network call). Set blueprints themselves aren't
# ducat-tradable, only individual components (Neuroptics/Chassis/Systems/
# weapon parts etc). Source: long-standing, unchanged DE/community
# reference value — flag if this ever turns out to be wrong for a specific
# item, since a handful of older items have historically had exceptions.
DUCAT_VALUES = {
    "common": 15,
    "uncommon": 45,
    "rare": 100,
}


def ducat_value(rarity: Optional[str]) -> Optional[int]:
    if not rarity:
        return None
    return DUCAT_VALUES.get(rarity.strip().lower())


class DropsError(RuntimeError):
    """Raised when the drop-data API returns an unexpected response."""


class DropTables:
    def __init__(self, config: OrdisConfig = DEFAULT_CONFIG, auto_load: bool = True):
        self._config = config
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": config.user_agent})
        self._raw: Dict[str, Any] = {}
        self._index: Dict[str, List[DropResult]] = defaultdict(list)
        if auto_load:
            self.refresh()

    # --- Loading ----------------------------------------------------------
    def refresh(self) -> None:
        """Fetch the full drop dump and rebuild the search index.

        The dataset is refreshed by WFCD on game updates, not continuously,
        so this is safe to call on a slow interval (e.g. once per hour)
        rather than per-request.
        """
        url = f"{self._config.drops_base}/all.json"
        try:
            resp = self._session.get(url, timeout=self._config.request_timeout)
            resp.raise_for_status()
            self._raw = resp.json()
        except requests.RequestException as exc:
            raise DropsError(f"Drop table request failed for {url}: {exc}") from exc
        self._build_index()

    def get_table(self, table_name: str) -> Any:
        """Fetch a single table directly (e.g. 'relics', 'missionRewards')
        instead of pulling the full ~20MB blob."""
        url = f"{self._config.drops_base}/{table_name}.json"
        try:
            resp = self._session.get(url, timeout=self._config.request_timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            raise DropsError(f"Drop table request failed for {url}: {exc}") from exc

    def _build_index(self) -> None:
        self._index = defaultdict(list)

        # missionRewards is nested: { "Earth": { "MissionNode": {gameMode,
        # isEvent, rewards} } }. `rewards` itself is IRREGULAR: for most
        # missions it's a dict keyed by rotation ("A"/"B"/"C" or the raw
        # rotation letter), but for single-reward mission types (Capture,
        # Assassination, Exterminate, etc.) it's a plain flat list instead.
        # Handle both without crashing on the other.
        mission_rewards = self._raw.get("missionRewards", {})
        if isinstance(mission_rewards, dict):
            for planet, missions in mission_rewards.items():
                if not isinstance(missions, dict):
                    continue
                for mission_name, mission_data in missions.items():
                    if not isinstance(mission_data, dict):
                        continue
                    rewards = mission_data.get("rewards")
                    location = f"{planet} / {mission_name}"

                    if isinstance(rewards, dict):
                        # keyed by rotation
                        for rotation, items in rewards.items():
                            if not isinstance(items, list):
                                continue
                            self._index_reward_list(items, "missionRewards", location, rotation)
                    elif isinstance(rewards, list):
                        # flat list, no rotation
                        self._index_reward_list(rewards, "missionRewards", location, None)

        # Void Relics — CONFIRMED VIA LIVE FETCH: relics.json is a flat list
        # of records shaped {tier, relicName, state, rewards: [{itemName,
        # rarity, chance}]}. This is one level deeper than the other flat
        # tables (reward items live under a nested "rewards" list, not at
        # the top level of each record), so it needs its own handling
        # rather than going through _LIST_TABLES. This matters a lot in
        # practice: nearly every Prime part in the game drops ONLY from
        # relics, so skipping this table (as an earlier version of this
        # file did) makes find_drop() silently blind to most Prime items.
        relics = self._raw.get("relics")
        if isinstance(relics, list):
            for relic in relics:
                if not isinstance(relic, dict):
                    continue
                rewards = relic.get("rewards")
                if not isinstance(rewards, list):
                    continue
                tier = relic.get("tier", "")
                relic_name = relic.get("relicName", "")
                state = relic.get("state")  # Intact / Exceptional / Flawless / Radiant
                location = f"{tier} {relic_name} Relic".strip()
                self._index_reward_list(rewards, "relics", location, state)

        # Flat list-style tables. Wrapped per-table in case a table's shape
        # doesn't match what we expect — one odd table shouldn't take down
        # indexing for the rest.
        for table_name in _LIST_TABLES:
            entries = self._raw.get(table_name)
            if not isinstance(entries, list):
                continue
            try:
                self._index_reward_list(entries, table_name, None, None, extra_fields=True)
            except Exception:
                # Best-effort: skip a table whose shape we didn't predict
                # rather than failing the whole refresh.
                continue

    def _index_reward_list(
        self,
        items: List[Any],
        table: str,
        location: Optional[str],
        rotation: Optional[str],
        extra_fields: bool = False,
    ) -> None:
        for entry in items:
            if not isinstance(entry, dict):
                continue
            name = _entry_name(entry)
            if not name:
                continue
            loc = location
            if extra_fields and loc is None:
                loc = entry.get("location") or entry.get("place")
            rot = rotation
            if extra_fields and rot is None:
                rot = entry.get("rotation")
            result = DropResult(
                item=name,
                table=table,
                location=loc,
                chance=entry.get("chance"),
                rotation=rot,
                rarity=entry.get("rarity"),
                raw=entry,
            )
            self._index[name.lower()].append(result)

    # --- Querying -----------------------------------------------------------
    def find_drop(self, item: str) -> List[DropResult]:
        """Return every known drop source for an item (case-insensitive,
        substring match against the index keys)."""
        if not self._index:
            self.refresh()
        needle = item.lower()
        hits: List[DropResult] = []
        for key, results in self._index.items():
            if needle in key:
                hits.extend(results)
        return hits

    def best_farm_location(self, item: str) -> Optional[DropResult]:
        """Convenience helper: highest-chance known source for an item."""
        hits = self.find_drop(item)
        scored = [h for h in hits if h.chance is not None]
        if not scored:
            return hits[0] if hits else None
        return max(scored, key=lambda h: h.chance)

    def find_set(self, query: str) -> Dict[str, Any]:
        """Set/component planner: group every matching item under one
        query into per-item best-source summaries, with ducat value where
        known. This is the same underlying data as find_drop() — Prime
        component names already carry the set name as a prefix in the drop
        tables (e.g. "Voruna Prime Chassis Blueprint") — reshaped around
        "what do I need for this set and where do I get each piece" rather
        than a flat list of hits.

        NOTE: this can't check what you already own — there's no
        player-inventory data source available (WFM has no third-party
        OAuth yet, see market.py). It shows every component that matched
        the query and its best farm source + ducat value, not a
        personalized completion checklist.
        """
        hits = self.find_drop(query)
        components: Dict[str, List[DropResult]] = defaultdict(list)
        for h in hits:
            components[h.item].append(h)

        summary = []
        total_ducats = 0
        for item_name, item_hits in components.items():
            scored = [h for h in item_hits if h.chance is not None]
            best = max(scored, key=lambda h: h.chance) if scored else item_hits[0]
            rarity = next((h.rarity for h in item_hits if h.rarity), None)
            ducats = ducat_value(rarity)
            if ducats:
                total_ducats += ducats
            summary.append(
                {
                    "item": item_name,
                    "rarity": rarity,
                    "ducats": ducats,
                    "source_count": len(item_hits),
                    "best_location": best.location,
                    "best_chance": best.chance,
                    "best_rotation": best.rotation,
                    "best_table": best.table,
                }
            )
        summary.sort(key=lambda c: c["item"])
        return {"query": query, "components": summary, "total_known_ducats": total_ducats}


if __name__ == "__main__":
    dt = DropTables()
    for hit in dt.find_drop("Forma Blueprint")[:5]:
        print(hit)
