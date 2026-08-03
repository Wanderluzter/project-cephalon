"""
Project ORDIS — adapter smoke test.

Run this to sanity-check that all five data-source integrations are wired
correctly. Network access required (worldstate, drops, market, wiki).
"""

from ordis import Worldstate, DropTables, Market, Lore, Builds
from ordis.builds import Build


def main() -> None:
    print("=== Worldstate ===")
    ws = Worldstate()
    try:
        sortie = ws.get_sortie()
        print("Sortie boss:", sortie.get("boss"))
    except Exception as exc:
        print("Worldstate check failed:", exc)

    print("\n=== Drop tables ===")
    try:
        dt = DropTables()
        hits = dt.find_drop("Forma Blueprint")
        print(f"Found {len(hits)} sources for 'Forma Blueprint'")
        if hits:
            print(" e.g.:", hits[0])
    except Exception as exc:
        print("Drop table check failed:", exc)

    print("\n=== Market (v2) ===")
    try:
        m = Market()
        results = m.search_item("ash prime")
        print("Search results (raw, first entry):", results[:1] if isinstance(results, list) else results)
    except Exception as exc:
        print("Market check failed (expected while v2 stabilizes):", exc)

    print("\n=== Lore ===")
    try:
        lore = Lore()
        summary = lore.get_summary("Rhino")
        print("Rhino summary:", (summary or "")[:200])
    except Exception as exc:
        print("Lore check failed:", exc)

    print("\n=== Builds (local store, no live Overframe call) ===")
    builds = Builds()
    builds.add_build(
        Build(frame="Rhino", name="Community Tank", mods=["Vitality", "Steel Fiber", "Iron Skin"], forma_count=2)
    )
    print(builds.get_build("Rhino"))


if __name__ == "__main__":
    main()
