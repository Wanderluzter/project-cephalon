// Project ORDIS — Overview (generalist summary) page.

async function loadCycles() {
  const el = $('#cycles');
  clearCountdowns();
  try {
    const res = await fetch('/api/worldstate/all');
    const data = await res.json();
    el.innerHTML = '';

    const cycles = [
      ['Cetus (Earth)', data['cetus-cycle']],
      ['Orb Vallis (Venus)', data['vallis-cycle']],
      ['Cambion Drift (Deimos)', data['cambion-cycle']],
      ['Zariman', data['zariman-cycle']],
      ['Duviri', data['duviri-cycle']],
    ];
    for (const [label, cycle] of cycles) {
      el.appendChild(buildCycleRow(label, cycle));
    }
    renderActiveOps(data);
  } catch (e) {
    el.innerHTML = `<div class="error-text">Link interrupted: ${e.message}</div>`;
  }
}

function renderActiveOps(data) {
  const el = $('#world-state');
  el.innerHTML = '';

  const sortie = data.sortie;
  if (sortie && !sortie.error) {
    el.appendChild(dataRow('Sortie boss', sortie.boss || '—'));
    if (sortie.expiry) {
      const row = dataRow('Sortie ends', '');
      const valueEl = row.querySelector('.data-row__value');
      registerCountdown(sortie.expiry, (ms) => { valueEl.textContent = fmtDuration(ms); });
      el.appendChild(row);
    }
  }

  const trader = data['void-trader'];
  if (trader && !trader.error) {
    const status = traderStatus(trader);
    const label = status === 'active' ? `on location — ${trader.location || ''}` : status;
    el.appendChild(dataRow("Baro Ki'Teer", label, status === 'active' ? 'data-row__value--highlight' : ''));
  }

  const nightwave = data.nightwave;
  if (nightwave && !nightwave.error && Array.isArray(nightwave.activeChallenges)) {
    el.appendChild(dataRow('Nightwave challenges', nightwave.activeChallenges.length));
  }

  const fissures = data.fissures;
  if (Array.isArray(fissures)) {
    el.appendChild(dataRow('Active fissures', fissures.length, 'data-row__value--highlight'));
  }

  el.appendChild(buildArbitrationRow(data.arbitration));

  const deals = data['daily-deals'];
  if (Array.isArray(deals) && deals.length) {
    const d = deals[0];
    const label = d.salePrice != null ? `${d.item} — ${d.salePrice}cr (${d.discount}% off)` : d.item;
    el.appendChild(dataRow('Darvo deal', label, 'data-row__value--highlight'));
  }

  if (!el.children.length) {
    el.innerHTML = '<div class="hint">No active operations reported.</div>';
  }
}

// ---------- Item hunter (mini) ----------
$('#hunter-form')?.addEventListener('submit', async (e) => {
  e.preventDefault();
  const item = $('#hunter-input').value.trim();
  const el = $('#hunter-results');
  if (!item) return;
  el.innerHTML = '<div class="loading">Cross-referencing drop tables&hellip;</div>';
  try {
    const res = await fetch(`/api/drops/find?item=${encodeURIComponent(item)}`);
    const hits = await res.json();
    if (hits.error) throw new Error(hits.error);
    if (!hits.length) {
      el.innerHTML = '<div class="hint">No known source found. Try a shorter or partial name.</div>';
      return;
    }
    el.innerHTML = '';
    el.appendChild(renderGroupedDropResults(hits.slice(0, 20)));
  } catch (err) {
    el.innerHTML = `<div class="error-text">Scan failed: ${err.message}</div>`;
  }
});

// ---------- Market (mini) ----------
$('#market-form')?.addEventListener('submit', async (e) => {
  e.preventDefault();
  const q = $('#market-input').value.trim();
  const el = $('#market-results');
  if (!q) return;
  el.innerHTML = '<div class="loading">Querying relay&hellip;</div>';
  try {
    const res = await fetch(`/api/market/search?q=${encodeURIComponent(q)}`);
    const items = await res.json();
    if (items.error) throw new Error(items.error);
    if (!items.length) {
      el.innerHTML = '<div class="hint">No matching tradable item.</div>';
      return;
    }
    el.innerHTML = '';
    for (const item of items.slice(0, 5)) {
      const div = document.createElement('div');
      div.className = 'result-item';
      const iconHtml = item.image_url
        ? `<img src="${item.image_url}" alt="" class="result-item__icon" onerror="console.warn('item icon failed to load:', this.src); this.remove()">`
        : '';
      div.innerHTML = `
        ${iconHtml}
        <div class="result-item__title">${item.name || item.slug}</div>
        <div class="result-item__chance" data-slug="${item.slug}">fetching price&hellip;</div>`;
      el.appendChild(div);
      fetchPrice(item.slug, div.querySelector('.result-item__chance'));
    }
  } catch (err) {
    el.innerHTML = `<div class="error-text">Query failed: ${err.message}</div>`;
  }
});

async function fetchPrice(slug, targetEl) {
  try {
    const res = await fetch(`/api/market/price/${encodeURIComponent(slug)}`);
    const data = await res.json();
    targetEl.textContent = data.lowest_sell_platinum != null ? `${data.lowest_sell_platinum}p lowest sell` : 'no active sell orders';
  } catch {
    targetEl.textContent = 'price unavailable';
  }
}

// ---------- Lore (mini) ----------
$('#lore-form')?.addEventListener('submit', async (e) => {
  e.preventDefault();
  const topic = $('#lore-input').value.trim();
  const el = $('#lore-output');
  if (!topic) return;
  el.innerHTML = '<div class="loading">Recalling archive fragment&hellip;</div>';
  try {
    const res = await fetch(`/api/lore/summary?topic=${encodeURIComponent(topic)}`);
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    if (!data.summary) {
      el.innerHTML = '<p class="hint">No archive entry found under that designation.</p>';
      return;
    }
    el.innerHTML = `<p class="lore-text">${data.summary}</p>`;
  } catch (err) {
    el.innerHTML = `<div class="error-text">Recall failed: ${err.message}</div>`;
  }
});

// ---------- Builds (mini) ----------
$('#builds-form')?.addEventListener('submit', async (e) => {
  e.preventDefault();
  const frame = $('#builds-input').value.trim();
  const el = $('#builds-results');
  if (!frame) return;
  el.innerHTML = '<div class="loading">Pulling loadout archive&hellip;</div>';
  try {
    const res = await fetch(`/api/builds/${encodeURIComponent(frame)}`);
    const results = await res.json();
    if (!results.length) {
      el.innerHTML = '<div class="hint">No curated build on file for that frame yet.</div>';
      return;
    }
    el.innerHTML = '';
    for (const b of results) {
      const div = document.createElement('div');
      div.className = 'build-card';
      const mods = b.mods.map((m) => `<span class="mod-chip">${m}</span>`).join('');
      div.innerHTML = `
        <div class="build-card__name">${b.name} <span style="color:var(--text-dim); font-weight:400; font-size:12px;">(${b.forma_count} forma)</span></div>
        <div class="build-card__mods">${mods}</div>`;
      el.appendChild(div);
    }
  } catch (err) {
    el.innerHTML = `<div class="error-text">Pull failed: ${err.message}</div>`;
  }
});

setGlobalRefreshHandler(loadCycles);
loadCycles();
// Cycles/daily data are server-cached for 24h; this refresh mainly catches
// fissure/sortie/trader/arbitration changes and re-syncs cycle expiry after
// a rollover — no need to poll every few seconds. Timers that hit zero
// also trigger an immediate refresh via registerCountdown's onZero default.
setInterval(loadCycles, 5 * 60_000);
