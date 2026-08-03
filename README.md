# 🛸 Project ORDIS — Data Integration Layer

![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)
![Framework](https://img.shields.io/badge/framework-Flask-green)
![Theme](https://img.shields.io/badge/theme-Orokin%2FTenno%20HUD-gold)
![License](https://img.shields.io/badge/license-MIT-informational)

An all-knowing **Warframe** assistant needs a clean, isolated adapter for every external data source it depends on. **Project ORDIS** is that layer: small, resilient clients built to survive upstream updates without taking down the rest of your application.

Built as a fresh implementation based on the **July 2026 data-source reference** covering Worldstate, Drop Tables, Warframe Market, Wiki Lore, and Overframe Builds.

---

## 📑 Table of Contents

- [Features](#-features)
- [Project Layout](#-project-layout)
- [Getting Started](#-getting-started)
- [Chat Agent — "Direct Channel"](#-chat-agent--direct-channel)
- [Architecture & Design](#-architecture--design)

---

## ⚡ Features

* **Resilient Data Adapters:** Isolated clients wrapping standard Warframe APIs with TTL caching, error boundaries, and fallbacks.
* **Orokin/Tenno HUD Dashboard:** Full Flask web frontend themed with custom HUD styling, real-time tickers, and interactive search tools.
* **Ordis AI Agent:** Function-calling LLM agent via OpenRouter that **must** execute backend tools before answering factual queries—zero hallucinations.
* **Zero-CORS Architecture:** Server-side proxying in `app.py` ensures external API calls are safely executed without leaking credentials or triggering cross-origin issues.

---

## 📂 Project Layout

```text
project_ordis/
├── README.md
├── requirements.txt
├── .env.example              # Copy to .env, set OPENROUTER_API_KEY
├── .gitignore
├── main.py                   # CLI demo / smoke test for adapters
├── app.py                    # Flask backend, page routes, weekly-image scheduler
├── data/
│   └── community_builds.json # Persisted community build submissions (auto-created)
├── templates/
│   ├── base.html             # Shared layout: header, nav, chat drawer include
│   ├── chat_widget.html      # Persistent chat drawer included on every page
│   ├── index.html            # / — Summarized "generalist" overview
│   ├── worldstate.html       # /worldstate — Full cycles/sortie/traders/etc.
│   ├── drops.html            # /drops — Item hunter + set planner
│   ├── market.html           # /market — Market relay + price history
│   ├── rivens.html           # /rivens — Riven auction search
│   ├── lore.html             # /lore — Full archive terminal
│   ├── builds.html           # /builds — Loadout archive + submission form
│   └── weekly.html           # /weekly — Generated digest image
├── static/
│   ├── style.css             # Orokin/Tenno HUD-styled theme
│   ├── common.js             # Clock, chat widget, countdown ticker, render helpers
│   ├── generated/            # Output location for weekly_digest.png
│   └── js/
│       ├── overview.js       # Per-page logic
│       ├── worldstate.js
│       ├── drops.js
│       ├── market.js
│       ├── rivens.js
│       ├── lore.js
│       ├── builds.js
│       └── weekly.js
└── ordis/
    ├── __init__.py
    ├── config.py              # Base URLs, timeouts, platform, OpenRouter defaults
    ├── worldstate.py          # api.warframestat.us wrapper + per-endpoint TTL cache
    ├── drops.py               # drops.warframestat.us wrapper + set/ducat planner
    ├── market.py              # docs.warframe.market v2 + v1 price-history exception
    ├── riven.py               # api.warframe.market v1 auction client
    ├── lore.py                # wiki.warframe.com client
    ├── builds.py              # Curated JSON seed + community submission handling
    ├── llm.py                 # OpenRouter chat-completions client
    ├── agent.py               # Tool-calling chat agent ("Ordis")
    ├── imagegen.py            # Weekly digest PNG renderer (Pillow)
    └── data/
        └── builds.json        # Curated build seed data
````
## 🚀 Getting Started
Prerequisites
Python 3.10+
````
pip package manager

Installation
Clone the repository:

Bash
git clone [https://github.com/your-username/project-ordis.git](https://github.com/your-username/project-ordis.git)
cd project-ordis
Install dependencies:

Bash
pip install -r requirements.txt
Running the Project
1. Quick Adapter Check (CLI Smoke Test)
Run a quick test against all adapters directly in your terminal:

Bash
python main.py
2. Full Dashboard & Web App
Start the Flask web application:

Bash
python app.py
Open http://127.0.0.1:5000 in your browser.
````

💡 Note: app.py handles all external API calls server-side. No credentials are visible in client code, and no CORS issues occur.

💬 Chat Agent — "Direct Channel"
Project ORDIS includes an AI conversational agent designed to act as your ship cephalon. The model is strictly grounded via tool calling—it cannot guess factual data.

Example: Asking "Where can I farm Voruna Prime?" forces the agent to invoke find_drop("Voruna Prime") against the live drop-table index, responding only with verified mission, chance, and rotation data.

Enabling the Chat Agent
Copy the environment template:

Bash
cp .env.example .env
Open .env and insert your OpenRouter API key:

Code snippet
OPENROUTER_API_KEY=sk-or-v1-...
Restart app.py.

Indicator Status Bar
The chat panel (Ordis // Direct Channel) includes an auto-detecting status indicator:

🟢 / 🔵 Cyan: Agent active and ready.

🔴 Red: No API key found (the rest of the dashboard remains fully operational).

ℹ️ .env is parsed automatically via a built-in loader (python-dotenv not required). Real environment variables take priority over .env entries.

## 🛠️ Architecture & Design
Agent Mechanics (ordis/llm.py + ordis/agent.py)
llm.py: A lightweight client built for OpenRouter's /chat/completions API supporting standard tool/function calls. Model selection can be customized via the OPENROUTER_MODEL environment variable.

agent.py: Wraps backend methods into five discrete tools:

find_drop

get_worldstate

get_market_price

get_lore

get_build

Safeguards: System prompts require tool verification for all factual assertions. The agent execution loop is capped at a maximum of 4 tool rounds to prevent infinite loops.

API Endpoints (app.py)
POST /api/chat — Accepts {"message": str, "history": [...]} and returns {"reply": str, "tool_calls": [...]}.

GET /api/chat/status — Endpoint consumed by the frontend to display agent availability.

Transparency Trace: The UI chat widget displays a collapsible "data pulled" trace under each reply, allowing users to inspect exact tool calls and parameters executed by the backend.
