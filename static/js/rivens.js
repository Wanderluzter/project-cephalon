// Project ORDIS — Riven Auctions page.
// Targets Warframe Market v1 (see ordis/riven.py for why — v2 has no
// auctions endpoint yet).

function fmtStat(s) {
  if (!s) return '';
  const val = typeof s.value === 'number' ? s.value : s.value;
  return `${s.attribute_key || 'stat'}: ${val}`;
}

$('#riven-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const weapon = $('#riven-input').value.trim();
  const sortBy = $('#riven-sort').value;
  const el = $('#riven-results');
  if (!weapon) return;
  el.innerHTML = '<div class="loading">Scanning riven auctions&hellip;</div>';
  try {
    const res = await fetch(`/api/rivens/search?weapon=${encodeURIComponent(weapon)}&sort_by=${encodeURIComponent(sortBy)}`);
    const auctions = await res.json();
    if (auctions.error) throw new Error(auctions.error);
    if (!auctions.length) {
      el.innerHTML = '<div class="hint">No live auctions found for that weapon.</div>';
      return;
    }
    el.innerHTML = '';
    for (const a of auctions) {
      const div = document.createElement('div');
      div.className = 'result-item';
      const positives = (a.positive_stats || []).map(fmtStat).join(', ') || 'no positive stats listed';
      const negative = a.negative_stat ? ` — ${fmtStat(a.negative_stat)}` : '';
      const price = a.buyout_price != null
        ? `${a.buyout_price}p buyout`
        : (a.starting_price != null ? `${a.starting_price}p starting bid` : 'price n/a');
      div.innerHTML = `
        <div class="result-item__title">${a.weapon || 'Riven'} — ${price}</div>
        <div class="result-item__meta">${positives}${negative}</div>
        <div class="result-item__meta">Rank ${a.mod_rank ?? '?'} · ${a.re_rolls ?? '?'} rerolls · MR${a.mastery_level ?? '?'} · ${a.polarity || 'unknown polarity'}</div>
        <div class="result-item__chance">${a.seller} (${a.seller_status})</div>`;
      el.appendChild(div);
    }
  } catch (err) {
    el.innerHTML = `<div class="error-text">Scan failed: ${err.message}</div>`;
  }
});

$('#lich-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const weapon = $('#lich-weapon').value.trim();
  const element = $('#lich-element').value.trim();
  const hasEphemera = $('#lich-ephemera').checked;
  const el = $('#lich-results');
  el.innerHTML = '<div class="loading">Scanning Lich/Sister auctions&hellip;</div>';
  try {
    const params = new URLSearchParams();
    if (weapon) params.set('weapon', weapon);
    if (element) params.set('element', element);
    if (hasEphemera) params.set('having_ephemera', 'true');
    const res = await fetch(`/api/liches/search?${params.toString()}`);
    const liches = await res.json();
    if (liches.error) throw new Error(liches.error);
    if (!liches.length) {
      el.innerHTML = '<div class="hint">No live auctions found.</div>';
      return;
    }
    el.innerHTML = '';
    for (const l of liches) {
      const div = document.createElement('div');
      div.className = 'result-item';
      const price = l.buyout_price != null
        ? `${l.buyout_price}p buyout`
        : (l.starting_price != null ? `${l.starting_price}p starting bid` : 'price n/a');
      const ephemeraLabel = l.has_ephemera ? `has ephemera (${l.ephemera || 'unspecified'})` : 'no ephemera';
      const quirksLabel = (l.quirks || []).length ? l.quirks.join(', ') : 'no quirks listed';
      div.innerHTML = `
        <div class="result-item__title">${l.weapon || 'Lich weapon'} — ${price}</div>
        <div class="result-item__meta">${l.element || 'unknown element'} · ${l.damage != null ? l.damage + '% bonus damage' : 'damage n/a'} · ${ephemeraLabel}</div>
        <div class="result-item__meta">${quirksLabel}</div>
        <div class="result-item__chance">${l.seller} (${l.seller_status})</div>`;
      el.appendChild(div);
    }
  } catch (err) {
    el.innerHTML = `<div class="error-text">Scan failed: ${err.message}</div>`;
  }
});
