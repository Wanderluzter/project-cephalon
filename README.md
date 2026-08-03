# Project ORDIS — Data Integration Layer

An all-knowing Warframe assistant needs a clean, isolated adapter for every
external data source it depends on. This is that layer: five small clients,
each wrapping one source, each built to survive that source changing without
taking the rest of the app down with it.

No existing ORDIS codebase was provided, so this is a fresh implementation
built directly from the July 2026 data-source reference: worldstate,
drop tables, Warframe Market, wiki lore, and Overframe builds.

## Layout

```
project_ordis/
├── README.md
├── requirements.txt
├── .env.example              # copy to .env, set OPENROUTER_API_KEY
├── .gitignore
├── main.py                   # CLI demo / smoke test for every adapter
├── app.py                    # Flask backend, page routes, weekly-image scheduler
├── data/
│   └── community_builds.json # persisted community build submissions (created on first submit)
├── templates/
│   ├── base.html             # shared layout: header, nav, chat drawer include
│   ├── chat_widget.html      # persistent chat drawer, included on every page
│   ├── index.html            # / — summarized "generalist" overview
│   ├── worldstate.html       # /worldstate — full cycles/sortie/traders/etc.
│   ├── drops.html            # /drops — full item hunter + set planner
│   ├── market.html           # /market — full market relay + price history
│   ├── rivens.html           # /rivens — riven auction search
│   ├── lore.html             # /lore — full archive terminal
│   ├── builds.html           # /builds — loadout archive + submission form
│   └── weekly.html           # /weekly — generated digest image
├── static/
│   ├── style.css             # Orokin/Tenno HUD-styled theme (shared)
│   ├── common.js             # clock, chat widget, countdown ticker, shared render helpers
│   ├── generated/            # weekly_digest.png lands here
│   └── js/
│       ├── overview.js       # per-page logic — one file per template above
│       ├── worldstate.js
│       ├── drops.js
│       ├── market.js
│       ├── rivens.js
│       ├── lore.js
│       ├── builds.js
│       └── weekly.js
└── ordis/
    ├── __init__.py
    ├── config.py              # base URLs, timeouts, platform, OpenRouter defaults
    ├── worldstate.py          # api.warframestat.us + per-endpoint TTL cache
    ├── drops.py               # drops.warframestat.us + set/ducat planner
    ├── market.py              # docs.warframe.market v2 + v1 price-history exception
    ├── riven.py               # api.warframe.market v1 (no v2 auctions endpoint yet)
    ├── lore.py                # wiki.warframe.com
    ├── builds.py              # curated JSON seed + community submissions (no scraper — see below)
    ├── llm.py                 # OpenRouter chat-completions client
    ├── agent.py               # tool-calling chat agent ("Ordis")
    ├── imagegen.py            # weekly digest PNG renderer (Pillow)
    └── data/
        └── builds.json        # small, dated, confidence-tagged curated build seed
```

## What changed vs. a naive first pass (and why each module looks the way it does)

**`worldstate.py`** — straightforward. `api.warframestat.us` is stable and
well documented, so this is a thin typed wrapper, one method per endpoint
(fissures, sortie, nightwave, steel path, void trader, arbitration,
invasions, syndicate missions). Platform (`pc`/`ps4`/`xb1`/`switch`) is a
constructor arg, not hardcoded.

**`drops.py`** — this is the one place a naive implementation breaks. The
drop dataset is **not** a flat list of `{itemName, rarity, chance, place,
rotation}` records — it's a single JSON object keyed by table type
(`missionRewards`, `relics`, `cetusBountyRewards`, `keyRewards`, etc). So
`find_drop(item)` can't be a simple filter; it has to walk every table shape
and normalize hits into a common `DropResult`. The client builds that index
once at startup (or on a refresh interval) rather than re-scanning the ~20MB
blob per lookup, and exposes both the full dump and single-table fetches
(`relics.json`, `missionRewards.json`, ...) for callers who only need one
slice.

**`market.py`** — Warframe Market v1 is deprecated; this targets v2, which
is pre-1.0 and can introduce breaking changes. The whole point of this
module is isolation: every v2 quirk (item slug lookups, order queries, the
fact that OAuth isn't available yet for third-party apps so authenticated
actions still need the legacy v1 auth flow) lives inside this one file. If
Market breaks something upstream, you patch `market.py`, not every tool that
calls `market_price()`.

**`lore.py`** — uses the wiki's REST summary endpoint for short,
voice-line-length answers (what Ordis would actually say out loud) and falls
back to the full MediaWiki `parse` endpoint (wikitext or rendered HTML) when
a caller wants the full article — including `Story_and_History`, which is
just a page like any other, not a special endpoint.

**`builds.py`** — Overframe has no official public API. This module does
**not** hit Overframe live in the request path. It's a local build store
(swap the in-memory dict for a real DB) seeded from your own curated data,
with a rate-limited `refresh_from_overframe()` stub meant to run as a
background enrichment job, clearly marked as best-effort/unofficial and
disabled by default.

## Setup

CLI smoke test (adapters only):
```bash
pip install -r requirements.txt
python main.py
```

Full dashboard (Flask backend + Ordis-styled frontend):
```bash
pip install -r requirements.txt
python app.py
```
Then open http://127.0.0.1:5000. The browser talks to `app.py`, which
does all external API calls server-side — no CORS issues, no credentials
in client code.

## Chat — "Direct Channel" (Ordis conversational agent)

Natural-language player queries, answered by an LLM that's forced to check
real data instead of guessing. Example: *"Where can I farm Voruna Prime"*
→ the model calls `find_drop("Voruna Prime")` against the real drop-table
index, gets back actual mission/chance/rotation data, and answers from
that — it never states a drop location from its own memory.

**Setup:**
```bash
cp .env.example .env
# edit .env, set OPENROUTER_API_KEY=sk-or-v1-...  (get one at https://openrouter.ai/keys)
python app.py
```
The chat panel ("Ordis // Direct Channel") shows a status dot — cyan means
the agent is live, red means no key was found (dashboard still works
without it, chat just reports itself unavailable). `.env` is loaded
automatically by `app.py` with a small built-in loader — no `python-dotenv`
dependency needed. Real environment variables always take priority over
`.env` if both are set.

**How it's wired** (`ordis/llm.py` + `ordis/agent.py`):
- `llm.py` — thin OpenAI-compatible client for OpenRouter's
  `/chat/completions` endpoint (tool/function calling included). Model is
  configurable via `OPENROUTER_MODEL`; OpenRouter's catalog changes over
  time so check https://openrouter.ai/models rather than trusting any
  hardcoded default forever.
- `agent.py` — defines five tools (`find_drop`, `get_worldstate`,
  `get_market_price`, `get_lore`, `get_build`), each backed directly by the
  real adapter methods (no re-implementation, no separate data path). The
  system prompt hard-requires a tool call for anything factual and
  instructs the model to say "not found" rather than invent an answer when
  a tool comes back empty. Runs a bounded loop (max 4 tool rounds) so a
  confused model can't loop forever.
- `app.py` exposes `POST /api/chat` (`{"message": str, "history": [...]}`
  → `{"reply": str, "tool_calls": [...]}`) and `GET /api/chat/status` for
  the frontend's availability check.
- The frontend chat panel shows a collapsible "data pulled" trace under
  each Ordis reply so you can see exactly which tool calls backed the
  answer — useful for catching a wrong tool arg or a bad match at a glance.

## Major restructure (July 28 batch — caching, correct fields, multi-page, weekly digest)

- **Server-side caching (`ordis/worldstate.py`)** — `Worldstate.call()` now
  caches per endpoint. Daily-rotating data (all six open-world cycles,
  daily deals, flash sales, global upgrades, events, alerts, conclave
  challenges) is cached for 24h; everything else gets a 60s default TTL
  just to de-duplicate rapid repeat calls. `force_refresh=True` bypasses
  the cache when needed (used by the weekly digest generator).
- **Cycle field names — CONFIRMED against a live fetch of `api.warframestat.us/pc`**
  — `state` is always present and authoritative (`"night"`, `"vome"`,
  `"warm"`, `"grineer"`, `"sorrow"`, etc.). The old code tried to derive
  state from `isDay`, which doesn't even exist on `cambionCycle`,
  `vallisCycle`, or `duviriCycle` — that's why cycles were mislabeled.
  Also confirmed `vallisCycle` and `duviriCycle` don't return `timeLeft`
  at all. Fixed: always read `state` directly, and compute remaining time
  from `expiry` client-side with a local 1-second ticker
  (`registerCountdown()` in `static/common.js`) instead of trusting a
  field that isn't always there — and instead of re-fetching just to
  update a clock, since cycles are now cached for 24h anyway.
- **"Active Operations" field bugs — also confirmed live:**
  - Sortie has no `eta` field (was reading one that doesn't exist) — now
    computed from `expiry` via the same local countdown ticker.
  - Void/Vault Trader have no `active` boolean — status (`arriving` /
    `active` / `departed`) is now derived from `now` vs `activation`/
    `expiry` (`traderStatus()` in `common.js`).
  - Arbitration returns a placeholder object with `expired: true` and
    epoch/max-date timestamps when nothing is active — that placeholder
    was being rendered as if it were real. Fixed to check `expired` and
    show "none active" instead.
- **Improved drop-tracker visualization** — each result now shows a
  table-type badge (relic vs. mission reward), the exact location/rotation,
  and a proportional chance bar, not just a bare percentage in a list.
- **Market: live-only pricing** — orders with `quantity <= 0` (sold out)
  are now filtered out in addition to the earlier buy/sell type fix, so
  only genuinely available current listings count. No historical/average
  pricing is fetched anywhere in this app — only live `/orders/item/{slug}`
  data, by design.
- **Weekly digest image** — `ordis/imagegen.py` renders a themed PNG
  summarizing the current Nightwave weekly challenges and Steel Path
  weekly rotation (Pillow, built-in bitmap font — no external font file
  dependency). A background daemon thread in `app.py` checks once a day
  whether the image is missing or older than 7 days and regenerates it —
  this runs regardless of whether anyone visits the site, so it's
  genuinely weekly, not just generate-on-request. Manual regeneration is
  also available from the Weekly Digest page.
- **Multi-page layout** — `templates/base.html` is now the shared layout
  (header, nav, content block) with the chat drawer included on every
  page via `templates/chat_widget.html`. `/` stays the summarized
  "generalist" dashboard (same resumed content as before); `/worldstate`,
  `/drops`, `/market`, `/lore`, `/builds`, `/weekly` are dedicated full
  pages with more detail and features than the overview cares to show.
  Per-page JS lives in `static/js/<page>.js`; shared logic (clock, chat,
  countdown ticker, field-correct render helpers) lives in
  `static/common.js`, loaded on every page.
- **Chat accessible on every page** — moved from an inline dashboard panel
  into `templates/chat_widget.html`, a collapsible drawer in the
  bottom-right corner rendered by `base.html` on every route. Conversation
  history persists across page navigation via `sessionStorage` (cleared
  when the tab closes, or with the "clear" button) so switching from
  Overview to Drops mid-conversation doesn't lose context.

## Seventh batch: item images actually not appearing — server-side proxy

Reported: no item images appearing at all (not broken-icon placeholders —
nothing). Research first: found independent confirmation from a currently
maintained package (`warframe-nexus-query`, updated April 2026, explicit
v2 support) whose own example output matches this project's CDN base
exactly (`https://warframe.market/static/assets/...`) — so the URL itself
was very likely right.

The more likely explanation: **hotlink/Referer-based blocking.** CDNs
commonly reject image requests whose `Referer` header comes from an
unrecognized origin (our local Flask app), which fails silently from the
browser's perspective — no error dialog, no broken-image icon, since the
`onerror` handler just removes the element. That exactly matches "no
images appearing, nothing visible."

**Fix: route images through a server-side proxy instead of loading them
directly in the browser.** `GET /api/image-proxy?path=<relative-icon-path>`
fetches the image server-side (not subject to browser referrer policies)
and streams the bytes back same-origin. `market.py`'s catalog now exposes
the raw relative `icon_path` (not just the pre-built absolute URL), and
`/api/market/search` builds the proxy URL from it instead of handing the
browser a direct cross-origin link.

**This endpoint accepts a path from the client, so it got the same
security scrutiny as everything else in this project — with actual
adversarial testing, not just "should be fine":** `_is_safe_icon_path()`
rejects anything with `..`, `://`, a leading slash, a doubled slash, or a
non-image extension, on top of a strict character-class regex. Tested
against 13 attack vectors (protocol-relative URLs, path traversal in
several forms, `javascript:`/`file:` schemes, extension smuggling,
backslash variants) — all blocked, confirmed with an automated test
before shipping. This endpoint can never become an open proxy or SSRF
vector regardless of what a client sends it.

## Sixth batch: quick wins (validation script, server status, themes, chat polish, item icons)

- **`scripts/live_validate.py`** — run this against real internet access
  to check every adapter's assumptions in one command
  (`python scripts/live_validate.py`, add `--verbose` to dump raw payloads
  for anything uncertain, `--quick` to skip slow checks). It already
  earned its keep: running it surfaced a genuine bug — `lore.py` was
  sending `exintro=True`/`explaintext=True` as Python booleans, which
  `requests` stringifies as capitalized `"True"`, not what MediaWiki's API
  expects. Fixed to send `1` instead. This is exactly the kind of bug that
  only shows up by actually building and running a request, which is why
  this script exists — turning every "I couldn't verify this live" caveat
  scattered through this project into an actual pass/fail check.
- **Server status per platform** — `Worldstate.check_platform_status()`
  pings pc/ps4/xb1/switch (platform codes confirmed from the original
  data-source reference this project was built from) and measures
  latency. New `/api/server-status` endpoint and a panel on `/worldstate`
  showing up/down + latency + a locally-ticking "last checked Xs ago"
  timer that doesn't need to re-fetch to stay current.
- **Themes (OG / KIM)** — `[data-theme="kim"]` CSS override block reusing
  the same variable names as the default theme, so every existing
  component re-themes for free. KIM is an original retro-terminal
  palette (phosphor green + magenta on near-black) inspired by the
  general 1999/Hex concept — not sourced from or copying any specific
  reference image. Switcher buttons in the header, persisted via
  `localStorage`, applied via a synchronous inline script in `<head>` so
  there's no flash of the wrong theme on load.
- **Chat window — verified + polished.** The toggle already worked; added
  keyboard shortcuts (`/` to open and focus from anywhere, `Esc` to
  close) and a `title` attribute for discoverability.
- **Item icons — added, with an important caveat.** WFM's own catalog
  data (confirmed real from an earlier live response) includes a relative
  icon path per item. I could not confirm the CDN domain to prefix it
  with despite two searches — `market_image_base` in `config.py` is a
  best-effort guess (`warframe.market/static/assets`), clearly flagged as
  such. Rendered with `onerror="this.remove()"` so a wrong guess just
  means no icon shows (today's behavior), never a broken-image icon or
  layout break.

## Fifth batch: live bug reports + auto-refreshing timers

Real bugs from live testing, fixed with verified evidence rather than
guesses where possible:

- **Riven search 400 Bad Request — fixed.** Found the actual OpenAPI spec
  text: the search endpoint's required parameters list starts with
  `platform`, before `weapon_url_name`. The code was sending `Platform:
  pc` only as an HTTP header, never as a query parameter — added it to
  both `search()` and `search_liches()`. I can't re-run the live request
  from this sandbox to fully confirm the fix resolves it, so please
  retest.
- **Dark Sectors — investigated further, not "fixed."** Found that
  `api.warframestat.us`'s API family includes a distinct
  `DarkSectorHistory` schema separate from `Mission` (via a community
  Rust client's schema list), which suggests dark sectors are tracked at
  the mission/node level somewhere. I could not confirm an actual live
  field name for a per-mission flag within reasonable research effort,
  and guessing one would just risk another silent bug like the ones
  fixed earlier in this project. The UI message now reflects this finding
  honestly instead of claiming a fix I don't have evidence for.
- **Timers now actually refresh at zero — real fix, not just cosmetic.**
  This required two changes:
  1. `Worldstate.call()`'s cache now checks the cached payload's own
     `expiry` field, not just its TTL age. Cycles are cached for 24h
     (per an earlier request to reduce polling), but a cycle's *state*
     changes every 50min-2h — so without this fix, a countdown reaching
     zero client-side and triggering a refresh would've just gotten back
     the same stale cached state from the server. Verified with a test
     that simulates a cached payload whose expiry has already passed.
  2. `registerCountdown()` in `common.js` now defaults `onZero` to a new
     `triggerGlobalRefresh()` — every countdown that reaches zero
     triggers a real data refresh unless it explicitly opts out, debounced
     so several timers hitting zero in the same tick coalesce into one
     refresh. Wired up on the Overview and Worldstate pages.

## Tier 4 of the improvement plan: Kuva Lich data (added); DE's static feeds (checked, skipped)

- **Kuva Lich / Sister of Parvos auctions — added.** Confirmed live Lich
  trading uses the exact same v1 `/auctions/search` endpoint as Rivens
  (just `type=lich` instead of `type=riven` — same marketplace, same
  live-data guarantees), so `riven.py` gained a `search_liches()` method
  and a `LichAuction` dataclass rather than a whole new module. New
  `search_liches` chat tool, new `/api/liches/search` endpoint, and a
  second search section on the `/rivens` page (weapon, element, "has
  ephemera" filter). **Caveat, worth repeating:** the Riven fields come
  from a long-documented, stable schema; the Lich-specific fields
  (`element`, `having_ephemera`, `quirks`, `damage`) are inferred from the
  site's own search *query parameters*, not a fetched response body — a
  rougher guess than the Riven side. Confirm against a real response.
- **DE's "Weekly Riven Mods Trade Data" feed — checked, deliberately NOT
  implemented.** This looked like a great supplementary data source (an
  official DE feed of actual riven trade prices), and I found the exact
  URL (`www-static.warframe.com/repos/weeklyRivensPC.json`) and its full
  field schema. But the Warframe Wiki's own Riven Mods article states
  outright that **it hasn't been updated since 13 May 2024** — over two
  years stale as of this writing. Wiring in a feed that silently serves
  2024 data under a "weekly" label would be worse than not having the
  feature at all, so I stopped here rather than build on it.
- **DE's "Annual Warframe and Weapon Usage Data" feed — checked,
  deliberately NOT implemented.** Same reasoning: the most recent file I
  could confirm is from 2023 (`WarframeUsageData2023.json`), with nothing
  found for 2024, 2025, or 2026 despite the feed supposedly being annual.
  Freshness unverified, so skipped rather than guessed.

This closes out the original Tier 1-4 plan. Everything implemented across
all four tiers has been tested (mocked-payload unit tests for parsing
logic, end-to-end agent tool-calling tests with a mocked LLM, and a full
Flask route regression covering all 8 pages) — see the test files
referenced throughout this document for what's actually been verified
versus what still carries an open caveat.

## Tier 3 of the improvement plan: fixing builds.py (and a plan change worth reading)

The original plan called for hand-curating ~20-30 meta builds. **I changed
that plan mid-implementation** after a fresh search showed how much
Warframe's meta has moved since my training cutoff (Jan 2026) — Incarnon
Genesis reshaped the entire weapon tier list, several new frames released
(Dante, Citrine, Kullervo, Uriel, Cyte-09, Temple), new Arcane systems
landed. Writing 20+ builds from memory and presenting them as current would
have been exactly the kind of confident-but-stale content I've been
avoiding all session for API shapes — builds deserve the same standard.

So instead:

- **Structural fix (the actual bug):** builds moved out of two
  hardcoded `add_build()` calls in `app.py` into `ordis/data/builds.json`,
  loaded by `Builds` at construction. This was the real problem —
  hardcoding data in application wiring code instead of a data file made
  it impossible to maintain or extend without touching `app.py`.
- **Small, dated, confidence-tagged seed** instead of a large guessed one.
  6 frames, each tagged `confidence: "high"` (long-stable kit
  mechanics — Rhino's Iron Skin scaling, Saryn's Spores/Miasma loop, both
  confirmed still S-tier as of a July 2026 search) or `confidence:
  "directional"` (frames with heavy Arcane/system dependency I can't fully
  verify, like Dante and Mesa's exalted weapon). The seed file carries an
  `as_of` date and an explicit staleness warning, surfaced both in the UI
  and to the chat agent (which now must relay confidence/staleness rather
  than presenting every build with equal certainty — new system prompt
  rule).
- **Community submission path** — `Builds.submit_build()` persists to
  `data/community_builds.json` (separate from the read-only curated seed
  in the package), with a minimal `POST /api/builds/submit` endpoint and a
  form on the `/builds` page. No moderation pipeline; submissions are
  tagged `source: "community"` so they're visually distinguishable from
  the reviewed seed. This is the sustainable answer to "the meta changes
  every few months" — better than me re-guessing builds periodically.
- **New `/api/builds`** lists every frame with build data on file plus
  the seed's disclaimer metadata, and the `/builds` page now has a
  clickable frame browser instead of only supporting exact-name search.



- **`Market.get_price_history()`** — daily sell-price history (default 14
  days). **Same v1 exception as Riven support:** checked v2's docs
  directly and confirmed there's no price-statistics endpoint at all — the
  complete section list is Manifests, Orders, Groups, Users, Achievements,
  Auth, Dashboard, and "Dashboard" turned out to just be featured-items
  content for the mobile app, not price stats. Targets v1's
  `/items/{slug}/statistics` instead, isolated the same way as
  `riven.py`. Filters to sell-side entries only (mirrors the same
  buy/sell-contamination fix from the original pricing bug). New
  `/api/market/history/<slug>` endpoint, and the market page now shows a
  7-day average with a trend arrow next to each item's live sellers.
- **`DropTables.find_set()`** — groups every drop-table hit for a query
  under one summary: each component's rarity, ducat value, and best known
  farm source. Ducat values come from a small static table
  (Common=15/Uncommon=45/Rare=100) — this is a long-stable DE game rule,
  not fetched data, so it's hardcoded rather than pulled from an API that
  doesn't expose it anyway. **Explicitly cannot check what you already
  own** — there's no player-inventory data source available (WFM has no
  third-party OAuth yet), so this shows every matching component and
  where to get it, not a personalized checklist. New `/api/drops/set`
  endpoint and a "Set Planner" section on the `/drops` page.
- **Chat agent** — two new tools, `get_price_history` and `plan_set`,
  both verified end-to-end with a mocked LLM the same way `search_rivens`
  was.



Implements the #1 gap identified in the audit — Riven mod tooling, the
single most-requested feature category across real third-party Warframe
companion tools (AlecaFrame, FrameForge).

- **`ordis/riven.py`** — new adapter for Warframe Market riven auctions.
  **Deliberate exception to "prefer v2":** I checked v2's own docs
  (`docs.warframe.market`) and its sidebar lists no Auctions or Rivens
  section at all — only Manifests, Orders, Groups, Users, Achievements,
  Auth, Dashboard. Riven trading has lived on the stable, long-unchanged
  v1 API for years with no v2 equivalent yet, so this module targets v1
  specifically for this one feature, isolated the same way market.py
  isolates v2 — swap it the moment v2 ships an equivalent. Confirmed the
  actual v1 endpoint paths (`/v1/auctions/search`, `/v1/auctions/entry/{id}`,
  `/v1/auctions/popular`) via a community Kotlin wrapper's endpoint list.
  **Caveat:** I could not make a live call to confirm the current auction
  JSON shape from this environment — the parsed fields come from the
  long-documented, historically stable v1 schema used across multiple
  independent tools for years, not a live sample I fetched myself this
  session. Parsing is fully defensive (`.get()` everywhere) so a shape
  drift degrades gracefully rather than crashing.
- **Chat agent** — new `search_rivens` tool, same pattern as `find_drop`:
  the model must call it for any riven price/stat question rather than
  guessing. Verified end-to-end with a mocked LLM (tool call → real riven
  search → result fed back into context → grounded answer).
- **New `/rivens` page** — search by weapon, see live auctions ranked by
  price with stats, polarity, mastery requirement, reroll count, and
  seller.
- **New `/api/rivens/search`** endpoint backing both the page and the
  agent tool.

## Third batch (item registry grouping, 1999 Calendar found, market sellers still uncertain)

- **Item Hunter — no more repeated item name.** The grouped registry cards
  from the previous batch still repeated the item name once per nested
  location row. Fixed: the card header shows the item name once;
  everything nested inside now shows only the table-type badge, location,
  rotation, and chance — no repetition.
- **1999 Calendar / "Hex KIM rewards" — found and wired in.** Pulled
  WFCD's actual OpenAPI spec (`docs.warframestat.us/openapi.yaml`), which
  lists every real endpoint with its schema name. Confirmed `/pc/calendar`
  (schema `CalendarDto`) exists — this is the 1999/Höllvania/Hex reward
  calendar. Also found and added two more real endpoints that weren't
  wired in before: `weeklyChallenges` and `clanWeeklyInitiative`, plus
  `kuva` (Kuva Siphon/Flood missions). **Caveat:** I've confirmed these
  endpoints exist and added them, but I haven't seen a live response body
  for any of the three weekly-tracker ones, so they're rendered generically
  (whatever top-level fields come back) rather than with a
  purpose-built layout — tell me what the real response looks like and
  I'll build a proper renderer.
- **"Descendia" — still not found.** Went through the complete, official
  endpoint list this time (not just a live snapshot) and there is nothing
  resembling this name anywhere in it. I don't want to guess further and
  risk shipping something fabricated — if you have a source for this
  (wiki page, screenshot, patch notes), send it over.
- **Market seller names still uncertain.** Re-researched from multiple
  angles (OpenAPI spec excerpts, a Rust crate's working example showing
  `order.user.ingame_name`) and `ingame_name` remains the best-supported
  guess, already tried first. If it's still only showing status with no
  name, the exact field may differ for your platform/region, or the
  order-list endpoint may only return a reduced user object. Changed the
  fallback from a generic "unknown seller" to a short id fragment
  (`seller-xxxxxxxx`) so sellers are at least distinguishable from each
  other. **If you can grab one raw order object** (e.g. open
  `https://api.warframe.market/v2/orders/item/<any_slug>` in a browser and
  copy one entry from `data`), send it to me and I'll fix this properly
  instead of guessing again.

## Second batch (worldstate accuracy, market sellers, drop registry grouping)

All of these were checked against a **live fetch of `api.warframestat.us/pc`**
taken during this session, not assumed from docs:

- **Trader "222 hour" display** — the underlying countdown math was
  correct, but `fmtDuration()` only formatted `HH:MM:SS` with no day
  rollover, so a real ~9-day wait showed as a giant triple-digit hour
  count. Fixed to show `9d 06:15:22`-style output. Verified against the
  actual live Vault Trader countdown from the fetch.
- **Arbitration "none active"** — re-checked live: the API is still
  returning `expired: true` with epoch placeholder dates. Arbitrations
  rotate every 1-2 hours in-game and are almost never genuinely absent, so
  this looks like a real gap in WFCD's own upstream sync rather than a bug
  in this app's rendering — the code is reading the field correctly. The
  message was softened to say the feed reports none rather than asserting
  it as fact, with a nudge to check in-game if it persists.
- **Steel Path → renamed "Teshin Rotation"** per request. Also confirmed
  `remaining` is a pre-formatted string from the API (`"5d 11h 43m 58s"`)
  — now used directly instead of recomputed. **Confirmed `incursions` is a
  single object with only `{id, activation, expiry}` — no node names at
  all.** There's no way to show which nodes are running incursions from
  this field; the UI says so honestly instead of fabricating a node list.
- **Dark Sectors "none"** — confirmed live `darkSectors: []`, genuinely
  empty. This endpoint tracks the old Solar Rail conflict system, a
  feature removed from the game years ago — likely why it's always empty
  now. If "dark sector nodes" meant the regular star-chart "Dark Sector"
  mission tags instead, that's different data this API doesn't expose the
  same way — the UI now says this explicitly rather than just showing
  "none" as if it answered the question.
- **Recent News — expanded panel.** Was showing only the single latest
  item; now a dedicated panel lists the last 12 items sorted by date, each
  linked out.
- **Archon Hunt, Duviri Circuit choices, Archimedea — added.** All three
  confirmed present in the live payload as `archonHunt`, `duviriCycle.choices`
  (frame/weapon options for the week), and `archimedeas` respectively, and
  none of them were wired into the app before. Now full endpoints/panels.
- **"Descendia" and "1999 KIM rewards" — not found.** I searched the full
  live payload for anything resembling these and found nothing. Rather
  than guess at an endpoint name and risk shipping something that looks
  plausible but is fabricated, I'm flagging this: if you have a source
  (wiki page, patch notes) for what these refer to, share it and I'll wire
  them up properly.
- **Market: seller names + top 10 sellers per item.** New
  `Market.top_sellers()` and `/api/market/sellers/<slug>` return the 10
  cheapest live sell orders with seller name, platinum, quantity, and
  online status — replacing the single "lowest price" number. **Caveat:**
  I could not confirm the exact v2 field name for a seller's username from
  a raw payload (only post-processed wrapper libraries surfaced one, and
  they normalize it) — the code tries several plausible field names
  (`ingame_name`, `username`, `displayName`, ...) and falls back to
  "unknown seller" rather than guessing wrong silently. Worth confirming
  against a real response and tightening if the field name turns out to
  be something else.
- **Item Hunter: grouped registry.** `find_drop()` results are now grouped
  into one collapsible card per unique item, with every known location
  nested inside it, instead of a flat list that repeated the item name
  once per drop source (which was especially noisy for Prime parts with
  dozens of relic sources).

## Fixes from initial testing (July 2026)

- **`drops.py`** — live testing surfaced that `missionRewards` is more
  irregular than the reference doc implied: `rewards` is a dict keyed by
  rotation (`A`/`B`/`C`) for multi-rotation mission types, but a **plain
  flat list** for single-reward types (Capture, Assassination,
  Exterminate, ...). Both shapes are now handled. Also corrected the reward
  item field name from `item` to the actual `itemName`. Other flat tables
  are indexed best-effort and skipped (not crashed) if their shape doesn't
  match what we've verified.
- **`lore.py`** — the REST summary endpoint can return 200 with an empty
  `extract` for some titles. `get_summary()` now falls back to the
  MediaWiki `action=query&prop=extracts` API, which is more tolerant of
  redirects/title variants, before giving up.
- **`worldstate.py`** — expanded from 8 to 27 endpoints, covering the
  hourly/daily/weekly content that was missing: open-world cycles (Cetus,
  Vallis, Cambion, Zariman, Duviri, Earth), daily deals, flash sales,
  global upgrades, events, alerts, dark sectors, conclave challenges,
  persistent enemies (Liches/Sisters), sentient outposts, Simaris target,
  news, and the vault trader (distinct from Baro's void trader).
- **`market.py`** — `search_item()` now flattens the v2 `i18n.en.name`
  field into a `display_name` key so callers don't have to know about the
  i18n nesting.
- **`market.py` (search fix)** — live testing showed `search=<query>`
  returning unrelated items. Checked the v1 OpenAPI spec and every v2
  client library surveyed (Rust `wf-market`, Python `pywmapi` and
  `warframe-market.py`): **`/items` has no server-side search/filter
  parameter in either API version** — it only ever returns the full
  catalog, and an unrecognized query param is silently ignored rather than
  erroring. `search_item()` now fetches and caches the full item catalog
  once (a few thousand items, one request) and filters client-side by
  substring match on name/slug. First search per process is a bit heavier;
  every search after that is instant and local.
- **`drops.py` (relics — the big one)** — `find_drop()` was returning
  nothing for items that exist and are farmable (confirmed live: Voruna
  Prime, released April 8 2026, drops from Void Relics). Root cause:
  `relics` was dropped from the indexed table list entirely during the
  first fix pass and never re-added. Fetched `relics.json` live and
  confirmed its real shape — a flat list of `{tier, relicName, state,
  rewards: [{itemName, rarity, chance}]}` records, one level deeper than
  the other flat tables since reward items sit under a nested `rewards`
  key. Added dedicated indexing for it (location becomes e.g. `"Axi A21
  Relic"`, rotation becomes the refinement state — Intact/Exceptional/
  Flawless/Radiant). This matters a lot: nearly every Prime part in the
  game drops *only* from relics, so this table being unindexed meant
  `find_drop()` was blind to most Prime frames/weapons, silently.
- **`market.py` (every price showing ~1p — a real bug, not a coincidence)**
  — `get_price()` requested orders with an `order_type` query param, then
  labeled *every* order it got back with that requested type
  unconditionally, without ever checking what type the order actually was.
  Cross-referenced three independent v2 client implementations (the
  community `warframe_market` Rust crate's `PostOrder { r#type:
  Type::Sell }`, `wfm.py`'s parsed `Order` objects, and the v1→v2 field
  rename) and confirmed: v2 orders carry their real type under a field
  called `type` (v1 called it `order_type`), and `/orders/item/{slug}`
  returns buy **and** sell orders together — the same "no server-side
  filtering" pattern already found in `/items`. Because the code trusted
  the request instead of the response, buy orders (almost always priced
  near 1 platinum — buyers lowball) were being silently counted as sell
  orders, which is exactly why every single item was showing "1p lowest
  sell." Fixed to read the real `type` field per order and filter
  client-side. Verified against a mocked mixed buy/sell payload — sell
  orders (42p/45p/200p) and buy orders (1p/3p) are now correctly separated
  and `lowest_sell_price()` returns 42p instead of 1p.
- **`agent.py` (fabricated claims for open-ended questions)** — for
  broad questions like "what's the easiest plat farm right now", the model
  called a few tools but then padded the answer with plausible-sounding but
  unsourced claims ("demand fluctuates significantly", "acquired from
  sortie missions") that weren't in any tool result. Tightened the system
  prompt: the model must now answer using *only* facts that came back from
  a tool call, must pick concrete named candidates and check each one
  individually for open-ended questions, and must drop any claim it can't
  back with a tool result rather than writing plausible filler around it.

## Frontend

`app.py` (Flask) + `templates/index.html` + `static/style.css` +
`static/app.js`: a single-page operator dashboard styled after Warframe's
own Orokin/Tenno HUD — angular corner-cut panels, gold/cyan accents, and a
pulsing dual-ring "Ordis eye" in the header. Panels:

- **Open World Cycles** — Cetus/Vallis/Cambion/Zariman/Duviri state
- **Active Operations** — sortie, void trader, nightwave, fissures, arbitration, Darvo deal
- **Item Hunter** — search any item, see every known drop source ranked by chance
- **Market Relay** — search a tradable item, see live lowest sell price
- **Archive / Lore Terminal** — pull a short Ordis-voice-length summary of any topic
- **Loadout Archive** — curated builds per frame (seeded with two examples in `app.py`)

All calls are proxied through Flask (`/api/...`), so the browser never
talks to warframestat.us, warframe.market, or the wiki directly.

## Adapter → source map

| Adapter method | Source | Stability |
|---|---|---|
| `Worldstate.get_*()` | api.warframestat.us | stable |
| `DropTables.find_drop(item)` | drops.warframestat.us | static-ish dump, index at load |
| `Market.get_price(item)` / `search_item(name)` | docs.warframe.market v2 | pre-1.0, breaking changes possible |
| `Lore.get_summary(topic)` / `get_page(topic)` | wiki.warframe.com | stable |
| `Builds.get_build(frame)` | local DB, background Overframe enrichment | unofficial, best-effort |

## Next steps for whoever picks this up

- Wire real persistence for `drops.py`'s index and `builds.py`'s store
  (SQLite is plenty to start).
- Add retry/backoff + response caching around `market.py` given v2's
  instability.
- If/when Warframe Market ships OAuth for third-party clients, replace the
  legacy-v1 auth fallback noted in `market.py`.
- Layer the Ordis voice-gen + item-hunter tracker features on top of these
  adapters rather than inside them, so the data layer stays swappable.
