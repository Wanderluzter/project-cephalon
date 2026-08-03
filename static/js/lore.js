// Project ORDIS — full Archive / Lore page.

$('#lore-form').addEventListener('submit', async (e) => {
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
