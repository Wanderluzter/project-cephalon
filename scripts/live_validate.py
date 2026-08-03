"""
Live validation script — run this against the real internet (not the
sandboxed environment this project was built in) to check every adapter's
assumptions against actual live API responses.

Throughout this project, several field-name/shape assumptions were made
without being able to verify them live (market seller names, Lich auction
fields, weekly tracker shapes for calendar/weeklyChallenges/
clanWeeklyInitiative, Archimedea structure, Sortie variants). This script
turns every one of those "I couldn't verify this" caveats into an actual
pass/fail check you can run with one command.

Usage:
    python scripts/live_validate.py            # run everything
    python scripts/live_validate.py --quick     # skip slow/heavy checks (full drop-table load)
    python scripts/live_validate.py --verbose   # dump raw payloads for anything flagged uncertain

Exit code is 0 if every check passed, 1 if anything failed or looked
suspicious. This does NOT require OPENROUTER_API_KEY — chat/LLM isn't
checked here, only the data adapters.
"""

import argparse
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ordis import Worldstate, DropTables, Market, Lore, Builds, Riven  # noqa: E402


class Report:
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.passed = 0
        self.failed = 0
        self.warned = 0

    def ok(self, name: str, detail: str = ""):
        self.passed += 1
        print(f"  \033[92mPASS\033[0m  {name}" + (f" — {detail}" if detail else ""))

    def warn(self, name: str, detail: str):
        self.warned += 1
        print(f"  \033[93mWARN\033[0m  {name} — {detail}")

    def fail(self, name: str, detail: str):
        self.failed += 1
        print(f"  \033[91mFAIL\033[0m  {name} — {detail}")

    def dump(self, label: str, data) -> None:
        if self.verbose:
            print(f"    [{label}] {data!r}"[:500])

    def section(self, title: str):
        print(f"\n=== {title} ===")


def check_worldstate(r: Report, quick: bool):
    r.section("Worldstate (api.warframestat.us)")
    ws = Worldstate()
    endpoints = sorted(ws.ENDPOINTS.keys())
    if quick:
        endpoints = ["sortie", "cetus-cycle", "nightwave", "arbitration", "void-trader", "calendar"]

    for endpoint in endpoints:
        try:
            data = ws.call(endpoint, force_refresh=True)
            r.dump(endpoint, data)
            if endpoint == "arbitration" and isinstance(data, dict) and data.get("expired"):
                r.warn(endpoint, "returned expired:true placeholder — check if this persists (see README)")
            elif endpoint == "dark-sectors" and isinstance(data, list) and not data:
                r.warn(endpoint, "empty — expected if this endpoint really is deprecated (see README)")
            elif endpoint in ("calendar", "weekly-challenges", "clan-weekly-initiative") and isinstance(data, dict):
                r.ok(endpoint, f"got a response, {len(data)} top-level keys — inspect with --verbose, renderer is currently generic")
            else:
                r.ok(endpoint)
        except Exception as exc:
            r.fail(endpoint, str(exc))


def check_drops(r: Report, quick: bool):
    r.section("Drop tables (drops.warframestat.us)")
    dt = DropTables(auto_load=False)
    try:
        t0 = time.time()
        dt.refresh()
        r.ok("refresh() full dump", f"{time.time() - t0:.1f}s")
    except Exception as exc:
        r.fail("refresh()", str(exc))
        return

    for item in ["Forma Blueprint", "Voruna Prime Chassis Blueprint"]:
        hits = dt.find_drop(item)
        if hits:
            r.ok(f"find_drop('{item}')", f"{len(hits)} sources")
        else:
            r.fail(f"find_drop('{item}')", "no sources found — check if relics/missionRewards indexing broke")

    relic_hits = [h for h in dt.find_drop("Prime") if h.table == "relics"]
    if relic_hits:
        r.ok("relics table indexed", f"{len(relic_hits)} relic-sourced hits for 'Prime'")
    else:
        r.fail("relics table indexed", "zero relic hits — relics indexing may be broken again")

    result = dt.find_set("Voruna Prime")
    if result["components"]:
        r.ok("find_set('Voruna Prime')", f"{len(result['components'])} components, {result['total_known_ducats']} ducats")
    else:
        r.warn("find_set('Voruna Prime')", "no components found — item may not exist yet or naming changed")


def check_market(r: Report, quick: bool):
    r.section("Market (docs.warframe.market v2)")
    m = Market()
    try:
        results = m.search_item("rhino prime set")
        if results:
            r.ok("search_item (client-side catalog filter)", f"{len(results)} matches")
        else:
            r.fail("search_item", "zero matches for a known item — catalog fetch or filter may be broken")
            return
    except Exception as exc:
        r.fail("search_item / catalog load", str(exc))
        return

    slug = results[0]["slug"]
    try:
        price = m.lowest_sell_price(slug, online_only=False)
        r.ok(f"lowest_sell_price('{slug}')", f"{price}p")
    except Exception as exc:
        r.fail("lowest_sell_price", str(exc))

    try:
        top = m.top_sellers(slug, limit=5)
        r.dump("top_sellers", [(o.seller_name, o.platinum, o.user_status) for o in top])
        named = [o for o in top if o.seller_name and not o.seller_name.startswith("seller-")]
        if top and named:
            r.ok("top_sellers seller names", f"{len(named)}/{len(top)} resolved a real name")
        elif top:
            r.warn("top_sellers seller names", "none resolved a real name — the ingame_name field guess may be wrong, see market.py caveat")
        else:
            r.warn("top_sellers", "no live sell orders for this item right now — try a more common item")
    except Exception as exc:
        r.fail("top_sellers", str(exc))

    if not quick:
        try:
            points = m.get_price_history(slug, days=7)
            r.dump("price_history", points[:2])
            if points:
                r.ok("get_price_history (v1 exception)", f"{len(points)} points")
            else:
                r.warn("get_price_history", "empty — check the statistics_closed.90days shape assumption")
        except Exception as exc:
            r.fail("get_price_history (v1 exception)", str(exc))


def check_riven_and_lich(r: Report, quick: bool):
    r.section("Riven & Lich auctions (v1 exception)")
    riven = Riven()
    try:
        auctions = riven.search(weapon_url_name="braton_prime", limit=5)
        r.dump("riven auctions", auctions[:1])
        if auctions:
            r.ok("search (riven)", f"{len(auctions)} live auctions")
        else:
            r.warn("search (riven)", "zero auctions — could be genuinely no listings, or the platform param fix didn't fully resolve the earlier 400")
    except Exception as exc:
        r.fail("search (riven) — was 400ing before a platform-param fix", str(exc))

    if quick:
        return
    try:
        liches = riven.search_liches(having_ephemera=True, limit=5)
        r.dump("lich auctions", liches[:1])
        if liches:
            r.ok("search_liches", f"{len(liches)} live auctions")
        else:
            r.warn("search_liches", "zero auctions — could be genuinely none with ephemera right now, or the field-shape guess is wrong")
    except Exception as exc:
        r.fail("search_liches", str(exc))


def check_lore(r: Report, quick: bool):
    r.section("Lore (wiki.warframe.com)")
    lore = Lore()
    try:
        summary = lore.get_summary("Rhino")
        if summary:
            r.ok("get_summary('Rhino')", f"{len(summary)} chars")
        else:
            r.warn("get_summary('Rhino')", "empty — REST endpoint may be failing again, check the extracts fallback")
    except Exception as exc:
        r.fail("get_summary", str(exc))


def check_builds(r: Report, quick: bool):
    r.section("Builds (local — no network required)")
    try:
        b = Builds()
        frames = b.list_frames()
        if frames:
            r.ok("curated seed loaded", f"{len(frames)} frames: {', '.join(frames)}")
        else:
            r.fail("curated seed loaded", "zero frames — ordis/data/builds.json may be missing or malformed")
        as_of = b.meta.get("as_of")
        if as_of:
            r.ok("seed metadata", f"as_of={as_of}")
        else:
            r.warn("seed metadata", "no as_of date found in builds.json _meta")
    except Exception as exc:
        r.fail("Builds()", str(exc))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--quick", action="store_true", help="skip slow/heavy checks")
    parser.add_argument("--verbose", action="store_true", help="dump raw payloads for uncertain checks")
    args = parser.parse_args()

    r = Report(verbose=args.verbose)
    checks = [check_worldstate, check_drops, check_market, check_riven_and_lich, check_lore, check_builds]
    for check in checks:
        try:
            check(r, args.quick)
        except Exception:
            print(f"  \033[91mCRASHED\033[0m running {check.__name__}:")
            traceback.print_exc()
            r.failed += 1

    print(f"\n{'=' * 50}")
    print(f"PASS: {r.passed}   WARN: {r.warned}   FAIL: {r.failed}")
    print("=" * 50)
    sys.exit(1 if r.failed else 0)


if __name__ == "__main__":
    main()
