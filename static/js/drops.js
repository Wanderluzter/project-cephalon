// Project ORDIS — full Item Hunter / Drop Tracker page.

$('#hunter-form').addEventListener('submit', async (e) => {
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
    const uniqueItems = new Set(hits.map((h) => h.item)).size;
    const summary = document.createElement('div');
    summary.className = 'hint';
    summary.style.marginBottom = '10px';
    summary.textContent = `${uniqueItems} item${uniqueItems === 1 ? '' : 's'} matched, ${hits.length} known source${hits.length === 1 ? '' : 's'} total.`;
    el.appendChild(summary);
    el.appendChild(renderGroupedDropResults(hits));
  } catch (err) {
    el.innerHTML = `<div class="error-text">Scan failed: ${err.message}</div>`;
  }
});

$('#set-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const query = $('#set-input').value.trim();
  const el = $('#set-results');
  if (!query) return;
  el.innerHTML = '<div class="loading">Planning set&hellip;</div>';
  try {
    const res = await fetch(`/api/drops/set?query=${encodeURIComponent(query)}`);
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    if (!data.components || !data.components.length) {
      el.innerHTML = '<div class="hint">No matching components found.</div>';
      return;
    }
    el.innerHTML = '';
    const summary = document.createElement('div');
    summary.className = 'hint';
    summary.style.marginBottom = '10px';
    summary.textContent = `${data.components.length} component${data.components.length === 1 ? '' : 's'} found — ${data.total_known_ducats} ducats total known value.`;
    el.appendChild(summary);
    for (const c of data.components) {
      const row = document.createElement('div');
      row.className = 'result-item';
      const ducatLabel = c.ducats != null ? `${c.ducats} ducats` : 'ducat value unknown';
      const chanceLabel = c.best_chance != null ? `${c.best_chance}%` : 'chance n/a';
      row.innerHTML = `
        <div class="result-item__title">${c.item}</div>
        <div class="result-item__meta">${c.rarity || 'rarity unknown'} · ${ducatLabel} · ${c.source_count} known source${c.source_count === 1 ? '' : 's'}</div>
        <div class="result-item__chance">${c.best_location || 'unknown location'} — ${chanceLabel}</div>`;
      el.appendChild(row);
    }
  } catch (err) {
    el.innerHTML = `<div class="error-text">Planning failed: ${err.message}</div>`;
  }
});
