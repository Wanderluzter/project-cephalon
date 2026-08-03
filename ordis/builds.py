"""
Builds — curated seed data + community submissions.

Overframe has no official public API (see the original module notes below,
still true), so this was never going to be a live-scraped data source. The
harder problem turned out to be a different one: Warframe's meta reshuffles
every few months (new frames, new Arcane systems, weapon rework waves like
Incarnon Genesis), which makes a large hand-written build list something
that goes stale fast — worse, it goes stale in a way that *looks*
authoritative right up until it's wrong. So the curated seed
(`ordis/data/builds.json`) is intentionally small and dated rather than
exhaustive, each entry tagged with a `confidence` level, and the primary
path for growing coverage is community submission, not more hand-curation.

Overframe architecture note (unchanged from the original design):

    Overframe -> scraper (rate-limited, cached, background job) -> local DB

`get_build(frame)` reads only from local data (curated JSON + persisted
community submissions). `refresh_from_overframe` remains a disabled-by-
default, best-effort stub — Overframe still has no documented API to
scrape safely.
"""

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

_CURATED_PATH = Path(__file__).parent / "data" / "builds.json"
_COMMUNITY_PATH = Path(__file__).parent.parent / "data" / "community_builds.json"


@dataclass
class Build:
    frame: str
    name: str
    mods: List[str]
    forma_count: int = 0
    source: str = "curated"  # "curated" | "community" | "overframe" (unused, no scraper yet)
    notes: str = ""
    confidence: str = "directional"  # "high" | "directional" — see module docstring


class BuildsError(RuntimeError):
    pass


class Builds:
    def __init__(
        self,
        curated_path: Path = _CURATED_PATH,
        community_path: Path = _COMMUNITY_PATH,
        enable_overframe_enrichment: bool = False,
        min_refresh_interval_s: float = 3600.0,
    ):
        self._curated_path = curated_path
        self._community_path = community_path
        self._store: Dict[str, List[Build]] = {}
        self.meta: Dict[str, Any] = {}
        self._enable_overframe = enable_overframe_enrichment
        self._min_refresh_interval_s = min_refresh_interval_s
        self._last_refresh: Dict[str, float] = {}

        self._load_curated()
        self._load_community()

    # --- Loading --------------------------------------------------------
    def _load_curated(self) -> None:
        if not self._curated_path.exists():
            return
        try:
            data = json.loads(self._curated_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        self.meta = data.get("_meta", {})
        for entry in data.get("builds", []):
            build = Build(
                frame=entry["frame"],
                name=entry["name"],
                mods=entry.get("mods", []),
                forma_count=entry.get("forma_count", 0),
                notes=entry.get("notes", ""),
                confidence=entry.get("confidence", "directional"),
                source="curated",
            )
            self._store.setdefault(build.frame.lower(), []).append(build)

    def _load_community(self) -> None:
        if not self._community_path.exists():
            return
        try:
            entries = json.loads(self._community_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        for entry in entries:
            build = Build(
                frame=entry["frame"],
                name=entry["name"],
                mods=entry.get("mods", []),
                forma_count=entry.get("forma_count", 0),
                notes=entry.get("notes", ""),
                confidence=entry.get("confidence", "directional"),
                source="community",
            )
            self._store.setdefault(build.frame.lower(), []).append(build)

    # --- Reading ----------------------------------------------------------
    def add_build(self, build: Build) -> None:
        """In-memory only — for tests/scripts. Use submit_build() for
        anything that should persist across restarts."""
        self._store.setdefault(build.frame.lower(), []).append(build)

    def get_build(self, frame: str) -> List[Build]:
        return self._store.get(frame.lower(), [])

    def list_frames(self) -> List[str]:
        return sorted({b.frame for builds in self._store.values() for b in builds})

    # --- Community submission ------------------------------------------------
    def submit_build(
        self, frame: str, name: str, mods: List[str], forma_count: int = 0, notes: str = ""
    ) -> Build:
        """Accepts and persists a community-submitted build. No moderation
        pipeline exists yet — this is intentionally simple (append to a
        JSON file) so coverage can grow without every frame needing to go
        through hand-curation. Marked source='community' and
        confidence='directional' so the UI can visually distinguish it
        from the reviewed curated seed."""
        if not frame or not name or not mods:
            raise BuildsError("frame, name, and at least one mod are required")

        build = Build(
            frame=frame,
            name=name,
            mods=mods,
            forma_count=forma_count,
            notes=notes,
            confidence="directional",
            source="community",
        )
        self._store.setdefault(build.frame.lower(), []).append(build)

        # Persist: read-modify-write the whole community file. Fine at
        # this scale; swap for a real DB if submission volume ever
        # justifies it.
        existing = []
        if self._community_path.exists():
            try:
                existing = json.loads(self._community_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                existing = []
        existing.append(
            {"frame": build.frame, "name": build.name, "mods": build.mods,
             "forma_count": build.forma_count, "notes": build.notes}
        )
        self._community_path.parent.mkdir(parents=True, exist_ok=True)
        self._community_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        return build

    # --- Background enrichment (disabled by default) ----------------------
    def refresh_from_overframe(self, frame: str) -> None:
        """Best-effort, unofficial background enrichment. Disabled unless
        explicitly enabled at construction time — Overframe still has no
        official, documented, or stable API to scrape."""
        if not self._enable_overframe:
            raise BuildsError(
                "Overframe enrichment is disabled by default (no official API — "
                "see module docstring). Pass enable_overframe_enrichment=True to "
                "Builds() if you've implemented and accepted the risk of a scraper."
            )

        now = time.monotonic()
        last = self._last_refresh.get(frame.lower(), 0.0)
        if now - last < self._min_refresh_interval_s:
            return

        raise NotImplementedError(
            "No scraper implemented. Overframe has no official API — implement this "
            "as a separate, rate-limited background job, not inline in a request path."
        )


if __name__ == "__main__":
    b = Builds()
    print("Loaded curated builds for:", b.list_frames())
    print("Meta:", b.meta)
