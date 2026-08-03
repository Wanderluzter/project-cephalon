// Project ORDIS — full Loadout Archive page.

function confidenceBadge(b) {
  if (b.confidence === 'high') return '<span class="build-card__badge build-card__badge--high">verified direction</span>';
  return '<span class="build-card__badge build-card__badge--directional">directional — verify before Forma-ing</span>';
}

$('#builds-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const frame = $('#builds-input').value.trim();
  const el = $('#builds-results');
  if (!frame) return;
  el.innerHTML = '<div class="loading">Pulling loadout archive&hellip;</div>';
  try {
    const res = await fetch(`/api/builds/${encodeURIComponent(frame)}`);
    const results = await res.json();
    if (!results.length) {
      el.innerHTML = '<div class="hint">No build on file for that frame yet — you can submit one below.</div>';
      return;
    }
    el.innerHTML = '';
    for (const b of results) {
      const div = document.createElement('div');
      div.className = 'build-card';
      const mods = b.mods.map((m) => `<span class="mod-chip">${m}</span>`).join('');
      const sourceLabel = b.source === 'community' ? 'community submitted' : 'curated';
      div.innerHTML = `
        <div class="build-card__name">${b.name} <span style="color:var(--text-dim); font-weight:400; font-size:12px;">(${b.forma_count} forma, ${sourceLabel})</span></div>
        <div class="build-card__mods">${mods}</div>
        ${confidenceBadge(b)}
        ${b.notes ? `<div class="result-item__meta" style="margin-top:6px;">${b.notes}</div>` : ''}`;
      el.appendChild(div);
    }
  } catch (err) {
    el.innerHTML = `<div class="error-text">Pull failed: ${err.message}</div>`;
  }
});

// ---------- Browse all frames with builds on file ----------
async function loadFrameIndex() {
  const el = $('#builds-index');
  if (!el) return;
  try {
    const res = await fetch('/api/builds');
    const data = await res.json();
    if (data.meta && data.meta.as_of) {
      $('#builds-as-of').textContent = `Curated seed last reviewed: ${data.meta.as_of}. ${data.meta.warning || ''}`;
    }
    el.innerHTML = data.frames.length
      ? data.frames.map((f) => `<span class="mod-chip" style="cursor:pointer;" data-frame="${f}">${f}</span>`).join(' ')
      : '<span class="hint">No frames on file yet.</span>';
    el.querySelectorAll('[data-frame]').forEach((chip) => {
      chip.addEventListener('click', () => {
        $('#builds-input').value = chip.dataset.frame;
        $('#builds-form').dispatchEvent(new Event('submit'));
      });
    });
  } catch {
    el.innerHTML = '<span class="hint">frame list unavailable</span>';
  }
}

// ---------- Submit a build ----------
$('#submit-build-form')?.addEventListener('submit', async (e) => {
  e.preventDefault();
  const status = $('#submit-build-status');
  const frame = $('#submit-frame').value.trim();
  const name = $('#submit-name').value.trim();
  const mods = $('#submit-mods').value.split(',').map((m) => m.trim()).filter(Boolean);
  const formaCount = parseInt($('#submit-forma').value, 10) || 0;
  const notes = $('#submit-notes').value.trim();

  if (!frame || !name || !mods.length) {
    status.textContent = 'Frame, build name, and at least one mod are required.';
    return;
  }
  status.textContent = 'Submitting…';
  try {
    const res = await fetch('/api/builds/submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ frame, name, mods, forma_count: formaCount, notes }),
    });
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    status.textContent = `Submitted "${data.name}" for ${data.frame}. Thanks, Operator.`;
    $('#submit-build-form').reset();
    loadFrameIndex();
  } catch (err) {
    status.textContent = `Submission failed: ${err.message}`;
  }
});

loadFrameIndex();
