"""
Project ORDIS — local backend.

Wraps the ordis adapters (worldstate, drops, market, lore, builds, and the
chat agent) as JSON endpoints for the frontend dashboard. Runs entirely
server-side so the browser never has to deal with CORS or hold API
credentials.

Run:
    python app.py
Then open http://127.0.0.1:5000

Chat requires an OpenRouter API key: set OPENROUTER_API_KEY in your
environment, or drop it in a .env file next to this script (KEY=value per
line — loaded below with no extra dependency required).
"""

import os
import re
import threading
import time
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import requests
from flask import Flask, jsonify, request, render_template, Response

from ordis import Worldstate, DropTables, Market, Lore, Builds, Riven, OrdisAgent
from ordis.imagegen import generate_weekly_digest
from ordis.llm import LLMError


def _load_dotenv(path: str = ".env") -> None:
    """Tiny .env loader — avoids adding python-dotenv as a dependency for
    one feature. Existing environment variables always win."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))
    except FileNotFoundError:
        pass


_load_dotenv()

app = Flask(__name__)

worldstate = Worldstate()
drops = DropTables(auto_load=False)  # lazy-load on first request, not at boot
market = Market()
lore = Lore()
builds = Builds()  # loads curated seed from ordis/data/builds.json + any persisted community submissions
riven = Riven()

# Chat agent is optional — only stands up if OPENROUTER_API_KEY is set
# (env var or .env file). The dashboard still works without it; the chat
# panel just reports itself as unavailable.
agent = None
_agent_error = None
try:
    agent = OrdisAgent(worldstate=worldstate, drops=drops, market=market, lore=lore, builds=builds, riven=riven)
except LLMError as exc:
    _agent_error = str(exc)
    print(f"[ORDIS] Chat agent disabled: {exc}")


# --- Weekly digest image ---------------------------------------------------
_WEEKLY_IMAGE_PATH = Path(__file__).parent / "static" / "generated" / "weekly_digest.png"
_WEEKLY_MAX_AGE_SECONDS = 7 * 24 * 3600
_weekly_lock = threading.Lock()


def _weekly_image_age_seconds() -> Optional[float]:
    if not _WEEKLY_IMAGE_PATH.exists():
        return None
    return time.time() - _WEEKLY_IMAGE_PATH.stat().st_mtime


def _regenerate_weekly_image() -> None:
    with _weekly_lock:
        generate_weekly_digest(worldstate, str(_WEEKLY_IMAGE_PATH))


def _weekly_scheduler_loop() -> None:
    """Runs for the life of the process: checks once a day whether the
    digest image is missing or older than a week, and regenerates if so.
    This is what actually makes it "weekly" regardless of whether anyone
    visits the page — not just generate-on-request."""
    while True:
        try:
            age = _weekly_image_age_seconds()
            if age is None or age > _WEEKLY_MAX_AGE_SECONDS:
                print("[ORDIS] Generating weekly digest image...")
                _regenerate_weekly_image()
                print("[ORDIS] Weekly digest image generated.")
        except Exception as exc:  # noqa: BLE001 — a failed generation shouldn't kill the loop
            print(f"[ORDIS] Weekly digest generation failed: {exc}")
        time.sleep(24 * 3600)


# Guard against the Flask reloader starting this thread twice in debug mode.
if os.environ.get("WERKZEUG_RUN_MAIN") != "true" or not app.debug:
    threading.Thread(target=_weekly_scheduler_loop, daemon=True).start()


def _err(exc: Exception, status: int = 502):
    return jsonify({"error": str(exc)}), status


# --- Worldstate --------------------------------------------------------
# Endpoint list lives on Worldstate.ENDPOINTS (ordis/worldstate.py) — single
# source of truth shared with the chat agent's tool schema.


@app.route("/api/worldstate/<endpoint>")
def api_worldstate(endpoint: str):
    if endpoint not in Worldstate.ENDPOINTS:
        return jsonify({"error": f"unknown worldstate endpoint '{endpoint}'"}), 404
    try:
        return jsonify(worldstate.call(endpoint))
    except Exception as exc:
        return _err(exc)


@app.route("/api/worldstate/all")
def api_worldstate_all():
    """Fetch every dashboard-relevant endpoint in one round trip so the
    frontend can render the full status board without N sequential calls."""
    out = {}
    for key in Worldstate.ENDPOINTS:
        try:
            out[key] = worldstate.call(key)
        except Exception as exc:
            out[key] = {"error": str(exc)}
    return jsonify(out)


@app.route("/api/server-status")
def api_server_status():
    try:
        status = worldstate.check_platform_status()
    except Exception as exc:
        return _err(exc)
    return jsonify(status)


# --- Drops / item hunter -------------------------------------------------
@app.route("/api/drops/find")
def api_drops_find():
    item = request.args.get("item", "").strip()
    if not item:
        return jsonify({"error": "missing 'item' query param"}), 400
    try:
        if not drops._raw:  # lazy-load the ~20MB dump on first real use
            drops.refresh()
        hits = drops.find_drop(item)
    except Exception as exc:
        return _err(exc)
    hits_sorted = sorted(hits, key=lambda h: (h.chance is None, -(h.chance or 0)))
    return jsonify([
        {
            "item": h.item,
            "table": h.table,
            "location": h.location,
            "chance": h.chance,
            "rotation": h.rotation,
            "rarity": h.rarity,
        }
        for h in hits_sorted[:50]
    ])


@app.route("/api/drops/set")
def api_drops_set():
    """Set/component planner — see DropTables.find_set() for what this
    does and does not do (no player-inventory awareness, just component +
    ducat + best-source grouping)."""
    query = request.args.get("query", "").strip()
    if not query:
        return jsonify({"error": "missing 'query' query param"}), 400
    try:
        if not drops._raw:
            drops.refresh()
        result = drops.find_set(query)
    except Exception as exc:
        return _err(exc)
    return jsonify(result)


# --- Market ---------------------------------------------------------------
@app.route("/api/market/search")
def api_market_search():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"error": "missing 'q' query param"}), 400
    try:
        results = market.search_item(q)
    except Exception as exc:
        return _err(exc)
    return jsonify([
        {
            "slug": r.get("slug"), "name": r.get("display_name"), "tags": r.get("tags"),
            # Routed through our own proxy (not the raw external URL) —
            # see api_image_proxy() below for why: WFM's CDN may reject
            # direct browser requests over a mismatched Referer, which
            # would make every image silently fail. Server-to-server
            # requests aren't subject to that.
            "image_url": f"/api/image-proxy?path={quote(r['icon_path'])}" if r.get("icon_path") else None,
        }
        for r in results[:20]
    ])


# Only relative paths matching WFM's own confirmed icon-path shape are
# ever fetched — no full URLs, no protocol, no traversal, no leading
# slash. This exists specifically so this endpoint can NEVER be used as
# an open proxy/SSRF vector regardless of what a client sends. Multiple
# explicit checks (not just the regex) as defense-in-depth, since a
# future refactor to use urljoin() instead of plain string formatting
# would change how a leading "//" or "/" gets resolved.
_ICON_PATH_RE = re.compile(r"^[a-zA-Z0-9_][a-zA-Z0-9_\-./]*\.(png|jpg|jpeg|webp)$")


def _is_safe_icon_path(path: str) -> bool:
    if not path:
        return False
    if ".." in path or "://" in path or "//" in path:
        return False
    if path.startswith("/") or path.startswith("\\"):
        return False
    return bool(_ICON_PATH_RE.match(path))


@app.route("/api/image-proxy")
def api_image_proxy():
    """Fetches an item icon server-side and streams it back, instead of
    the browser loading it directly from warframe.market. This sidesteps
    any hotlink/Referer-based blocking the CDN might do on cross-origin
    browser requests — a plausible explanation for images not appearing
    at all with no visible broken-image icon (the onerror fallback would
    fire silently on a blocked request)."""
    path = request.args.get("path", "")
    if not _is_safe_icon_path(path):
        return jsonify({"error": "invalid image path"}), 400

    url = f"{market._config.market_image_base}/{path}"
    try:
        resp = requests.get(url, timeout=6, headers={"User-Agent": market._config.user_agent})
        resp.raise_for_status()
    except requests.RequestException as exc:
        return jsonify({"error": f"upstream image fetch failed: {exc}"}), 502

    content_type = resp.headers.get("Content-Type", "image/png")
    return Response(resp.content, mimetype=content_type, headers={"Cache-Control": "public, max-age=86400"})


@app.route("/api/market/price/<slug>")
def api_market_price(slug: str):
    try:
        # online_only=False here means "don't require the seller to be
        # in-game right now" — this still only pulls LIVE current orders
        # (see market.py get_price()), never historical/average pricing.
        price = market.lowest_sell_price(slug, online_only=False)
    except Exception as exc:
        return _err(exc)
    return jsonify({"slug": slug, "lowest_sell_platinum": price})


@app.route("/api/market/sellers/<slug>")
def api_market_sellers(slug: str):
    """Top 10 live sell orders for an item, cheapest first, with seller
    name/status. See market.py for the caveat on the exact seller-name
    field — it's read defensively since I couldn't confirm the precise
    v2 field name from a raw payload."""
    try:
        top = market.top_sellers(slug, limit=10, online_only=False)
    except Exception as exc:
        return _err(exc)
    return jsonify([
        {
            "seller": o.seller_name or "unknown seller",
            "platinum": o.platinum,
            "quantity": o.quantity,
            "status": o.user_status or "unknown",
        }
        for o in top
    ])


@app.route("/api/market/history/<slug>")
def api_market_history(slug: str):
    """Daily sell-price history. See market.py get_price_history() for the
    v1-exception caveat — v2 has no price-statistics endpoint yet."""
    days = request.args.get("days", default=14, type=int)
    try:
        points = market.get_price_history(slug, days=days)
    except Exception as exc:
        return _err(exc)
    return jsonify([
        {
            "date": p.date,
            "avg_price": p.avg_price,
            "median": p.median,
            "min_price": p.min_price,
            "max_price": p.max_price,
            "volume": p.volume,
        }
        for p in points
    ])


# --- Rivens -----------------------------------------------------------------
@app.route("/api/rivens/search")
def api_rivens_search():
    """Riven auction search. Targets Warframe Market's v1 API — see
    ordis/riven.py for why (v2 has no auctions/rivens endpoint yet)."""
    weapon = request.args.get("weapon", "").strip()
    if not weapon:
        return jsonify({"error": "missing 'weapon' query param"}), 400
    weapon_slug = weapon.lower().replace(" ", "_")
    try:
        auctions = riven.search(
            weapon_url_name=weapon_slug,
            buyout_policy=request.args.get("buyout_policy") or None,
            sort_by=request.args.get("sort_by", "price_asc"),
            limit=20,
        )
    except Exception as exc:
        return _err(exc)
    return jsonify([
        {
            "weapon": a.weapon,
            "positive_stats": a.positive_stats,
            "negative_stat": a.negative_stat,
            "polarity": a.polarity,
            "mod_rank": a.mod_rank,
            "mastery_level": a.mastery_level,
            "re_rolls": a.re_rolls,
            "starting_price": a.starting_price,
            "buyout_price": a.buyout_price,
            "is_direct_sell": a.is_direct_sell,
            "seller": a.seller_name or "unknown seller",
            "seller_status": a.seller_status or "unknown",
        }
        for a in auctions
    ])


@app.route("/api/liches/search")
def api_liches_search():
    """Kuva Lich / Sister of Parvos auction search. Same v1 endpoint
    family as rivens — see ordis/riven.py."""
    weapon = request.args.get("weapon", "").strip()
    weapon_slug = weapon.lower().replace(" ", "_") if weapon else None
    having_ephemera_raw = request.args.get("having_ephemera")
    having_ephemera = having_ephemera_raw == "true" if having_ephemera_raw else None
    try:
        liches = riven.search_liches(
            weapon_url_name=weapon_slug,
            element=request.args.get("element") or None,
            having_ephemera=having_ephemera,
            sort_by=request.args.get("sort_by", "price_asc"),
            limit=20,
        )
    except Exception as exc:
        return _err(exc)
    return jsonify([
        {
            "weapon": l.weapon,
            "element": l.element,
            "has_ephemera": l.has_ephemera,
            "ephemera": l.ephemera,
            "quirks": l.quirks,
            "damage": l.damage,
            "starting_price": l.starting_price,
            "buyout_price": l.buyout_price,
            "is_direct_sell": l.is_direct_sell,
            "seller": l.seller_name or "unknown seller",
            "seller_status": l.seller_status or "unknown",
        }
        for l in liches
    ])


# --- Lore -------------------------------------------------------------------
@app.route("/api/lore/summary")
def api_lore_summary():
    topic = request.args.get("topic", "").strip()
    if not topic:
        return jsonify({"error": "missing 'topic' query param"}), 400
    try:
        summary = lore.get_summary(topic)
        if not summary:
            hits = lore.search(topic, limit=1)
            if hits:
                summary = lore.get_summary(hits[0]["title"])
    except Exception as exc:
        return _err(exc)
    return jsonify({"topic": topic, "summary": summary})


# --- Builds -----------------------------------------------------------------
@app.route("/api/builds/<frame>")
def api_builds(frame: str):
    results = builds.get_build(frame)
    return jsonify([
        {
            "name": b.name, "mods": b.mods, "forma_count": b.forma_count,
            "notes": b.notes, "source": b.source, "confidence": b.confidence,
        }
        for b in results
    ])


@app.route("/api/builds")
def api_builds_index():
    """List every frame with at least one build on file, plus the
    curated-seed disclaimer metadata (as_of date, staleness warning)."""
    return jsonify({"frames": builds.list_frames(), "meta": builds.meta})


@app.route("/api/builds/submit", methods=["POST"])
def api_builds_submit():
    body = request.get_json(silent=True) or {}
    try:
        build = builds.submit_build(
            frame=(body.get("frame") or "").strip(),
            name=(body.get("name") or "").strip(),
            mods=[m.strip() for m in (body.get("mods") or []) if m.strip()],
            forma_count=int(body.get("forma_count") or 0),
            notes=(body.get("notes") or "").strip(),
        )
    except Exception as exc:
        return _err(exc, status=400)
    return jsonify({
        "name": build.name, "frame": build.frame, "mods": build.mods,
        "forma_count": build.forma_count, "notes": build.notes,
        "source": build.source, "confidence": build.confidence,
    })


# --- Chat ---------------------------------------------------------------
@app.route("/api/chat/status")
def api_chat_status():
    return jsonify({"available": agent is not None, "error": _agent_error})


@app.route("/api/chat", methods=["POST"])
def api_chat():
    if agent is None:
        return jsonify({
            "error": (
                "Chat isn't configured. Set OPENROUTER_API_KEY (env var or .env "
                "file) and restart the server. Detail: " + (_agent_error or "")
            )
        }), 503

    body = request.get_json(silent=True) or {}
    message = (body.get("message") or "").strip()
    history = body.get("history") or []
    if not message:
        return jsonify({"error": "missing 'message'"}), 400
    # Only pass through plain user/assistant turns — the agent rebuilds its
    # own tool-call bookkeeping fresh each turn, so trimming history to just
    # role+content keeps the request small and avoids stale tool_call ids.
    clean_history = [
        {"role": m.get("role"), "content": m.get("content", "")}
        for m in history
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]

    try:
        result = agent.ask(message, history=clean_history)
    except LLMError as exc:
        return jsonify({"error": str(exc)}), 502
    return jsonify(result)


@app.route("/")
def page_overview():
    return render_template("index.html", active_page="overview")


@app.route("/worldstate")
def page_worldstate():
    return render_template("worldstate.html", active_page="worldstate")


@app.route("/drops")
def page_drops():
    return render_template("drops.html", active_page="drops")


@app.route("/market")
def page_market():
    return render_template("market.html", active_page="market")


@app.route("/rivens")
def page_rivens():
    return render_template("rivens.html", active_page="rivens")


@app.route("/lore")
def page_lore():
    return render_template("lore.html", active_page="lore")


@app.route("/builds")
def page_builds():
    return render_template("builds.html", active_page="builds")


@app.route("/weekly")
def page_weekly():
    age = _weekly_image_age_seconds()
    return render_template(
        "weekly.html",
        active_page="weekly",
        image_exists=_WEEKLY_IMAGE_PATH.exists(),
        age_days=round(age / 86400, 1) if age is not None else None,
    )


# --- Weekly digest image API ------------------------------------------------
@app.route("/api/weekly-image/status")
def api_weekly_status():
    age = _weekly_image_age_seconds()
    return jsonify({
        "exists": _WEEKLY_IMAGE_PATH.exists(),
        "age_days": round(age / 86400, 2) if age is not None else None,
        "stale": age is None or age > _WEEKLY_MAX_AGE_SECONDS,
    })


@app.route("/api/weekly-image/regenerate", methods=["POST"])
def api_weekly_regenerate():
    try:
        _regenerate_weekly_image()
    except Exception as exc:
        return _err(exc)
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
