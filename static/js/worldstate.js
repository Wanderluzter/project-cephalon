// Project ORDIS — full Worldstate page.

let _lastStatusCheck = null;
async function loadServerStatus() {
  const el = $('#ws-server-status');
  try {
    const res = await fetch('/api/server-status');
    const data = await res.json();
    _lastStatusCheck = Date.now();
    el.innerHTML = '';
    const platformLabels = { pc: 'PC', ps4: 'PlayStation', xb1: 'Xbox', switch: 'Switch' };
    for (const [platform, info] of Object.entries(data)) {
      const label = platformLabels[platform] || platform;
      if (info.status === 'up') {
        el.appendChild(dataRow(label, `up · ${info.latency_ms}ms`, 'data-row__value--highlight'));
      } else {
        el.appendChild(dataRow(label, 'down', 'data-row__value--warn'));
      }
    }
    const checkedRow = dataRow('  last checked', '');
    checkedRow.id = 'ws-status-checked';
    el.appendChild(checkedRow);
  } catch (e) {
    el.innerHTML = `<div class="error-text">Status check failed: ${e.message}</div>`;
  }
}

// Local ticking "checked Xs ago" — no need to re-fetch just to update this.
setInterval(() => {
  const row = $('#ws-status-checked');
  if (!row || !_lastStatusCheck) return;
  const v = row.querySelector('.data-row__value');
  if (v) v.textContent = `${Math.round((Date.now() - _lastStatusCheck) / 1000)}s ago`;
}, 1000);

async function loadAll() {
  clearCountdowns();
  try {
    const res = await fetch('/api/worldstate/all');
    const data = await res.json();
    renderCycles(data);
    renderSortie(data.sortie);
    renderArchonHunt(data['archon-hunt']);
    renderFissures(data.fissures);
    renderNightwave(data.nightwave);
    renderTraders(data);
    renderArbitration(data.arbitration);
    renderTeshinRotation(data['steel-path']);
    renderDailyDeals(data['daily-deals']);
    renderFlashSales(data['flash-sales']);
    renderInvasions(data.invasions);
    renderConclave(data['conclave-challenges']);
    renderArchimedeas(data.archimedeas);
    renderNews(data.news);
    renderWeeklyTrackers(data);
    renderMisc(data);
  } catch (e) {
    $('#ws-error').textContent = `Link interrupted: ${e.message}`;
  }
}

function renderCycles(data) {
  const el = $('#ws-cycles');
  el.innerHTML = '';
  const cycles = [
    ['Cetus (Earth)', data['cetus-cycle']],
    ['Regular Earth', data['earth-cycle']],
    ['Orb Vallis (Venus)', data['vallis-cycle']],
    ['Cambion Drift (Deimos)', data['cambion-cycle']],
    ['Zariman', data['zariman-cycle']],
    ['Duviri', data['duviri-cycle']],
  ];
  for (const [label, c] of cycles) el.appendChild(buildCycleRow(label, c));

  // Duviri Circuit weekly choices — CONFIRMED present as duviriCycle.choices,
  // a list of {category, choices: [frame/weapon names]}.
  const duviri = data['duviri-cycle'];
  if (duviri && Array.isArray(duviri.choices) && duviri.choices.length) {
    for (const group of duviri.choices) {
      el.appendChild(dataRow(`  Circuit (${group.category})`, (group.choices || []).join(', ')));
    }
  }
}

function renderSortie(sortie) {
  const el = $('#ws-sortie');
  if (!sortie || sortie.error) { el.innerHTML = '<div class="hint">unavailable</div>'; return; }
  el.innerHTML = '';
  el.appendChild(dataRow('Boss', `${sortie.boss || '—'} (${sortie.faction || '—'})`));
  if (sortie.expiry) {
    const row = dataRow('Ends in', '');
    const v = row.querySelector('.data-row__value');
    registerCountdown(sortie.expiry, (ms) => { v.textContent = fmtDuration(ms); });
    el.appendChild(row);
  }
  (sortie.variants || []).forEach((variant, i) => {
    el.appendChild(dataRow(`Mission ${i + 1}`, `${variant.missionType} — ${variant.node}`));
    el.appendChild(dataRow('  Modifier', variant.modifier || '—'));
  });
}

function renderArchonHunt(hunt) {
  const el = $('#ws-archon');
  if (!hunt || hunt.error) { el.innerHTML = '<div class="hint">unavailable</div>'; return; }
  el.innerHTML = '';
  el.appendChild(dataRow('Boss', `${hunt.boss || '—'} (${hunt.faction || '—'})`));
  if (hunt.expiry) {
    const row = dataRow('Resets in', '');
    const v = row.querySelector('.data-row__value');
    registerCountdown(hunt.expiry, (ms) => { v.textContent = fmtDuration(ms); });
    el.appendChild(row);
  }
  (hunt.missions || []).forEach((m, i) => {
    el.appendChild(dataRow(`Mission ${i + 1}`, `${m.type} — ${m.node}`));
  });
}

function renderFissures(fissures) {
  const el = $('#ws-fissures');
  if (!Array.isArray(fissures) || !fissures.length) { el.innerHTML = '<div class="hint">No active fissures.</div>'; return; }
  el.innerHTML = '';
  const sorted = [...fissures].sort((a, b) => (a.tierNum || 0) - (b.tierNum || 0));
  for (const f of sorted.slice(0, 30)) {
    const row = dataRow(`${f.tier}${f.isStorm ? ' (Steel Path)' : ''}`, `${f.missionType} — ${f.node}`);
    if (f.expiry) {
      const v = row.querySelector('.data-row__value');
      registerCountdown(f.expiry, (ms) => { v.textContent = `${f.missionType} — ${f.node} (${fmtDuration(ms)})`; });
    }
    el.appendChild(row);
  }
}

function renderNightwave(nw) {
  const el = $('#ws-nightwave');
  if (!nw || nw.error) { el.innerHTML = '<div class="hint">unavailable</div>'; return; }
  el.innerHTML = '';
  el.appendChild(dataRow('Season', nw.season ?? '—'));
  const challenges = nw.activeChallenges || [];
  for (const c of challenges) {
    const tag = c.isElite ? '[ELITE] ' : c.isDaily ? '[DAILY] ' : '[WEEKLY] ';
    el.appendChild(dataRow(tag + c.title, `${c.reputation} standing`));
  }
  if (!challenges.length) el.appendChild(dataRow('Challenges', 'none listed'));
}

function renderTraders(data) {
  const el = $('#ws-traders');
  el.innerHTML = '';
  for (const [label, trader] of [["Baro Ki'Teer", data['void-trader']], ['Varzia (Prime Vault)', data['vault-trader']]]) {
    if (!trader || trader.error) { el.appendChild(dataRow(label, 'unavailable')); continue; }
    const status = traderStatus(trader);
    const row = dataRow(label, `${status}${trader.location ? ' — ' + trader.location : ''}`,
      status === 'active' ? 'data-row__value--highlight' : '');
    el.appendChild(row);
    const boundaryIso = status === 'arriving' ? trader.activation : trader.expiry;
    if (boundaryIso) {
      const countdownRow = dataRow(status === 'arriving' ? '  arrives in' : '  leaves in', '');
      const v = countdownRow.querySelector('.data-row__value');
      registerCountdown(boundaryIso, (ms) => { v.textContent = fmtDuration(ms); });
      el.appendChild(countdownRow);
    }
    if (Array.isArray(trader.inventory) && trader.inventory.length) {
      el.appendChild(dataRow('  inventory items', trader.inventory.length));
    }
  }
}

function renderArbitration(arb) {
  const el = $('#ws-arbitration');
  el.innerHTML = '';
  el.appendChild(buildArbitrationRow(arb));
}

function renderTeshinRotation(sp) {
  const el = $('#ws-steelpath');
  if (!sp || sp.error) { el.innerHTML = '<div class="hint">unavailable</div>'; return; }
  el.innerHTML = '';
  if (sp.currentReward) el.appendChild(dataRow('Current reward', `${sp.currentReward.name} (${sp.currentReward.cost} kuva)`, 'data-row__value--highlight'));
  // CONFIRMED: `remaining` is already a pre-formatted string from the API
  // ("5d 11h 43m 58s") — use it directly rather than recomputing.
  if (sp.remaining) el.appendChild(dataRow('Rotation ends in', sp.remaining));
  if (Array.isArray(sp.rotation) && sp.rotation.length) {
    for (const r of sp.rotation) el.appendChild(dataRow(`  ${r.name}`, `${r.cost} kuva`));
  }
  // CONFIRMED via live fetch: `incursions` is a single object with only
  // {id, activation, expiry} — it does NOT include node names. There's no
  // way to show which nodes are running Teshin incursions from this field
  // as-is; showing a fabricated node list would be worse than admitting
  // the gap.
  if (sp.incursions) {
    el.appendChild(dataRow('Incursion window', 'active (node list not exposed by this API field)'));
  }
}

function renderDailyDeals(deals) {
  const el = $('#ws-deals');
  if (!Array.isArray(deals) || !deals.length) { el.innerHTML = '<div class="hint">No deals right now.</div>'; return; }
  el.innerHTML = '';
  for (const d of deals) {
    el.appendChild(dataRow(d.item, `${d.salePrice}cr (${d.discount}% off) — ${d.sold}/${d.total} sold`, 'data-row__value--highlight'));
  }
}

function renderFlashSales(sales) {
  const el = $('#ws-flashsales');
  if (!Array.isArray(sales) || !sales.length) { el.innerHTML = '<div class="hint">None active.</div>'; return; }
  el.innerHTML = '';
  for (const s of sales.slice(0, 15)) {
    const price = s.premiumOverride != null ? `${s.premiumOverride}p` : '';
    const discount = s.discount != null ? ` (${s.discount}% off)` : '';
    el.appendChild(dataRow(s.item, `${price}${discount}`));
  }
}

function renderInvasions(invasions) {
  const el = $('#ws-invasions');
  if (!Array.isArray(invasions) || !invasions.length) { el.innerHTML = '<div class="hint">No active invasions.</div>'; return; }
  el.innerHTML = '';
  for (const inv of invasions.slice(0, 15)) {
    const pct = Math.max(-100, Math.min(100, inv.completion || 0)).toFixed(0);
    el.appendChild(dataRow(inv.node, `${inv.desc} — ${pct}%`));
  }
}

function renderConclave(challenges) {
  const el = $('#ws-conclave');
  if (!Array.isArray(challenges) || !challenges.length) { el.innerHTML = '<div class="hint">None listed.</div>'; return; }
  el.innerHTML = '';
  for (const c of challenges.slice(0, 12)) {
    el.appendChild(dataRow(c.title, `${c.standing} standing`));
  }
}

function renderArchimedeas(list) {
  const el = $('#ws-archimedeas');
  if (!Array.isArray(list) || !list.length) { el.innerHTML = '<div class="hint">No Archimedea data available right now.</div>'; return; }
  el.innerHTML = '';
  for (const a of list) {
    const div = document.createElement('div');
    div.className = 'result-item';
    const missionSummary = (a.missions || [])
      .map((m) => m.missionType || m.faction || 'mission')
      .join(', ');
    const deviations = (a.missions || [])
      .map((m) => m.deviation && m.deviation.name)
      .filter(Boolean)
      .join(', ');
    div.innerHTML = `
      <div class="result-item__title">${a.type || 'Archimedea'}</div>
      <div class="result-item__meta">${missionSummary}${deviations ? ' — ' + deviations : ''}</div>`;
    el.appendChild(div);
  }
}

function renderNews(news) {
  const el = $('#ws-news');
  if (!Array.isArray(news) || !news.length) { el.innerHTML = '<div class="hint">No news items.</div>'; return; }
  el.innerHTML = '';
  const sorted = [...news].sort((a, b) => new Date(b.date) - new Date(a.date));
  for (const n of sorted.slice(0, 12)) {
    const div = document.createElement('div');
    div.className = 'result-item';
    const dateLabel = n.date && n.date !== '1970-01-01T00:00:00.000Z'
      ? new Date(n.date).toLocaleDateString()
      : '';
    div.innerHTML = `
      <div class="result-item__title"><a href="${n.link}" target="_blank" rel="noopener" style="color:inherit;">${n.message}</a></div>
      <div class="result-item__meta">${dateLabel}${n.update ? ' · update' : ''}${n.primeAccess ? ' · prime access' : ''}</div>`;
    el.appendChild(div);
  }
}

function renderWeeklyTrackers(data) {
  const el = $('#ws-weekly');
  el.innerHTML = '';

  // NOTE: these three endpoints are confirmed to exist (via the official
  // OpenAPI spec) but I haven't seen a live response for any of them, so
  // I'm rendering generically rather than guessing at specific field
  // names I can't verify. If this looks sparse, that's why — tell me what
  // you see and I'll wire up a proper renderer.
  const sections = [
    ['1999 Calendar (Hex / KIM rewards)', data.calendar],
    ['Weekly Challenges', data['weekly-challenges']],
    ["Clan Weekly Initiative", data['clan-weekly-initiative']],
  ];

  for (const [label, obj] of sections) {
    const header = document.createElement('div');
    header.className = 'data-row';
    header.innerHTML = `<span class="data-row__label" style="font-weight:600;color:var(--gold);">${label}</span>`;
    el.appendChild(header);
    if (!obj || obj.error) {
      el.appendChild(dataRow('  status', 'unavailable from this API right now'));
      continue;
    }
    el.appendChild(renderGenericFields(obj));
  }

  const kuva = data.kuva;
  const kuvaHeader = document.createElement('div');
  kuvaHeader.className = 'data-row';
  kuvaHeader.innerHTML = `<span class="data-row__label" style="font-weight:600;color:var(--gold);">Kuva Missions</span>`;
  el.appendChild(kuvaHeader);
  if (Array.isArray(kuva) && kuva.length) {
    for (const k of kuva.slice(0, 6)) {
      el.appendChild(dataRow(`  ${k.type || 'Kuva mission'}`, k.node || '—'));
    }
  } else {
    el.appendChild(dataRow('  status', 'none active right now'));
  }
}

// Generic best-effort renderer for response shapes I haven't confirmed
// live — shows top-level scalar fields as rows, arrays as a count, and
// skips deeply nested objects rather than guessing their structure.
function renderGenericFields(obj) {
  const wrap = document.createElement('div');
  if (typeof obj !== 'object' || obj === null) {
    wrap.appendChild(dataRow('  value', String(obj)));
    return wrap;
  }
  const entries = Object.entries(obj).slice(0, 10);
  for (const [key, val] of entries) {
    if (val == null) continue;
    if (Array.isArray(val)) {
      wrap.appendChild(dataRow(`  ${key}`, `${val.length} item${val.length === 1 ? '' : 's'}`));
    } else if (typeof val === 'object') {
      wrap.appendChild(dataRow(`  ${key}`, '(nested data)'));
    } else {
      wrap.appendChild(dataRow(`  ${key}`, String(val)));
    }
  }
  return wrap;
}

function renderMisc(data) {
  const el = $('#ws-misc');
  el.innerHTML = '';
  const simaris = data.simaris;
  if (simaris && !simaris.error) {
    el.appendChild(dataRow('Simaris target', `${simaris.target}${simaris.isTargetActive ? ' (active)' : ''}`));
  }
  const persistent = data['persistent-enemies'];
  if (Array.isArray(persistent)) {
    el.appendChild(dataRow('Kuva Liches / Sisters', persistent.length || 'none currently'));
  }
  const darkSectors = data['dark-sectors'];
  if (Array.isArray(darkSectors)) {
    // Investigated further: api.warframestat.us models a distinct
    // "DarkSectorHistory" schema separate from "Mission" (confirmed via
    // a community Rust client's schema list), which suggests dark
    // sectors ARE tracked at the mission/node level somewhere in this
    // API family. I could not confirm an exact live field name for a
    // per-mission flag within reasonable research effort, though — and
    // guessing one would just risk a new silent bug the same way earlier
    // field-name guesses did. Left honest rather than "fixed."
    const label = darkSectors.length
      ? `${darkSectors.length} active`
      : "none reported by this endpoint. It appears to track only historical Solar Rail conflict data, not current per-node status — investigated further but couldn't confirm a live per-mission dark-sector field within this API in the time available.";
    el.appendChild(dataRow('Dark sectors', label));
  }
  const news = data.news;
  if (Array.isArray(news) && news.length) {
    el.appendChild(dataRow('Latest news', news[news.length - 1].message || '—'));
  }
}

setGlobalRefreshHandler(loadAll);
loadAll();
setInterval(loadAll, 5 * 60_000);

loadServerStatus();
setInterval(loadServerStatus, 60_000);
