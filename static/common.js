// Project ORDIS — shared across all pages (clock + persistent chat drawer).

const $ = (sel) => document.querySelector(sel);

function tickClock() {
  const el = $('#clock');
  if (!el) return;
  const now = new Date();
  el.textContent = now.toUTCString().split(' ')[4] + ' UTC';
}
setInterval(tickClock, 1000);
tickClock();

// ---------- Chat (persists across pages via sessionStorage) ----------
const CHAT_HISTORY_KEY = 'ordis_chat_history';
const CHAT_OPEN_KEY = 'ordis_chat_open';

function loadChatHistory() {
  try {
    return JSON.parse(sessionStorage.getItem(CHAT_HISTORY_KEY) || '[]');
  } catch {
    return [];
  }
}
function saveChatHistory(history) {
  sessionStorage.setItem(CHAT_HISTORY_KEY, JSON.stringify(history));
}

function addBubble(role, text, traceHtml = '') {
  const log = $('#chat-log');
  if (!log) return null;
  const div = document.createElement('div');
  div.className = `chat-bubble chat-bubble--${role === 'user' ? 'user' : 'ordis'}`;
  div.innerHTML = `
    <div class="chat-bubble__author">${role === 'user' ? 'Operator' : 'ORDIS'}</div>
    <div class="chat-bubble__text"></div>
    ${traceHtml}`;
  div.querySelector('.chat-bubble__text').textContent = text; // textContent only — no HTML injection from model output
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
  return div;
}

function traceSummaryHtml(toolCalls) {
  if (!toolCalls || !toolCalls.length) return '';
  const lines = toolCalls.map((t) => `${t.tool}(${JSON.stringify(t.args)})`).join('\n');
  const escaped = lines.replace(/</g, '&lt;');
  return `<details class="chat-bubble__trace"><summary>data pulled (${toolCalls.length})</summary><pre>${escaped}</pre></details>`;
}

function renderStoredHistory() {
  const log = $('#chat-log');
  if (!log) return;
  const history = loadChatHistory();
  if (!history.length) return; // keep the default greeting bubble
  log.innerHTML = '';
  for (const turn of history) {
    addBubble(turn.role, turn.content, traceSummaryHtml(turn.tool_calls));
  }
}

async function checkChatStatus() {
  const badge = $('#chat-status-badge');
  const toggleBadge = $('#chat-toggle-status');
  try {
    const res = await fetch('/api/chat/status');
    const data = await res.json();
    const cls = `status-dot ${data.available ? 'status-dot--ok' : 'status-dot--warn'}`;
    if (badge) badge.className = cls;
    if (toggleBadge) toggleBadge.className = cls;
    return data.available;
  } catch {
    if (badge) badge.className = 'status-dot status-dot--warn';
    if (toggleBadge) toggleBadge.className = 'status-dot status-dot--warn';
    return false;
  }
}

const CHAT_HIDDEN_KEY = 'ordis_chat_hidden'; // localStorage — persists across sessions, unlike open/closed which is per-tab

function initChatWidget() {
  const widget = $('#chat-widget');
  const toggle = $('#chat-toggle');
  const drawer = $('#chat-drawer');
  const form = $('#chat-form');
  const clearBtn = $('#chat-clear');
  const hideBtn = $('#chat-hide');
  const restoreBtn = $('#chat-restore');
  const input = $('#chat-input');
  if (!toggle || !drawer || !form) return;

  renderStoredHistory();
  checkChatStatus();

  function setHidden(hidden) {
    if (widget) widget.hidden = hidden;
    if (restoreBtn) restoreBtn.hidden = !hidden;
    localStorage.setItem(CHAT_HIDDEN_KEY, hidden ? '1' : '0');
    if (hidden) setOpen(false); // don't leave the drawer "open" underneath a hidden widget
  }

  function setOpen(open) {
    drawer.hidden = !open;
    toggle.setAttribute('aria-expanded', String(open));
    sessionStorage.setItem(CHAT_OPEN_KEY, open ? '1' : '0');
    if (open) input?.focus();
  }

  const startHidden = localStorage.getItem(CHAT_HIDDEN_KEY) === '1';
  setHidden(startHidden);

  const isOpen = sessionStorage.getItem(CHAT_OPEN_KEY) === '1';
  if (isOpen && !startHidden) {
    drawer.hidden = false;
    toggle.setAttribute('aria-expanded', 'true');
  }

  toggle.addEventListener('click', () => setOpen(drawer.hidden));
  hideBtn?.addEventListener('click', () => setHidden(true));
  restoreBtn?.addEventListener('click', () => {
    setHidden(false);
    setOpen(true);
  });

  // Keyboard: "/" opens the chat from anywhere (un-hiding it first if it
  // was fully hidden) unless already typing in a field. Escape closes it.
  document.addEventListener('keydown', (e) => {
    if (e.key === '/' && (drawer.hidden || (widget && widget.hidden))) {
      const tag = (e.target.tagName || '').toLowerCase();
      if (tag === 'input' || tag === 'textarea' || tag === 'select') return;
      e.preventDefault();
      if (widget && widget.hidden) setHidden(false);
      setOpen(true);
    } else if (e.key === 'Escape' && !drawer.hidden) {
      setOpen(false);
      toggle.focus();
    }
  });

  clearBtn?.addEventListener('click', () => {
    sessionStorage.removeItem(CHAT_HISTORY_KEY);
    $('#chat-log').innerHTML = `
      <div class="chat-bubble chat-bubble--ordis">
        <div class="chat-bubble__author">ORDIS</div>
        <div class="chat-bubble__text">Channel cleared, Operator.</div>
      </div>`;
  });

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const input = $('#chat-input');
    const message = input.value.trim();
    if (!message) return;
    input.value = '';

    const history = loadChatHistory();
    addBubble('user', message);
    history.push({ role: 'user', content: message });
    saveChatHistory(history);

    const thinking = addBubble('ordis', '');
    thinking.querySelector('.chat-bubble__text').innerHTML = '<span class="typing-dots"><span></span><span></span><span></span></span>';

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, history: history.slice(0, -1).map(({ role, content }) => ({ role, content })) }),
      });
      const data = await res.json();
      thinking.remove();
      if (data.error) {
        addBubble('ordis', `Channel error: ${data.error}`);
        return;
      }
      const bubble = addBubble('ordis', data.reply || '(no response)');
      if (data.tool_calls && data.tool_calls.length) {
        bubble.insertAdjacentHTML('beforeend', traceSummaryHtml(data.tool_calls));
      }
      const savedHistory = loadChatHistory();
      savedHistory.push({ role: 'assistant', content: data.reply || '', tool_calls: data.tool_calls || [] });
      saveChatHistory(savedHistory);
    } catch (err) {
      thinking.remove();
      addBubble('ordis', `Channel error: ${err.message}`);
    }
  });
}

document.addEventListener('DOMContentLoaded', initChatWidget);
document.addEventListener('DOMContentLoaded', initThemeSwitcher);

function initThemeSwitcher() {
  const buttons = document.querySelectorAll('[data-theme-choice]');
  if (!buttons.length) return;
  const current = localStorage.getItem('ordis_theme') || 'og';

  function applyTheme(theme) {
    if (theme === 'og') {
      document.documentElement.removeAttribute('data-theme');
    } else {
      document.documentElement.setAttribute('data-theme', theme);
    }
    localStorage.setItem('ordis_theme', theme);
    buttons.forEach((b) => b.classList.toggle('active', b.dataset.themeChoice === theme));
  }

  buttons.forEach((btn) => {
    btn.addEventListener('click', () => applyTheme(btn.dataset.themeChoice));
  });
  applyTheme(current); // sync button active-state (theme itself already applied inline in <head>)
}

// ---------- Shared helpers: correct field names + local-ticking timers ----------
// Cycles are only fetched once/day (server-cached); the countdown itself
// ticks locally from each cycle's `expiry` timestamp so we don't need to
// keep re-fetching just to update a clock.

function capitalize(s) {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
}

function msUntil(iso) {
  return new Date(iso).getTime() - Date.now();
}

function fmtDuration(ms) {
  if (ms <= 0) return '00:00:00';
  const totalSec = Math.floor(ms / 1000);
  const days = Math.floor(totalSec / 86400);
  const h = Math.floor((totalSec % 86400) / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  const s = totalSec % 60;
  const hms = [h, m, s].map((n) => String(n).padStart(2, '0')).join(':');
  return days > 0 ? `${days}d ${hms}` : hms;
}

// Central 1s ticker. Register {expiryIso, onTick(remainingMs), onZero?}.
// If onZero isn't provided, it defaults to triggerGlobalRefresh() below —
// so ANY countdown reaching zero triggers a real data refresh by default,
// not just a frozen "00:00:00" display. Combined with the worldstate
// cache fix (payload's own expiry invalidates the cache even within the
// nominal TTL), this means a cycle/sortie/trader timer that hits zero
// actually shows the new state on its next refresh instead of repeating
// stale data.
let _globalRefreshFn = null;
let _refreshDebounceTimer = null;
function setGlobalRefreshHandler(fn) {
  _globalRefreshFn = fn;
}
function triggerGlobalRefresh() {
  if (!_globalRefreshFn) return;
  clearTimeout(_refreshDebounceTimer);
  // Small delay: (a) coalesces multiple timers hitting zero in the same
  // tick into one refresh instead of several, (b) gives the backend a
  // moment past the exact boundary in case the upstream API itself needs
  // a second to reflect the new state.
  _refreshDebounceTimer = setTimeout(() => _globalRefreshFn(), 1500);
}

const _countdowns = [];
function registerCountdown(expiryIso, onTick, onZero) {
  const entry = { expiryIso, onTick, onZero: onZero || triggerGlobalRefresh, firedZero: false };
  _countdowns.push(entry);
  onTick(msUntil(expiryIso));
  return entry;
}
function clearCountdowns() {
  _countdowns.length = 0;
}
setInterval(() => {
  for (const c of _countdowns) {
    const remaining = msUntil(c.expiryIso);
    c.onTick(remaining);
    if (remaining <= 0 && !c.firedZero) {
      c.firedZero = true;
      c.onZero?.();
    }
  }
}, 1000);

function dataRow(label, value, cls = '') {
  const div = document.createElement('div');
  div.className = 'data-row';
  const l = document.createElement('span');
  l.className = 'data-row__label';
  l.textContent = label;
  const v = document.createElement('span');
  v.className = `data-row__value ${cls}`;
  v.textContent = value;
  div.appendChild(l);
  div.appendChild(v);
  return div;
}

// Cycle rendering: CONFIRMED against a live fetch that `state` is always
// present and authoritative (day/night/warm/cold/fass/vome/grineer/corpus/
// mood name) — never derive it from `isDay`, which doesn't even exist on
// cambionCycle/vallisCycle/duviriCycle. `timeLeft` from the server is also
// NOT always present (vallisCycle/duviriCycle omit it) — compute remaining
// time from `expiry` locally instead, and keep it ticking every second
// without re-fetching.
function buildCycleRow(label, cycleObj) {
  const valueSpan = document.createElement('span');
  valueSpan.className = 'data-row__value data-row__value--highlight';
  const row = dataRow(label, '');
  row.replaceChild(valueSpan, row.querySelector('.data-row__value'));

  if (!cycleObj || cycleObj.error) {
    valueSpan.textContent = 'unavailable';
    valueSpan.className = 'data-row__value data-row__value--warn';
    return row;
  }
  const state = cycleObj.state ? capitalize(cycleObj.state) : '—';
  if (cycleObj.expiry) {
    registerCountdown(cycleObj.expiry, (ms) => {
      valueSpan.textContent = `${state} · ${fmtDuration(ms)}`;
    });
  } else {
    valueSpan.textContent = state;
  }
  return row;
}

// Trader (void/vault): CONFIRMED there is no `active` boolean field on
// either — status must be derived from now vs activation/expiry.
function traderStatus(trader) {
  if (!trader || trader.error || !trader.activation || !trader.expiry) return 'unknown';
  const now = Date.now();
  const act = new Date(trader.activation).getTime();
  const exp = new Date(trader.expiry).getTime();
  if (now < act) return 'arriving';
  if (now < exp) return 'active';
  return 'departed';
}

// Arbitration: CONFIRMED via a live fetch that the API can return a
// placeholder object with `expired: true` and epoch/max-date timestamps.
// Arbitrations rotate roughly every 1-2 hours in-game and are very rarely
// truly absent, so a persistent `expired: true` here is more likely a
// sync gap in WFCD's own upstream feed than a real "nothing is active"
// state — the message reflects that instead of asserting it as fact.
function buildArbitrationRow(arb) {
  if (!arb || arb.error || arb.expired) {
    return dataRow('Arbitration', "feed reports none — check in-game if this persists");
  }
  return dataRow('Arbitration', arb.node || '—', 'data-row__value--highlight');
}

// Improved drop-tracker visualization: table-type badge, chance bar,
// rotation tag. Called ONLY inside a grouped registry card (see
// renderGroupedDropResults below), so it deliberately does NOT repeat the
// item name — that already lives in the card header. Only the
// drop-specific details (location/relic, rotation, chance) are shown here.
function renderDropResult(h) {
  const div = document.createElement('div');
  div.className = 'drop-result';

  const badgeCls = h.table === 'relics' ? 'drop-result__badge--relics'
    : h.table === 'missionRewards' ? 'drop-result__badge--missionRewards' : '';
  const badgeLabel = h.table === 'relics' ? 'RELIC' : h.table === 'missionRewards' ? 'MISSION' : (h.table || '').toUpperCase();
  const rot = h.rotation ? ` · ${h.rotation}` : '';
  const chance = h.chance != null ? h.chance : null;
  const barPct = chance != null ? Math.max(2, Math.min(100, chance)) : 0;

  div.innerHTML = `
    <div class="drop-result__main">
      <div class="drop-result__title"><span class="drop-result__badge ${badgeCls}">${badgeLabel}</span>${h.location || 'unknown location'}${rot}</div>
    </div>
    <div class="drop-result__chance-wrap">
      <div class="drop-result__chance-val">${chance != null ? chance + '%' : 'n/a'}</div>
      <div class="drop-result__bar-track"><div class="drop-result__bar-fill" style="width:${barPct}%"></div></div>
    </div>`;
  return div;
}

// One registry card per unique item, every known location nested inside
// it — instead of a flat list repeating the item name once per source.
// Each card is collapsible so a heavily-farmed item (dozens of relic
// sources) doesn't dominate the results view.
function renderGroupedDropResults(hits) {
  const groups = new Map(); // item name -> hits[]
  for (const h of hits) {
    const key = h.item;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(h);
  }

  const container = document.createElement('div');
  let firstCard = true;
  for (const [item, itemHits] of groups) {
    const sorted = [...itemHits].sort((a, b) => {
      if (a.chance == null) return 1;
      if (b.chance == null) return -1;
      return b.chance - a.chance;
    });
    const best = sorted[0];
    const bestChance = best.chance != null ? `${best.chance}%` : 'n/a';

    const card = document.createElement('details');
    card.className = 'drop-registry-card';
    if (firstCard) { card.open = true; firstCard = false; }

    const summary = document.createElement('summary');
    summary.className = 'drop-registry-card__summary';
    summary.innerHTML = `
      <span class="drop-registry-card__name">${item}</span>
      <span class="drop-registry-card__meta">${sorted.length} location${sorted.length === 1 ? '' : 's'} · best ${bestChance}</span>`;
    card.appendChild(summary);

    const body = document.createElement('div');
    body.className = 'drop-registry-card__body';
    for (const h of sorted) body.appendChild(renderDropResult(h));
    card.appendChild(body);

    container.appendChild(card);
  }
  return container;
}
