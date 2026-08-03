// Project ORDIS — full Market Relay page.

$('#market-form').addEventListener('submit', async (e) => {
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
    for (const item of items.slice(0, 15)) {
      const div = document.createElement('div');
      div.className = 'result-item';
      // image_url is a best-effort guess (see market.py caveat) — hide
      // the <img> entirely on load failure rather than show a broken-image icon.
      const iconHtml = item.image_url
        ? `<img src="${item.image_url}" alt="" class="result-item__icon" onerror="console.warn('item icon failed to load:', this.src); this.remove()">`
        : '';
      div.innerHTML = `
        ${iconHtml}
        <div class="result-item__title">${item.name || item.slug}</div>
        <div class="result-item__meta">${(item.tags || []).join(', ')}</div>
        <div class="price-history" data-slug="${item.slug}"><span class="hint">loading price history&hellip;</span></div>
        <div class="seller-list" data-slug="${item.slug}"><div class="hint">loading sellers&hellip;</div></div>`;
      el.appendChild(div);
      fetchSellers(item.slug, div.querySelector('.seller-list'));
      fetchHistory(item.slug, div.querySelector('.price-history'));
    }
  } catch (err) {
    el.innerHTML = `<div class="error-text">Query failed: ${err.message}</div>`;
  }
});

async function fetchSellers(slug, targetEl) {
  try {
    const res = await fetch(`/api/market/sellers/${encodeURIComponent(slug)}`);
    const sellers = await res.json();
    if (sellers.error) throw new Error(sellers.error);
    if (!sellers.length) {
      targetEl.innerHTML = '<div class="hint">No active sell orders right now.</div>';
      return;
    }
    targetEl.innerHTML = '';
    for (const s of sellers) {
      const row = document.createElement('div');
      row.className = 'data-row';
      row.innerHTML = `
        <span class="data-row__label">${s.seller} <span style="color:var(--text-dim);">(${s.status})</span></span>
        <span class="data-row__value data-row__value--highlight">${s.platinum}p ${s.quantity > 1 ? `×${s.quantity}` : ''}</span>`;
      targetEl.appendChild(row);
    }
  } catch {
    targetEl.innerHTML = '<div class="hint">sellers unavailable</div>';
  }
}

async function fetchHistory(slug, targetEl) {
  try {
    const res = await fetch(`/api/market/history/${encodeURIComponent(slug)}?days=7`);
    const points = await res.json();
    if (points.error || !points.length) {
      targetEl.innerHTML = '<div class="hint">no recent price history</div>';
      return;
    }
    // Most recent first (API sorts that way); show a compact trend line.
    const newest = points[0];
    const oldest = points[points.length - 1];
    const delta = newest.avg_price != null && oldest.avg_price != null
      ? (newest.avg_price - oldest.avg_price)
      : null;
    const trendCls = delta == null ? '' : delta > 0 ? 'data-row__value--warn' : 'data-row__value--highlight';
    const trendArrow = delta == null ? '' : delta > 0 ? '▲' : delta < 0 ? '▼' : '→';
    const deltaLabel = delta != null ? ` ${trendArrow} ${Math.abs(delta).toFixed(1)}p vs ${points.length}d ago` : '';
    targetEl.innerHTML = `<div class="data-row"><span class="data-row__label">7-day avg sell price</span><span class="data-row__value ${trendCls}">${newest.avg_price != null ? newest.avg_price.toFixed(1) + 'p' : 'n/a'}${deltaLabel}</span></div>`;
  } catch {
    targetEl.innerHTML = '<div class="hint">price history unavailable</div>';
  }
}
