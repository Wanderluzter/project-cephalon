"""
Ordis conversational agent.

Turns a natural-language player question ("where can I farm Voruna Prime")
into real tool calls against the ORDIS data adapters — drops, worldstate,
market, lore, builds — then has the LLM answer using the actual results,
in Ordis' voice. The model never answers game-data questions from its own
memory; it's instructed to call a tool for anything factual, so answers are
grounded in live data instead of the model's (possibly stale or wrong)
training knowledge.

Backend: OpenRouter, OpenAI-compatible tool/function calling. See llm.py.
"""

import json
from typing import Any, Dict, List, Optional

from .builds import Builds
from .drops import DropTables
from .llm import LLMError, OpenRouterClient
from .lore import Lore
from .market import Market
from .riven import Riven
from .worldstate import Worldstate

ORDIS_SYSTEM_PROMPT = """\
You are ORDIS, a Cephalon assistant to a Warframe player (the "Operator"/"Tenno"). \
Your tone: clipped, precise, occasionally dryly sardonic — a machine intelligence that \
genuinely wants to help but finds some of the Operator's choices mildly exasperating. \
Never overdo it; one wry aside per answer at most.

Hard rules:
1. For ANY question involving current game data — drop locations, farm routes, drop \
chances, market prices, riven auction prices/stats, active world state (sortie, cycles, \
fissures, trader, etc.), lore/wiki facts, or Warframe builds — you MUST call the matching \
tool before answering. Never state a drop location, price, riven value, or lore fact from \
memory. The game changes too often and your training data is not reliable for this.
2. Answer using ONLY facts that came back from a tool call. Do not add supporting \
claims, context, or color that didn't come from a tool result — no "demand is high", \
"this is commonly farmed in sorties", "prices fluctuate", "check back often", or similar \
plausible-sounding filler. If you don't have a tool result backing a specific claim, \
leave the claim out rather than writing around the gap.
3. If a tool returns no results, say so plainly. Do not invent a plausible-sounding \
answer to fill the gap.
4. When a tool returns multiple drop sources, report the highest-chance ones first and \
mention the rotation letter when present.
5. For open-ended requests with no single obvious tool target (e.g. "what's a good \
plat farm right now", "what should I build"), pick a small number of concrete, named \
candidates and call a tool (get_market_price, find_drop, etc.) on each of them \
individually. Report only the numbers those calls actually returned — a ranked list of \
real prices/chances, not a narrative recommendation padded with unsourced reasoning \
about demand, difficulty, or popularity.
6. get_build results carry a `confidence` field ("high" or "directional") and a \
`data_as_of` date. Always relay this — for "directional" builds, explicitly tell the \
Operator it's a starting point to verify rather than a finished optimal build, and \
mention the as_of date if the build is more than a couple months old. Don't present a \
directional build with the same certainty as a high-confidence one.
7. Keep answers focused — a couple of sentences plus the concrete facts (location, \
chance, price) the Operator asked for. This is a HUD readout, not an essay.
8. If the question isn't about Warframe or doesn't need live data (small talk, \
clarifying questions), answer directly without calling a tool.
"""


def _worldstate_tool_schema() -> Dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "get_worldstate",
            "description": (
                "Get current live Warframe world state: sortie, nightwave, active "
                "fissures, open-world cycles (Cetus/Vallis/Cambion/Zariman/Duviri/Earth), "
                "void/vault trader, arbitration, invasions, daily deals, and more."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "endpoint": {
                        "type": "string",
                        "enum": sorted(Worldstate.ENDPOINTS.keys()),
                        "description": "Which piece of world state to fetch.",
                    }
                },
                "required": ["endpoint"],
            },
        },
    }


TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "find_drop",
            "description": (
                "Find where to farm/obtain a specific Warframe item. Returns every "
                "known drop source ranked by yield probability, with mission/location, "
                "drop chance, and rotation where applicable. Use this for ANY "
                "'where can I farm/get X' question."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "item": {
                        "type": "string",
                        "description": "Item name, e.g. 'Voruna Prime Systems' or just 'Voruna Prime'.",
                    }
                },
                "required": ["item"],
            },
        },
    },
    _worldstate_tool_schema(),
    {
        "type": "function",
        "function": {
            "name": "get_market_price",
            "description": "Get the current lowest live platinum sell price for a tradable item on Warframe Market.",
            "parameters": {
                "type": "object",
                "properties": {"item": {"type": "string", "description": "Item name to look up."}},
                "required": ["item"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_lore",
            "description": "Get a short lore/background summary for a Warframe topic (frame, character, questline, faction, etc), pulled from the Warframe Wiki.",
            "parameters": {
                "type": "object",
                "properties": {"topic": {"type": "string", "description": "Topic to look up, e.g. 'Rhino' or 'Story and History'."}},
                "required": ["topic"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_build",
            "description": "Get curated mod build(s)/loadout(s) on file for a given Warframe.",
            "parameters": {
                "type": "object",
                "properties": {"frame": {"type": "string", "description": "Warframe name, e.g. 'Rhino'."}},
                "required": ["frame"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_rivens",
            "description": (
                "Search live Riven mod auctions for a weapon on Warframe Market. Use for ANY "
                "'what's my riven worth', 'find me a riven for X', or riven price question."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "weapon": {"type": "string", "description": "Weapon name, e.g. 'War' or 'Braton Prime'."},
                    "buyout_policy": {
                        "type": "string",
                        "enum": ["direct", "with_buyout"],
                        "description": "Optional: restrict to auctions with an instant-buyout price.",
                    },
                    "sort_by": {
                        "type": "string",
                        "enum": ["price_asc", "price_desc"],
                        "description": "Sort order, default cheapest first.",
                    },
                },
                "required": ["weapon"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_liches",
            "description": (
                "Search live Kuva Lich / Sister of Parvos weapon auctions on Warframe Market. "
                "Use for 'what's a good Lich weapon roll worth' or ephemera-related questions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "weapon": {"type": "string", "description": "Weapon name, e.g. 'Kuva Kraken'. Optional — omit to search all."},
                    "element": {
                        "type": "string",
                        "description": "Elemental damage type, e.g. 'toxin', 'electricity', 'heat', 'viral'.",
                    },
                    "having_ephemera": {"type": "boolean", "description": "Restrict to auctions with an ephemera included."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_price_history",
            "description": (
                "Get recent daily sell-price history (up to ~14 days) for a tradable item. "
                "Use for 'is this a good time to sell/buy X' or 'has X's price been dropping' "
                "questions — this shows a trend, unlike get_market_price which is a live snapshot."
            ),
            "parameters": {
                "type": "object",
                "properties": {"item": {"type": "string", "description": "Item name to look up."}},
                "required": ["item"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "plan_set",
            "description": (
                "Plan a Prime set or item family: lists every matching component, its ducat "
                "value, and its best known farm source in one call. Use for 'what do I need for "
                "X set' or 'where do I farm all the pieces of X' — more efficient than calling "
                "find_drop once per component. Cannot check what the player already owns (no "
                "inventory access) — say so if asked about personal completion progress."
            ),
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Set or item family name, e.g. 'Voruna Prime'."}},
                "required": ["query"],
            },
        },
    },
]


class AgentError(RuntimeError):
    pass


class OrdisAgent:
    def __init__(
        self,
        llm: Optional[OpenRouterClient] = None,
        drops: Optional[DropTables] = None,
        worldstate: Optional[Worldstate] = None,
        market: Optional[Market] = None,
        lore: Optional[Lore] = None,
        builds: Optional[Builds] = None,
        riven: Optional[Riven] = None,
    ):
        self.llm = llm or OpenRouterClient()
        self.drops = drops if drops is not None else DropTables(auto_load=False)
        self.worldstate = worldstate or Worldstate()
        self.market = market or Market()
        self.lore = lore or Lore()
        self.builds = builds or Builds()
        self.riven = riven or Riven()

    # --- tool execution -----------------------------------------------------
    def _exec_tool(self, name: str, args: Dict[str, Any]) -> Any:
        try:
            if name == "find_drop":
                return self._tool_find_drop(args.get("item", ""))
            if name == "get_worldstate":
                return self.worldstate.call(args.get("endpoint", ""))
            if name == "get_market_price":
                return self._tool_market_price(args.get("item", ""))
            if name == "get_lore":
                return self._tool_lore(args.get("topic", ""))
            if name == "get_build":
                return self._tool_build(args.get("frame", ""))
            if name == "search_rivens":
                return self._tool_search_rivens(args)
            if name == "search_liches":
                return self._tool_search_liches(args)
            if name == "get_price_history":
                return self._tool_price_history(args.get("item", ""))
            if name == "plan_set":
                return self._tool_plan_set(args.get("query", ""))
            return {"error": f"unknown tool '{name}'"}
        except Exception as exc:  # noqa: BLE001 — tool errors go back to the model as data, not raised
            return {"error": str(exc)}

    def _tool_search_rivens(self, args: Dict[str, Any]) -> List[Dict[str, Any]]:
        weapon = args.get("weapon_url_name") or args.get("weapon")
        if not weapon:
            return {"error": "no weapon specified"}
        # Accept either a display name or a slug — normalize display-name-ish
        # input ("War", "Braton Prime") into WFM's slug format as a
        # best-effort fallback if it doesn't already look like a slug.
        weapon_slug = weapon.lower().replace(" ", "_") if " " in weapon or weapon != weapon.lower() else weapon
        auctions = self.riven.search(
            weapon_url_name=weapon_slug,
            buyout_policy=args.get("buyout_policy"),
            sort_by=args.get("sort_by", "price_asc"),
            limit=10,
        )
        return [
            {
                "weapon": a.weapon,
                "positive_stats": a.positive_stats,
                "negative_stat": a.negative_stat,
                "polarity": a.polarity,
                "mastery_level": a.mastery_level,
                "re_rolls": a.re_rolls,
                "buyout_price": a.buyout_price,
                "starting_price": a.starting_price,
                "seller": a.seller_name,
                "seller_status": a.seller_status,
            }
            for a in auctions
        ]

    def _tool_search_liches(self, args: Dict[str, Any]) -> List[Dict[str, Any]]:
        weapon = args.get("weapon")
        weapon_slug = None
        if weapon:
            weapon_slug = weapon.lower().replace(" ", "_") if " " in weapon or weapon != weapon.lower() else weapon
        liches = self.riven.search_liches(
            weapon_url_name=weapon_slug,
            element=args.get("element"),
            having_ephemera=args.get("having_ephemera"),
            limit=10,
        )
        return [
            {
                "weapon": l.weapon,
                "element": l.element,
                "has_ephemera": l.has_ephemera,
                "ephemera": l.ephemera,
                "quirks": l.quirks,
                "damage": l.damage,
                "buyout_price": l.buyout_price,
                "starting_price": l.starting_price,
                "seller": l.seller_name,
                "seller_status": l.seller_status,
            }
            for l in liches
        ]

    def _tool_price_history(self, item: str) -> Dict[str, Any]:
        if not item:
            return {"error": "no item specified"}
        results = self.market.search_item(item)
        if not results:
            return {"error": f"no tradable item matching '{item}'"}
        best = results[0]
        points = self.market.get_price_history(best["slug"], days=14)
        return {
            "item": best.get("display_name"),
            "slug": best.get("slug"),
            "history": [
                {"date": p.date, "avg_price": p.avg_price, "median": p.median, "volume": p.volume}
                for p in points
            ],
        }

    def _tool_plan_set(self, query: str) -> Dict[str, Any]:
        if not query:
            return {"error": "no set/item specified"}
        if not self.drops._raw:
            self.drops.refresh()
        return self.drops.find_set(query)

    def _tool_find_drop(self, item: str) -> List[Dict[str, Any]]:
        if not item:
            return {"error": "no item specified"}
        if not self.drops._raw:  # lazy-load the ~20MB dump on first real use
            self.drops.refresh()
        hits = self.drops.find_drop(item)
        hits_sorted = sorted(hits, key=lambda h: (h.chance is None, -(h.chance or 0)))[:10]
        return [
            {"item": h.item, "table": h.table, "location": h.location, "chance": h.chance, "rotation": h.rotation}
            for h in hits_sorted
        ]

    def _tool_market_price(self, item: str) -> Dict[str, Any]:
        if not item:
            return {"error": "no item specified"}
        results = self.market.search_item(item)
        if not results:
            return {"error": f"no tradable item matching '{item}'"}
        best = results[0]
        price = self.market.lowest_sell_price(best["slug"], online_only=False)
        return {
            "item": best.get("display_name"),
            "slug": best.get("slug"),
            "lowest_sell_platinum": price,
            "other_matches": [r.get("display_name") for r in results[1:5]],
        }

    def _tool_lore(self, topic: str) -> Dict[str, Any]:
        if not topic:
            return {"error": "no topic specified"}
        summary = self.lore.get_summary(topic)
        if not summary:
            hits = self.lore.search(topic, limit=1)
            if hits:
                summary = self.lore.get_summary(hits[0]["title"])
        return {"topic": topic, "summary": summary or "no archive entry found under that title"}

    def _tool_build(self, frame: str) -> List[Dict[str, Any]]:
        if not frame:
            return {"error": "no frame specified"}
        results = self.builds.get_build(frame)
        as_of = self.builds.meta.get("as_of")
        return [
            {
                "name": b.name, "mods": b.mods, "forma_count": b.forma_count,
                "notes": b.notes, "confidence": b.confidence, "source": b.source,
                "data_as_of": as_of,
            }
            for b in results
        ]

    # --- conversation loop ----------------------------------------------------
    def ask(
        self,
        user_message: str,
        history: Optional[List[Dict[str, str]]] = None,
        max_tool_rounds: int = 4,
    ) -> Dict[str, Any]:
        """Run the tool-calling loop for one user turn.

        `history` is a flat list of {"role": "user"|"assistant", "content": str}
        from prior turns (no tool-call bookkeeping needed between turns — each
        call rebuilds its own tool exchange fresh).

        Returns {"reply": str, "tool_calls": [{"tool":..., "args":..., "result":...}, ...]}
        """
        messages: List[Dict[str, Any]] = [{"role": "system", "content": ORDIS_SYSTEM_PROMPT}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        tool_trace: List[Dict[str, Any]] = []

        for _ in range(max_tool_rounds):
            reply = self.llm.chat(messages, tools=TOOLS)
            tool_calls = reply.get("tool_calls")
            if not tool_calls:
                return {"reply": reply.get("content", "") or "", "tool_calls": tool_trace}

            messages.append({"role": "assistant", "content": reply.get("content"), "tool_calls": tool_calls})
            for call in tool_calls:
                fn_name = call["function"]["name"]
                raw_args = call["function"].get("arguments") or "{}"
                try:
                    fn_args = json.loads(raw_args)
                except json.JSONDecodeError:
                    fn_args = {}
                result = self._exec_tool(fn_name, fn_args)
                tool_trace.append({"tool": fn_name, "args": fn_args, "result": result})
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "content": json.dumps(result)[:4000],  # guard against oversized payloads
                    }
                )

        # Ran out of tool rounds — force a final answer without further tools
        # rather than looping forever.
        final = self.llm.chat(messages, tools=None)
        return {"reply": final.get("content", "") or "", "tool_calls": tool_trace}
